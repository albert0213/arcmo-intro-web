/**
 * Arcmo 유입·도입 신청 기록기 (Google Apps Script 웹 앱)
 *
 * arcmo.xyz 의 /lesson/ · /apply/ · 본 페이지가 보내는 기록을 이 스프레드시트에 남깁니다.
 *   - events 시트: 방문·버튼 클릭 (방문자 무작위 id, 유입 경로만. 개인정보 없음)
 *   - leads 시트: 도입 신청 (연락처 등). 새 신청이 오면 메일로 알려 줍니다.
 *   - 통계 시트: 유입 경로별 방문자·클릭·신청 수. 매시간, 그리고 신청이 올 때마다 다시 계산합니다.
 *
 * 설정 방법은 같은 폴더의 README.md 를 보세요.
 */

var EVENTS = 'events';
var LEADS = 'leads';
var STATS = '통계';

var EVENT_HEADERS = ['시각', '이벤트', '유입', '최초유입', '방문자', '페이지', '이전 사이트', '기기'];
var LEAD_HEADERS = ['시각', '연락처', '성함·레슨장', '지역', '연락 방법', '궁금한 점', '유입', '최초유입', '방문자', '기기', '처리 상태', '메모'];

var ALLOWED_EVENTS = {
  landing_view: 1, click_more: 1, click_apply: 1,
  apply_view: 1, form_start: 1, lead_submit: 1, lead_fallback: 1, click_more_after_apply: 1,
  main_view: 1, main_click_apply: 1
};

/* 유입 경로 표시 이름 — 새 커뮤니티를 쓰면 여기에 한 줄 추가하면 됩니다. */
var SOURCE_NAMES = {
  gameone: '게임원', dcinside: '디시인사이드', naver: '네이버', daum: '다음', kakao: '카카오',
  instagram: '인스타그램', youtube: '유튜브', ref: '기타 사이트', direct: '직접 접속'
};

/* ────────────────── 처음 한 번 실행 ────────────────── */

function setup() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  sheet_(ss, EVENTS, EVENT_HEADERS);
  sheet_(ss, LEADS, LEAD_HEADERS);
  sheet_(ss, STATS, null);

  var props = PropertiesService.getScriptProperties();
  if (!props.getProperty('STATS_KEY')) {
    props.setProperty('STATS_KEY', Utilities.getUuid().replace(/-/g, '').slice(0, 20));
  }

  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'refreshStatsSheet') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('refreshStatsSheet').timeBased().everyHours(1).create();

  refreshStatsSheet();
  Logger.log('통계 페이지 열쇠(STATS_KEY): ' + props.getProperty('STATS_KEY'));
  Logger.log('알림 메일 받는 주소: ' + notifyEmail_());
}

function sheet_(ss, name, headers) {
  var sh = ss.getSheetByName(name) || ss.insertSheet(name);
  if (headers && sh.getLastRow() === 0) {
    sh.appendRow(headers);
    sh.setFrozenRows(1);
    sh.getRange(1, 1, 1, headers.length).setFontWeight('bold');
    // 연락처 앞자리 0 이 사라지지 않게 글자로 둡니다.
    sh.getRange(2, 2, sh.getMaxRows() - 1, headers.length - 1).setNumberFormat('@');
  }
  return sh;
}

/* ────────────────── 기록 받기 ────────────────── */

function doPost(e) {
  var d;
  try {
    d = JSON.parse((e && e.postData && e.postData.contents) || '{}');
  } catch (err) {
    return text_('bad json');
  }

  var lock = LockService.getScriptLock();
  try {
    lock.waitLock(10000);
  } catch (err) {
    return text_('busy');
  }
  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var now = new Date();
    var src = src_(d.src), first = src_(d.first), vid = cell_(d.vid, 40);
    var page = cell_(d.page, 80), ref = cell_(d.ref, 80), device = cell_(d.device, 10);

    if (d.kind === 'lead') {
      if (d.website) return text_('ok'); // 봇
      var phone = cell_(d.phone, 20);
      if (!/^0\d{1,2}-?\d{3,4}-?\d{4}$/.test(phone)) return text_('bad phone');
      if (tooMany_(vid)) return text_('slow down');

      var row = [now, phone, cell_(d.name, 80), cell_(d.region, 80), cell_(d.contact, 10),
                 cell_(d.memo, 1000), src, first, vid, device, '새 신청', ''];
      var sheetRow = row.slice();
      sheetRow[1] = "'" + phone; // 앞자리 0 이 숫자로 바뀌지 않게
      ss.getSheetByName(LEADS).appendRow(sheetRow);
      ss.getSheetByName(EVENTS).appendRow([now, 'lead_submit', src, first, vid, page, ref, device]);
      lock.releaseLock();
      notify_(row);
      try { refreshStatsSheet(); } catch (err) { /* 통계는 다음 시간에 */ }
      return text_('ok');
    }

    var ev = String(d.event || '');
    if (!ALLOWED_EVENTS[ev]) return text_('unknown event');
    ss.getSheetByName(EVENTS).appendRow([now, ev, src, first, vid, page, ref, device]);
    return text_('ok');
  } finally {
    try { lock.releaseLock(); } catch (err) { /* 이미 풀림 */ }
  }
}

