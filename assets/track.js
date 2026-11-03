/* Arcmo 유입 기록 — 커뮤니티 랜딩(/lesson/), 신청(/apply/), 본 사이트에서 같이 씁니다.
 *
 * 기록은 Google Apps Script 웹 앱(ops/leads-apps-script/Code.gs)이 구글 시트에 남깁니다.
 * ENDPOINT 가 비어 있으면 아무것도 보내지 않고, 신청 폼은 메일로 보내기로 대신합니다.
 *
 * 유입 경로: 주소의 ?from=gameone (또는 utm_source=) 을 읽어 이 탭이 닫힐 때까지 기억합니다.
 * 방문자 구분: 브라우저에 만든 무작위 id 하나. 이름·연락처는 신청할 때만 보냅니다.
 */
(function () {
  'use strict';

  var ENDPOINT = '';

  var SRC_RE = /^[a-z0-9_-]{1,32}$/;
  var REF_SOURCES = [
    [/(^|\.)gameone\.kr$/, 'gameone'],
    [/(^|\.)dcinside\.com$/, 'dcinside'],
    [/(^|\.)naver\.com$/, 'naver'],
    [/(^|\.)daum\.net$/, 'daum'],
    [/(^|\.)instagram\.com$/, 'instagram'],
    [/(^|\.)kakao\.com$/, 'kakao'],
    [/(^|\.)youtube\.com$/, 'youtube']
  ];

  function store(kind) {
    try { return window[kind]; } catch (e) { return null; }
  }
  function get(kind, key) {
    var s = store(kind);
    try { return s ? s.getItem(key) : null; } catch (e) { return null; }
  }
  function put(kind, key, value) {
    var s = store(kind);
    try { if (s) s.setItem(key, value); } catch (e) { /* 사생활 보호 모드 등 */ }
  }

  function clean(v) {
    v = String(v || '').trim().toLowerCase();
    return SRC_RE.test(v) ? v : '';
  }

  function refHost() {
    try {
      if (!document.referrer) return '';
      var h = new URL(document.referrer).hostname;
      return h === location.hostname ? '' : h;
    } catch (e) { return ''; }
  }

  var params;
  try { params = new URLSearchParams(location.search); } catch (e) { params = { get: function () { return null; } }; }

  var host = refHost();
  var src = clean(params.get('from')) || clean(params.get('utm_source')) || clean(params.get('src'));
  if (!src && host) {
    for (var i = 0; i < REF_SOURCES.length; i++) {
      if (REF_SOURCES[i][0].test(host)) { src = REF_SOURCES[i][1]; break; }
    }
  }
  if (!src) src = clean(get('sessionStorage', 'arcmo-src'));
  if (!src && host) src = 'ref';
  if (!src) src = 'direct';
  put('sessionStorage', 'arcmo-src', src);

  var first = clean(get('localStorage', 'arcmo-src-first'));
  if (!first) { first = src; put('localStorage', 'arcmo-src-first', src); }

  var vid = get('localStorage', 'arcmo-vid');
  if (!vid || !/^v[a-z0-9]{8,24}$/.test(vid)) {
    vid = 'v' + Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
    put('localStorage', 'arcmo-vid', vid);
  }

  var device = /Mobi|Android|iPhone|iPad/i.test(navigator.userAgent || '') ? 'mobile' : 'desktop';

  function base(kind) {
    return {
      kind: kind,
      src: src,
      first: first,
      vid: vid,
      page: location.pathname,
      ref: host,
      device: device
    };
  }

  function post(body, keepalive) {
    return fetch(ENDPOINT, {
      method: 'POST',
      mode: 'no-cors',
      keepalive: !!keepalive,
      headers: { 'Content-Type': 'text/plain;charset=UTF-8' },
      body: body
    });
  }

  function track(event, extra) {
    var d = base('event');
    d.event = event;
    if (extra) for (var k in extra) if (Object.prototype.hasOwnProperty.call(extra, k)) d[k] = extra[k];
    if (!ENDPOINT) {
      if (window.console) console.info('[arcmo] (기록 주소 미설정)', event, src);
      return;
    }
    var body = JSON.stringify(d);
    try {
      if (navigator.sendBeacon && navigator.sendBeacon(ENDPOINT, new Blob([body], { type: 'text/plain;charset=UTF-8' }))) return;
    } catch (e) { /* fall through */ }
    try { post(body, true).catch(function () {}); } catch (e) { /* 기록 실패는 화면에 영향 없게 */ }
  }

  /* 신청 — 성공하면 resolve. 기록 주소가 없거나 네트워크가 끊기면 reject. */
  function lead(fields) {
    if (!ENDPOINT) return Promise.reject(new Error('no-endpoint'));
    var d = base('lead');
    for (var k in fields) if (Object.prototype.hasOwnProperty.call(fields, k)) d[k] = fields[k];
    return post(JSON.stringify(d), false);
  }

  /* 같은 사이트 안의 링크에 유입 경로를 붙입니다. */
  function withSrc(url) {
    if (src === 'direct') return url;
    try {
      var u = new URL(url, location.href);
      if (u.origin !== location.origin) return url;
      if (!u.searchParams.get('from')) u.searchParams.set('from', src);
      return u.pathname + u.search + u.hash;
    } catch (e) { return url; }
  }

  /* data-track="이벤트이름" 을 단 링크·버튼은 누를 때 기록합니다. */
  document.addEventListener('click', function (e) {
    var el = e.target && e.target.closest ? e.target.closest('[data-track]') : null;
    if (el) track(el.getAttribute('data-track'));
  }, true);

  window.Arcmo = {
    endpoint: ENDPOINT,
    configured: !!ENDPOINT,
    src: src,
    first: first,
    vid: vid,
    track: track,
    lead: lead,
    withSrc: withSrc
  };
})();
