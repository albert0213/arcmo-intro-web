"""가벼운 데모 페이지(demo/index.html)가 읽는 data.json 과 lite.mp4 를 만듭니다.

전체 리포트 화면(demo/full/)을 build_demo.py 로 먼저 만든 뒤 실행합니다.

    python tools/demo/build_lite.py --full demo/full --video <원본 video.mp4> --out demo

- data.json: 프레임별 스켈레톤·손·머리·배트·공 좌표와 그래프용 값 (1280x720 좌표, 정수/소수 1자리)
- lite.mp4 : 원본 213프레임을 960x540, 30fps 타임라인(= 1/5 슬로모션)으로 다시 인코딩.
             10프레임마다 키프레임을 넣어 프레임 넘기기·드래그가 빠릅니다.
- poster.jpg: 임팩트 프레임 (영상이 오기 전 첫 화면)
- demo/full/video.mp4 도 15프레임마다 키프레임을 넣어 다시 인코딩합니다 (150fps 그대로).
"""
import argparse
import json
import math
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
PLAY_FPS = 30
SWEET_SPOT_FRAC = 0.82   # track_demo.py 와 같은 값 (배트 끝에서 약 15cm)


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def r1(v):
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else round(float(v), 1)


def ipt(p):
    return None if not p else [int(round(p[0])), int(round(p[1]))]


def build_data(full, tracking):
    pose = load(os.path.join(full, "pose.json"))
    series = load(os.path.join(full, "series.json"))["series"]
    sm = load(os.path.join(full, "summary.json"))
    tr = load(tracking)
    meta, ov = pose["meta"], pose["overlays"]
    n = meta["n_frames"]
    impact = tr["impact_frame"]                     # 1부터 세는 프레임 번호
    win = sm.get("analysis_window") or {}
    w0, w1 = int(win.get("start_frame", 0)), int(win.get("end_frame", n - 1))   # 0부터

    skel = []
    for fr in ov["skeleton"]["pts"]:
        skel.append([v for p in (fr or []) for v in (ipt(p) or [None, None])])

    gz = sm["head_gaze"]
    base, body = gz["baseline_y_px"], gz["body_px"]
    head_pct = [None if y is None else r1((base - y) / body * 100) for y in series["head_stability"]["y_px"]]

    rot = series["shoulder_hip_rotation"]
    sep = [r1(v) if v is not None else None for v in rot["separation_deg"]]
    in_win = [(v, i) for i, v in enumerate(sep[w0:w1 + 1], w0) if v is not None]
    sep_peak, sep_peak_i = max(in_win)

    cs = series["center_shift"]
    front = [None if v is None else round(v * 10) for v in cs["front_ratio"]]

    m = tr["metrics"]
    scale = tr["scale"]["m_per_px"]
    rows = {r[0]: r for r in tr["bat"]["rows"]}

    def bat_speed(f):
        a, b = rows.get(f - 1), rows.get(f + 1)
        if not a or not b:
            return None
        pa = (a[1] + SWEET_SPOT_FRAC * (a[3] - a[1]), a[2] + SWEET_SPOT_FRAC * (a[4] - a[2]))
        pb = (b[1] + SWEET_SPOT_FRAC * (b[3] - b[1]), b[2] + SWEET_SPOT_FRAC * (b[4] - b[2]))
        return r1(math.dist(pa, pb) / 2 * tr["fps"] * scale * 3.6)

    bat_win = [35, 110]
    return {
        "schema": "arcmo.demo_lite.v1",
        "src_fps": tr["fps"], "play_fps": PLAY_FPS, "n": n,
        "w": meta["width"], "h": meta["height"],
        "impact": impact, "win": [w0 + 1, w1 + 1],
        "player": {"name": "김선우", "note": "가명", "side": "우타", "date": "2026-09-10",
                   "place": "야외 타격장"},
        "conns": ov["skeleton"]["connections"],
        "skel": skel,
        "hand": [ipt(p) for p in ov["hand_trace"]["pts"]],
        "head": [ipt(p) for p in ov["head_stability"]["pts"]],
        "head_anchor": ov["head_stability"]["anchor"],
        "gaze": {"grade": gz["grade"], "up": r1(gz["up_pct"]), "down": r1(gz["down_pct"]),
                 "up_frame": gz["up_frame"] + 1, "down_frame": gz["down_frame"] + 1,
                 "end": gz["end_frame"] + 1, "pct": head_pct},
        "rot": {"method": rot.get("method"), "sh": [r1(v) if v is not None else None for v in rot["shoulder_deg"]],
                "hip": [r1(v) if v is not None else None for v in rot["hip_deg"]], "sep": sep,
                "peak": r1(sep_peak), "peak_frame": sep_peak_i + 1},
        "cs": {"range": r1(float(sm["weight_shift_range"])), "front": front},
        "bat": {"win": bat_win, "rows": [rows[f] for f in sorted(rows)],
                "kmh": m["bat_speed_kmh"], "head_kmh": m["bat_head_speed_kmh"],
                "frame": m["bat_speed_frame"],
                "speed": {str(f): bat_speed(f) for f in range(bat_win[0], bat_win[1] + 1)
                          if bat_speed(f) is not None}},
        "ball": {"pre": tr["ball"]["pre"], "post": tr["ball"]["post"],
                 "kmh": m["exit_velocity_kmh"], "deg": m["launch_angle_deg"],
                 "pitch_kmh": m["pitch_speed_kmh"]},
        "scale_cm_px": round(scale * 100, 3),
    }


def encode(video, out, impact):
    mp4 = os.path.join(out, "lite.mp4")
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-i", video,
        "-vf", f"setpts=N/{PLAY_FPS}/TB,scale=960:540", "-r", str(PLAY_FPS),
        "-c:v", "libx264", "-profile:v", "main", "-preset", "slow", "-crf", "28",
        "-g", "10", "-keyint_min", "10", "-sc_threshold", "0", "-bf", "0",
        "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart", mp4], check=True)
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-i", video,
        "-vf", f"select=eq(n\\,{impact - 1}),scale=960:540", "-frames:v", "1", "-q:v", "6",
        os.path.join(out, "poster.jpg")], check=True)


def reencode_full(video, full):
    """전체 리포트 화면 영상도 15프레임마다 키프레임을 넣어 넘기기를 빠르게 합니다 (150fps 그대로)."""
    dst = os.path.join(full, "video.mp4")
    tmp = os.path.join(full, "video.tmp.mp4")
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-i", video,
        "-c:v", "libx264", "-profile:v", "main", "-preset", "slow", "-crf", "27",
        "-g", "15", "-keyint_min", "15", "-sc_threshold", "0", "-bf", "0",
        "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart", tmp], check=True)
    os.replace(tmp, dst)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", required=True, help="build_demo.py 로 만든 전체 리포트 폴더 (demo/full)")
    ap.add_argument("--video", required=True, help="원본 213프레임 video.mp4")
    ap.add_argument("--tracking", default=os.path.join(HERE, "tracking.json"))
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    data = build_data(a.full, a.tracking)
    with open(os.path.join(a.out, "data.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    encode(a.video, a.out, data["impact"])
    reencode_full(a.video, a.full)
    print(f"→ {a.out}  (분리각 {data['rot']['peak']}° · 시선 {data['gaze']['grade']} · "
          f"배트 {data['bat']['kmh']} km/h · 타구 {data['ball']['kmh']} km/h {data['ball']['deg']}°)")


if __name__ == "__main__":
    main()