function tooMany_(vid) {
  var cache = CacheService.getScriptCache();
  var key = 'lead_' + (vid || 'none');
  var n = Number(cache.get(key) || 0);
  if (n >= 5) return true;
  cache.put(key, String(n + 1), 3600);
  return false;
}

function notify_(row) {
  try {
    var to = notifyEmail_();
    if (!to) return;
    var src = SOURCE_NAMES[row[6]] || row[6];
    var body = [
      '새 도입 신청이 들어왔습니다.',
      '',
      '연락처: ' + row[1],
      '성함·레슨장: ' + (row[2] || '-'),
      '지역: ' + (row[3] || '-'),
      '편한 연락 방법: ' + row[4],
      '궁금한 점: ' + (row[5] || '-'),
      '유입 경로: ' + src,
      '',
      '시트: ' + SpreadsheetApp.getActiveSpreadsheet().getUrl()
    ].join('\n');
    MailApp.sendEmail(to, '[Arcmo] 도입 신청 — ' + (row[2] || row[1]) + ' (' + src + ')', body);
  } catch (err) {
    console.error('notify failed', err);
  }
}

function notifyEmail_() {
  return PropertiesService.getScriptProperties().getProperty('NOTIFY_EMAIL') ||
         Session.getEffectiveUser().getEmail();
}

/* ────────────────── 통계 보기 (arcmo.xyz/stats/) ────────────────── */

function doGet(e) {
  var p = (e && e.parameter) || {};
  var key = PropertiesService.getScriptProperties().getProperty('STATS_KEY');
  if (!key || p.key !== key) return json_({ ok: false, error: 'key' });
  var days = Math.min(Math.max(Number(p.days) || 30, 1), 365);
  return json_(computeStats_(days, true));
}

function computeStats_(days, withLeads) {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var tz = ss.getSpreadsheetTimeZone() || 'Asia/Seoul';
  var ev = rows_(ss.getSheetByName(EVENTS));
  var ld = rows_(ss.getSheetByName(LEADS));

  var since = new Date(Date.now() - days * 86400000);
  var bySrc = {}, daily = {};
  function srcRow(s) {
    return bySrc[s] || (bySrc[s] = { src: s, name: SOURCE_NAMES[s] || s, visitors: {}, landing_view: 0,
      click_more: 0, click_apply: 0, apply_view: 0, form_start: 0, main_click_apply: 0, leads: 0 });
  }
  function dayRow(t) {
    var k = Utilities.formatDate(t, tz, 'yyyy-MM-dd');
    return daily[k] || (daily[k] = { date: k, visitors: {}, click_more: 0, click_apply: 0, leads: 0 });
  }

  ev.forEach(function (r) {
    var t = r[0];
    if (!(t instanceof Date)) return;
    var name = r[1], s = r[2] || 'direct', vid = r[4];
    var row = srcRow(s);
    var beforeWindow = t < since;
    if (/_view$/.test(name)) row.visitors[vid] = 1;
    if (typeof row[name] === 'number' && name !== 'leads') row[name]++;
    if (beforeWindow) return;
    var dr = dayRow(t);
    if (/_view$/.test(name)) dr.visitors[vid] = 1;
    if (name === 'click_more') dr.click_more++;
    if (name === 'click_apply' || name === 'main_click_apply') dr.click_apply++;
  });

  var leads = [];
  ld.forEach(function (r) {
    var t = r[0];
    if (!(t instanceof Date)) return;
    srcRow(r[6] || 'direct').leads++;
    if (t >= since) dayRow(t).leads++;
    leads.push({ time: Utilities.formatDate(t, tz, 'yyyy-MM-dd HH:mm'), phone: r[1], name: r[2], region: r[3],
                 contact: r[4], memo: r[5], src: SOURCE_NAMES[r[6]] || r[6], status: r[10] });
  });

  var sources = Object.keys(bySrc).map(function (k) {
    var r = bySrc[k];
    r.visitors = Object.keys(r.visitors).length;
    r.cvr = r.visitors ? Math.round(r.leads / r.visitors * 1000) / 10 : 0;
    return r;
  }).sort(function (a, b) { return b.visitors - a.visitors; });

  var series = [];
  for (var i = days - 1; i >= 0; i--) {
    var k = Utilities.formatDate(new Date(Date.now() - i * 86400000), tz, 'yyyy-MM-dd');
    var d = daily[k] || { date: k, visitors: {}, click_more: 0, click_apply: 0, leads: 0 };
    series.push({ date: k, visitors: Object.keys(d.visitors).length, click_more: d.click_more,
                  click_apply: d.click_apply, leads: d.leads });
  }

  var total = { visitors: 0, landing_view: 0, click_more: 0, click_apply: 0, apply_view: 0, form_start: 0, leads: 0 };
  sources.forEach(function (r) {
    Object.keys(total).forEach(function (k) {
      total[k] += k === 'click_apply' ? r.click_apply + r.main_click_apply : r[k];
    });
  });

  var out = { ok: true, updated: Utilities.formatDate(new Date(), tz, 'yyyy-MM-dd HH:mm'), days: days,
              total: total, sources: sources, daily: series };
  if (withLeads) out.leads = leads.reverse().slice(0, 100);
  return out;
}

