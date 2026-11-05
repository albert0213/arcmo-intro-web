# -*- coding: utf-8 -*-
"""
build_demo.py — arcmo.xyz/demo/ (공개 데모 리포트)를 다시 만듭니다.

리포트 화면은 분석 엔진 저장소(AIMotionAnalysisProject)의 web/arcmo_web.html 을 그대로 씁니다.
tools/export_public_report.py 의 정적 모드 shim 과 같은 방식으로 통신 함수만 정적 파일 읽기로
바꾸고, 데모 한 개만 담는 평평한 폴더(demo/*.json, demo/video.mp4)를 읽게 합니다.

데모에만 있는 것
  - 배트: tools/demo/tracking.json 의 프레임별 배트(그립·끝)를 bat.json(arcmo.bat_analysis.v1)으로
  - 공: 임팩트 뒤 공 궤적(노란 점선)과 타구 속도·발사각, 배트 스피드 카드
  - 기준점: benchmarks.json (지금까지 분석한 리포트 분포 — 숫자만, 선수 정보 없음)
  - 이름·브랜드: 선수는 가명, 화면 이름은 Arcmo

사용법
  python tools/demo/build_demo.py \
      --web  ../AIMotionAnalysisProject/AIMotionAnalysis_AnalysisModel_MVP/web/arcmo_web.html \
      --src  <리포트 폴더: summary.json · series.json · pose.json · video.mp4> \
      --bench ../AIMotionAnalysisProject/AIMotionAnalysis_AnalysisModel_MVP/web/benchmarks_table.json \
      --out  demo
"""
import argparse
import datetime as _dt
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PID, RID = "d1", "demo"
OUTPUTS = ("index.html", "manifest.json", "summary.json", "series.json", "pose.json",
           "bat.json", "benchmarks.json", "video.mp4")

MANIFEST_BASE = {
    "version": 1,
    "title": "Arcmo 데모 리포트",
    "note": "실제 분석 결과로 만든 공개 데모입니다. 선수 정보는 가명 처리했습니다.",
    "anonymized": True,
    "user": {"id": "demo", "name": "데모", "teams": []},
    "teams": [{"name": "Arcmo 데모팀", "color": "#073b2d"}],
    "players": [{"id": PID, "number": 7, "name": "김선우", "team": "Arcmo 데모팀",
                 "position": "CF", "lr": "R/R"}],
    "analysis_options": [
        {"key": "스윙 궤적", "label": "스윙 궤적", "overlay": "swing_path", "needs_lr": False},
        {"key": "머리 고정", "label": "시선 움직임", "overlay": "head_stability", "needs_lr": False},
        {"key": "어깨-골반 회전", "label": "어깨-골반 회전", "overlay": "shoulder_hip_rotation", "needs_lr": False},
        {"key": "무게중심", "label": "무게중심", "overlay": "center_shift", "needs_lr": False},
    ],
    "overlay_keys": ["skeleton", "swing_path", "head_stability", "center_shift", "shoulder_hip_rotation"],
}


def read_json(p):
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def write_json(p, obj, pretty=False):
    with open(p, "w", encoding="utf-8") as f:
        if pretty:
            json.dump(obj, f, ensure_ascii=False, indent=1)
        else:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ─────────────────────────────────────────────────────────────
# 데이터
# ─────────────────────────────────────────────────────────────
def bat_doc(tr, n_frames, width, height):
    rows = {r[0]: r for r in tr["bat"]["rows"]}
    manual = set(tr["bat"].get("manual_head_frames") or [])
    frames = []
    for f in range(1, n_frames + 1):
        r = rows.get(f)
        if not r:
            frames.append({"frame": f, "state": "not_detected"})
            continue
        frames.append({
            "frame": f, "state": "detected",
            "knob_px": {"x": r[1], "y": r[2]}, "head_px": {"x": r[3], "y": r[4]},
            "endpoint_identity": "manual_review" if f in manual else "white_mask_reviewed",
        })
    return {
        "schema_version": "arcmo.bat_analysis.v1",
        "created_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "report": {"player_id": PID, "report_id": RID},
        "status": "complete",
        "source_video": {"source_name": "video.mp4", "frame_index_base": 1, "fps": tr["fps"],
                         "width": width, "height": height, "frame_count": n_frames},
        "coordinate_mode": "image_2d_px",
        "tracker": {"active": {"kind": "demo_frame_review", "name": "프레임별 확인 추적 (데모 전용)",
                               "learned": False}},
        "frames": frames,
        "analysis_window": {"start_frame": 1, "end_frame": n_frames,
                            "swing_anchor_frame": tr["impact_frame"]},
        "impact_candidate": {"frame": tr["impact_frame"], "source": "ball_contact"},
        "quality": {"track_status": "complete", "evaluated_frame_count": n_frames,
                    "detected_frame_count": len(rows)},
        "error": None,
    }


def experimental(tr):
    m, sc = tr["metrics"], tr["scale"]
    return {
        "source": "demo_frame_review",
        "bat_speed": {
            "kmh": m["bat_speed_kmh"], "mph": round(m["bat_speed_kmh"] / 1.609344, 1),
            "status": "ok", "point": m["bat_speed_point"], "frame": m["bat_speed_frame"],
            "head_kmh": m["bat_head_speed_kmh"], "by_frame_kmh": m["sweet_spot_speed_by_frame"],
        },
        "ball_speed": {
            "kmh": m["exit_velocity_kmh"], "status": "ok",
            "launch_angle_deg": m["launch_angle_deg"], "pitch_kmh": m["pitch_speed_kmh"],
            "frames_used": len(tr["ball"]["post"]),
            "track": tr["ball"]["post"], "incoming": tr["ball"]["pre"],
        },
        "scale": sc,
        "basis": m["basis"],
    }


def build_data(src, tr, out):
    sm = read_json(os.path.join(src, "summary.json"))
    se = read_json(os.path.join(src, "series.json"))
    pose = read_json(os.path.join(src, "pose.json"))

    sm["player_id"], sm["report_id"] = PID, RID
    sm.setdefault("overlays", {})["swing_path"] = True
    sm["experimental"] = experimental(tr)
    pose["meta"]["player_id"], pose["meta"]["report_id"] = PID, RID
    n = int(pose["meta"].get("n_video_frames") or pose["meta"]["n_frames"])

    write_json(os.path.join(out, "summary.json"), sm)
    write_json(os.path.join(out, "series.json"), se)
    write_json(os.path.join(out, "pose.json"), pose)
    write_json(os.path.join(out, "bat.json"),
               bat_doc(tr, n, pose["meta"]["width"], pose["meta"]["height"]))
    shutil.copyfile(os.path.join(src, "video.mp4"), os.path.join(out, "video.mp4"))

    gaze = sm.get("head_gaze") or {}
    items = [o["label"] for o in MANIFEST_BASE["analysis_options"]]
    mf = dict(MANIFEST_BASE)
    mf["generated_at"] = _dt.datetime.now().isoformat(timespec="seconds")
    mf["reports"] = [{
        "player_id": PID, "report_id": RID, "seq": 1, "date": "2026.09.10",
        "created_at": sm.get("created_at") or "", "analysis_type": "batting",
        "items": items, "memo": "공개 데모 · " + " · ".join(items) + " · 배트 스피드 · 타구",
        "is_complete": True, "has_summary": True, "has_series": True, "has_video": True,
        "overlays": {"skeleton": True, "swing_path": True, "head_stability": True,
                     "center_shift": True, "shoulder_hip_rotation": True},
        "errors": {},
        "head_stability": _num(sm.get("head_stability")),
        "head_gaze_grade": gaze.get("grade"),
        "impact_weight_front": _num(sm.get("impact_weight_front")),
        "impact_weight_rear": _num(sm.get("impact_weight_rear")),
        "separation_deg": _num(sm.get("separation_deg")),
        "bat_side": sm.get("bat_side"),
    }]
    mf["assets"] = {PID + "/" + RID: {"series": True, "pose": True, "video": True, "bat": True,
                                      "benchmarks": os.path.exists(os.path.join(out, "benchmarks.json"))}}
    write_json(os.path.join(out, "manifest.json"), mf, pretty=True)
    return sm


# ─────────────────────────────────────────────────────────────
# 화면 — arcmo_web.html + 데모 shim
# ─────────────────────────────────────────────────────────────
def patch(html, old, new, count=1):
    if html.count(old) < 1:
        sys.exit("arcmo_web.html 에서 바꿀 곳을 못 찾았습니다 (화면 코드가 바뀌었는지 확인):\n  " + old[:120])
    return html.replace(old, new, count)