/* 통계 시트를 다시 씁니다 (매시간 + 신청이 올 때). */
function refreshStatsSheet() {
  var s = computeStats_(30, false);
  var sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(STATS);
  sh.clear();
  var head = ['유입 경로', '방문자(명)', '랜딩 조회', '자세히 보기', '도입 신청 버튼', '신청 화면 조회', '입력 시작', '신청 완료', '방문자 대비 신청(%)'];
  var body = s.sources.map(function (r) {
    return [r.name, r.visitors, r.landing_view, r.click_more, r.click_apply + r.main_click_apply,
            r.apply_view, r.form_start, r.leads, r.cvr];
  });
  var t = s.total;
  body.push(['합계', t.visitors, t.landing_view, t.click_more, t.click_apply, t.apply_view, t.form_start, t.leads,
             t.visitors ? Math.round(t.leads / t.visitors * 1000) / 10 : 0]);
  sh.getRange(1, 1).setValue('누적 (마지막 계산: ' + s.updated + ')').setFontWeight('bold');
  sh.getRange(2, 1, 1, head.length).setValues([head]).setFontWeight('bold');
  sh.getRange(3, 1, body.length, head.length).setValues(body);
  sh.getRange(2 + body.length, 1, 1, head.length).setFontWeight('bold');

  var r0 = body.length + 5;
  sh.getRange(r0, 1).setValue('최근 30일 일별').setFontWeight('bold');
  var dh = ['날짜', '방문자(명)', '자세히 보기', '도입 신청 버튼', '신청 완료'];
  sh.getRange(r0 + 1, 1, 1, dh.length).setValues([dh]).setFontWeight('bold');
  var dv = s.daily.slice().reverse().map(function (d) {
    return [d.date, d.visitors, d.click_more, d.click_apply, d.leads];
  });
  sh.getRange(r0 + 2, 1, dv.length, dh.length).setValues(dv);
  sh.autoResizeColumns(1, head.length);
}

/* ────────────────── 도우미 ────────────────── */

function rows_(sh) {
  if (!sh || sh.getLastRow() < 2) return [];
  return sh.getRange(2, 1, sh.getLastRow() - 1, sh.getLastColumn()).getValues();
}

function src_(v) {
  v = String(v || '').toLowerCase();
  return /^[a-z0-9_-]{1,32}$/.test(v) ? v : 'direct';
}

/* 시트 수식으로 읽히지 않게 막고 길이를 자릅니다. */
function cell_(v, max) {
  v = String(v == null ? '' : v).replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, '').trim().slice(0, max);
  return /^[=+\-@]/.test(v) ? "'" + v : v;
}

function text_(s) {
  return ContentService.createTextOutput(s).setMimeType(ContentService.MimeType.TEXT);
}

function json_(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}