LAB_DETAIL = r"""    title = '배트 스피드 · 타구';
    const x = sm.experimental || {}, b = x.bat_speed || {}, ball = x.ball_speed || {}, sc = x.scale || {};
    const kv = (k, v) => '<span class="muted">' + k + '</span><span class="n">' + v + '</span><span></span>';
    const cmpx = v => v == null ? '-' : (Number(v) * 100).toFixed(2) + ' cm/px';
    body = '<div class="muted" style="font-size:13.5px">이 데모 스윙은 150fps 영상을 <b style="color:var(--ink)">프레임마다 확인하며</b> '
         + '배트(그립·끝)와 공을 따라가 계산했습니다. 영상의 <b style="color:#e66a1f">주황</b>이 배트, '
         + '<b style="color:#ffd60a">노란 점선</b>이 임팩트 뒤 공이 날아간 길입니다. '
         + '축척은 공·배트가 만나는 깊이에서 잽니다 — 임팩트 전 공이 떨어지는 가속도를 중력에 맞춘 값과 '
         + '공 지름(7.3cm)으로 잰 값의 평균입니다. 키(181cm)로 잰 몸 위치의 축척은 카메라에서 더 멀어 값이 더 큽니다.</div>'
         + '<div class="sect-t" style="margin-top:12px">배트</div><div class="kv">'
         + kv('배트 스피드 (스윗스팟)', kmh(b.kmh) + ' km/h' + (b.mph != null ? ' <span class="dim">(' + Number(b.mph).toFixed(0) + ' mph)</span>' : ''))
         + kv('배트 끝 최고 속도', kmh(b.head_kmh) + ' km/h')
         + kv('잰 곳', '배트 끝에서 약 15cm · 프레임 ' + (b.frame != null ? b.frame : '-'))
         + '</div>'
         + '<div class="sect-t" style="margin-top:12px">타구</div><div class="kv">'
         + kv('타구 속도', kmh(ball.kmh) + ' km/h')
         + kv('발사각', ball.launch_angle_deg != null ? Number(ball.launch_angle_deg).toFixed(0) + '°' : '-')
         + kv('들어온 공 (토스)', kmh(ball.pitch_kmh) + ' km/h')
         + kv('쓴 프레임', ball.frames_used != null ? ball.frames_used + ' (임팩트 뒤)' : '-')
         + '</div>'
         + '<div class="sect-t" style="margin-top:12px">축척</div><div class="kv">'
         + kv('임팩트 지점', cmpx(sc.m_per_px))
         + kv('중력 · 공 지름', cmpx(sc.from_gravity_m_per_px) + ' · ' + cmpx(sc.from_ball_diameter_m_per_px))
         + kv('몸 위치 (키 기준)', cmpx(sc.body_plane_from_height_m_per_px))
         + '</div>'
         + '<div class="dim" style="font-size:12px;margin-top:8px">화면 평면(2D) 기준 어림값입니다. '
         + '카메라 쪽·반대쪽으로 움직인 성분은 빠지므로 실제보다 조금 낮게 나올 수 있습니다.</div>';
  }
"""

DEMO_SHIM = r"""
<!-- ══════════ 공개 데모 (arcmo.xyz/demo) ══════════
     tools/demo/build_demo.py 가 붙입니다. 화면 코드는 arcmo_web.html 그대로이고,
     통신 함수만 이 폴더의 정적 파일 읽기로 바꿉니다. -->
<style>
#login{display:none!important}
.navitem[data-go="manage"],.navitem[data-go="analysis"],.navitem[data-go="settings"],
.navitem[data-go="collect"],.navitem[data-go="clips"],
#btnLogout,#connBox,#hpAnalyze,#hpEdit,#memoCard,
.fcard[data-f="manage"],.fcard[data-f="analysis"],.fcard[data-f="collect"]{display:none!important}
.rrow .sc{display:none!important}
/* 리포트가 하나뿐인 데모 — 비교·삭제·임팩트 지정, 이 영상에 없는 스트라이드(바닥 캘리브레이션 없음)는 숨깁니다 */
#repCompare,#repDelete,.imp-fix,.chip[data-ov="stride"],.chip[data-dov="stride"],.mcard[disabled]{display:none!important}
#pubBar{
  position:sticky;top:0;z-index:40;display:flex;gap:10px;align-items:center;flex-wrap:wrap;
  padding:8px 14px;font-size:12.5px;line-height:1.5;
  background:var(--surface2);border-bottom:1px solid var(--line);color:var(--ink2);
}
#pubBar b{color:var(--ink);font-weight:700}
#pubBar .sp{margin-left:auto;display:flex;gap:8px}
#pubBar .lk{
  border:1px solid var(--line2);background:var(--surface);color:var(--ink2);
  border-radius:8px;padding:3px 9px;font-size:12px;cursor:pointer;
}
#pubBar .lk:hover{background:var(--surface3)}
</style>
<script>
'use strict';
(function(){
  var BASE = location.pathname.replace(/[^/]*$/, '');
  var MF = null;
  function dataURL(rel){ return BASE + rel; }
  function httpErr(status){ var e = new Error('HTTP ' + status); e.status = status; return e; }
  async function getJSON(u){
    var r = await fetch(u, {cache:'no-store'});
    if (!r.ok) throw httpErr(r.status);
    return await r.json();
  }
  function readOnly(){
    var e = new Error('공개 데모입니다 — 촬영·분석·편집은 할 수 없습니다.');
    e.status = 403; return e;
  }
  function isDemo(pid, rid){ return pid === '__PID__' && rid === '__RID__'; }
  function hasAsset(key){
    var a = MF && MF.assets && MF.assets['__PID__/__RID__'];
    return !!(a && a[key]);
  }

  window.url = function(path){
    if (/^\/api\/(report_video|overlay_video)\?/.test(path || '')) return dataURL('video.mp4');
    if (/^\/video_feed/.test(path || '')) return '';
    return BASE + String(path || '').replace(/^\//, '');
  };

  window.api = async function(path, opts){
    opts = opts || {};
    var method = (opts.method || 'GET').toUpperCase();
    var q = path.indexOf('?');
    var bare = q < 0 ? path : path.slice(0, q);
    var args = new URLSearchParams(q < 0 ? '' : path.slice(q + 1));
    if (method !== 'GET' && bare !== '/api/login') throw readOnly();

    if (bare === '/api/health')  return {ok:true, static:true, time: MF && MF.generated_at};
    if (bare === '/api/login')   return {ok:true, user: MF.user};
    if (bare === '/api/bootstrap')
      return {teams: MF.teams, players: MF.players, analysis_options: MF.analysis_options, overlay_keys: MF.overlay_keys};
    if (bare === '/api/teams')   return {teams: MF.teams};
    if (bare === '/api/players') return {players: MF.players};
    if (bare === '/api/benchmarks' || bare === '/api/v1/benchmarks'){
      if (!hasAsset('benchmarks')) throw httpErr(404);
      return await getJSON(dataURL('benchmarks.json'));
    }
    var mr = /^\/api\/players\/([^/]+)\/reports$/.exec(bare);
    if (mr){
      var pid = decodeURIComponent(mr[1]);
      return {player_id: pid, reports: MF.reports.filter(function(r){ return r.player_id === pid; })};
    }
    if (bare === '/api/pose'){
      if (!isDemo(args.get('player_id'), args.get('report_id')) || !hasAsset('pose')) throw httpErr(404);
      return await getJSON(dataURL('pose.json'));
    }
    var mb = /^\/api\/reports\/([^/]+)\/([^/]+)\/bat-analysis$/.exec(bare);
    if (mb){
      if (!isDemo(decodeURIComponent(mb[1]), decodeURIComponent(mb[2])) || !hasAsset('bat')) throw httpErr(404);
      return await getJSON(dataURL('bat.json'));
    }
    var mp = /^\/reports\/([^/]+)\/([^/]+)\/(summary|series|ready)$/.exec(bare);
    if (mp){
      if (!isDemo(decodeURIComponent(mp[1]), decodeURIComponent(mp[2]))) throw httpErr(404);
      if (mp[3] === 'ready') return {is_complete:true, steps:{}, errors:{}};
      if (mp[3] === 'series' && !hasAsset('series')) throw httpErr(404);
      return await getJSON(dataURL(mp[3] + '.json'));
    }
    throw httpErr(404);
  };

  /* 촬영 장비(미니PC)는 찾지 않습니다 — 방문자 기기의 localhost 로 요청이 가지 않게 */
  probeMiniPc = async function(){ S.miniPc.ok = false; return false; };

  /* ── 배트 스피드 · 타구 카드 (원본에서는 설정의 '실험 지표 표시'를 켜야 보입니다) ── */
  labOn = function(){ return true; };
  labValHTML = function(sm){
    var b = ((sm && sm.experimental) || {}).bat_speed || {};
    return '<span class="v">' + kmh(b.kmh) + '<small> km/h 배트</small></span>';
  };
  labNote = function(sm){
    var ball = ((sm && sm.experimental) || {}).ball_speed || {};
    return '타구 ' + kmh(ball.kmh) + ' km/h · 발사각 '
      + (ball.launch_angle_deg != null ? Number(ball.launch_angle_deg).toFixed(0) + '°' : '-');
  };

  /* ── 임팩트 뒤 공 궤적 — 스윙 궤적 위에 노란 점선 ── */
  var baseSwing = drawSwingPath;
  drawSwingPath = function(ctx, g, videoIndex, poseIndex, R){
    baseSwing(ctx, g, videoIndex, poseIndex, R);
    R = R || S.rep;
    var ball = R && R.summary && R.summary.experimental && R.summary.experimental.ball_speed;
    var tr = ball && ball.track, inc = ball && ball.incoming;
    if (!tr || !tr.length) return;
    var frame = videoIndex + 1, rows = tr.filter(function(r){ return r[0] <= frame; });
    if (!rows.length) return;
    var pts = rows.map(function(r){ return [r[1], r[2]]; });
    if (inc && inc.length) { var l = inc[inc.length - 1]; pts.unshift([l[1], l[2]]); }   // 맞은 자리에서 시작
    ctx.save();
    ctx.setLineDash([7 * g.s, 6 * g.s]);
    _poly(ctx, g, pts, '#ffd60a', 2.5);
    ctx.setLineDash([]);
    _ring(ctx, g, pts[0], '#ffd60a', 7, 2);
    var last = rows[rows.length - 1];
    if (frame - last[0] <= 1) _dot(ctx, g, [last[1], last[2]], '#ffd60a', 6);
    if (rows.length === tr.length){
      var tip = pts[pts.length - 1], fs = Math.round(15 * g.s / Math.max(g.s, .5));
      ctx.font = '600 ' + Math.max(11, Math.round(14 * g.s)) + 'px system-ui, sans-serif';
      ctx.fillStyle = '#ffd60a'; ctx.textAlign = 'right'; ctx.textBaseline = 'top';
      var txt = kmh(ball.kmh) + ' km/h · ' + Number(ball.launch_angle_deg).toFixed(0) + '°';
      ctx.fillText(txt, _X(g, tip) - 6 * g.s, _Y(g, tip) + 14 * g.s);
    }
    ctx.restore();
  };

  function mountBar(){
    if (document.getElementById('pubBar')) return;
    var bar = document.createElement('div');
    bar.id = 'pubBar';
    bar.innerHTML =
      '<span><b>' + esc(MF.title) + '</b></span>'
      + '<span>' + esc(MF.note || '') + '</span>'
      + '<span class="sp"><span style="align-self:center">'
      + esc((MF.generated_at || '').slice(0, 10)) + ' 갱신</span>'
      + '<button class="lk" id="pubLink">이 리포트 링크 복사</button></span>';
    var main = document.querySelector('main');
    main.parentNode.insertBefore(bar, main);
    document.getElementById('pubLink').onclick = function(){
      var u = location.origin + location.pathname;
      if (S.rep && S.rep.pid) u += '?p=' + encodeURIComponent(S.rep.pid) + '&r=' + encodeURIComponent(S.rep.rid);
      try{ navigator.clipboard.writeText(u); toast('링크를 복사했습니다'); }
      catch(e){ prompt('링크', u); }
    };
  }

  var Q = new URLSearchParams(location.search);
  var LINK_PID = Q.get('p'), LINK_RID = Q.get('r');

  var origOpen = window.openReport;
  window.openReport = function(pid, rid){
    try{ history.replaceState(null, '', location.pathname + '?p=' + encodeURIComponent(pid) + '&r=' + encodeURIComponent(rid)); }catch(e){}
    return origOpen.apply(this, arguments);
  };
  var origGo = window.go;
  window.go = function(view){
    if (view === 'home'){ try{ history.replaceState(null, '', location.pathname); }catch(e){} }
    return origGo.apply(this, arguments);
  };

  (async function(){
    try{ MF = await getJSON(dataURL('manifest.json')); }
    catch(e){
      document.body.innerHTML = '<div style="padding:40px;font:15px/1.6 system-ui">'
        + 'manifest.json 을 읽지 못했습니다. 정적 서버로 열어야 합니다 — <code>python -m http.server 8080</code></div>';
      return;
    }
    document.title = MF.title || document.title;
    S.server = '';
    S.user = MF.user;
    await bootstrap();
    mountBar();
    var p = LINK_PID && playerById(LINK_PID);
    if (p){
      S.home.team = p.team;
      renderHome();
      await selectHomePlayer(p.id);
      if (LINK_RID) openReport(LINK_PID, LINK_RID);
    }
  })();
})();
</script>
"""


def build_index(web, title):
    with open(web, "r", encoding="utf-8") as f:
        html = f.read()
    if "</body>" not in html:
        sys.exit("arcmo_web.html 에 </body> 가 없습니다.")
    # 화면 이름 — 납품용 빌드는 다른 이름일 수 있습니다. 공개 데모는 Arcmo.
    html = re.sub(r"<title>[^<]*</title>", "<title>%s</title>" % title, html, count=1)
    html = re.sub(r'(<div class="brandtxt"><b>)[^<]*(</b>)', r"\1Arcmo\2", html, count=1)
    html = re.sub(r"(\$\('#barTitle'\)\.textContent = TITLES\[view\] \|\| ')[^']*(')", r"\1Arcmo\2", html, count=1)
    # 스윙 궤적 문구 — 데모의 배트는 모델 후보가 아니라 프레임별로 확인한 값입니다.
    html = patch(html, "'배트 후보 '+batSeen+' / '+batTotal+' 프레임 · 영상에서 확인'",
                 "'배트 '+batSeen+'프레임 추적 · 공 궤적 포함'")
    html = patch(html, "'<br><b style=\"color:#e66a1f\">주황</b>은 모델이 찾은 2D 배트 후보입니다. '",
                 "'<br><b style=\"color:#e66a1f\">주황</b>은 프레임마다 확인해 따라간 배트입니다. '")
    html = patch(html, "'. 실제 공·배트 접촉은 영상으로 확인합니다.'",
                 "'. <b style=\"color:#ffd60a\">노란 점선</b>은 임팩트 뒤 공이 날아간 길입니다.'")
    html = patch(html, "스윙 궤적: 배트 후보를 '", "스윙 궤적: 배트를 '")
    html = patch(html, "' 프레임에서 찾았습니다. '", "' 프레임에서 따라갔습니다. '")
    html = patch(html, "card('lab','배트 · 공 속도 (실험)'", "card('lab','배트 스피드 · 타구'")
    m = re.search(r"    title = '배트 · 공 속도 \(실험\)';\n.*?\n  \}\n(?=  else if \(which === 'bat'\))", html, re.S)
    if not m:
        sys.exit("arcmo_web.html 에서 '배트 · 공 속도' 상세 화면을 못 찾았습니다.")
    html = html[:m.start()] + LAB_DETAIL + html[m.end():]
    shim = DEMO_SHIM.replace("__PID__", PID).replace("__RID__", RID)
    return html.replace("</body>", shim + "\n</body>", 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--web", required=True, help="AIMotionAnalysisProject 의 web/arcmo_web.html")
    ap.add_argument("--src", required=True, help="summary.json · series.json · pose.json · video.mp4 가 있는 폴더")
    ap.add_argument("--tracking", default=os.path.join(HERE, "tracking.json"))
    ap.add_argument("--bench", default=None, help="web/benchmarks_table.json (기준점 표시용)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    html = build_index(a.web, MANIFEST_BASE["title"])   # 화면 코드가 안 맞으면 지우기 전에 멈춥니다
    os.makedirs(a.out, exist_ok=True)
    for name in OUTPUTS:                       # 예전 데모 파일 정리 (swing-overlay.mp4 등 소개 페이지 파일은 그대로)
        p = os.path.join(a.out, name)
        if os.path.isfile(p):
            os.remove(p)
    if a.bench:
        shutil.copyfile(a.bench, os.path.join(a.out, "benchmarks.json"))
    tr = read_json(a.tracking)
    sm = build_data(a.src, tr, a.out)
    with open(os.path.join(a.out, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    x = sm["experimental"]
    print("→ %s  (분리각 %s° · %s · 시선 %s · 배트 %.0f km/h · 타구 %.0f km/h · 발사각 %.0f°)" % (
        a.out, sm.get("separation_deg"), sm.get("separation_method") or "v1",
        (sm.get("head_gaze") or {}).get("grade"), x["bat_speed"]["kmh"], x["ball_speed"]["kmh"],
        x["ball_speed"]["launch_angle_deg"]))


if __name__ == "__main__":
    main()
