# -*- coding: utf-8 -*-
"""
track_demo.py — 데모 스윙(150fps) 한 개의 배트·공을 프레임별로 추적하고
배트 스피드 · 타구 속도 · 발사각을 어림합니다. 결과는 tools/demo/tracking.json.

데모 한 개만을 위한 수작업 보조 도구입니다(분석 엔진 기능이 아닙니다).
  - 배트: 배경(전체 프레임 중앙값) 차분 + 흰색(저채도·고명도) 마스크에서 손목에 붙은
    덩어리를 찾아, 손목에서 가장 먼 점을 배트 끝, 반대쪽 끝을 그립으로 둡니다.
    블러로 배트가 번진 77~79 프레임은 확대 이미지를 보고 배트 끝을 직접 찍었습니다(MANUAL_HEAD).
    프레임마다 결과를 영상 위에 그려 눈으로 확인했습니다.
  - 공: 같은 마스크에서 둥근 덩어리를 이전 위치 근처로 따라갑니다. 37~79(임팩트 전), 81~89(임팩트 후).
  - 축척: 임팩트 지점(홈플레이트 위)의 cm/px 을 두 가지로 잽니다.
      (1) 임팩트 전 공의 낙하 가속도를 중력(9.81 m/s²)에 맞춤
      (2) 공 지름(7.3 cm)이 화면에서 차지하는 픽셀
    키(181 cm)로 잰 몸 위치의 축척은 카메라에서 더 멀어 값이 더 큽니다(참고로만 기록).
  - 모든 속도는 2D(화면 평면) 기준 어림값입니다. 카메라 쪽/반대쪽으로 움직인 성분은 빠집니다.

사용법
  python tools/demo/track_demo.py --video <preprocessed_video.mp4> --pose <pose.json> --out tools/demo/tracking.json
  (opencv-python, numpy, scipy, ffmpeg 필요)
"""
import argparse
import json
import os
import subprocess
import tempfile

import cv2
import numpy as np
from scipy.signal import savgol_filter

FPS = 150.0
BAT_FRAMES = range(30, 112)          # 1-based. 112 이후는 배트가 머리 뒤로 가려집니다
MANUAL_HEAD = {77: (476, 342), 78: (547, 340), 79: (610, 345)}
BALL_SEED = (1094, 187, 50)          # 임팩트 전 공이 또렷한 프레임
BALL_POST_SEED = (711, 262, 81)      # 임팩트 직후 첫 프레임
IMPACT_FRAME = 80                    # 공이 79 까지 들어오고 81 부터 튀어 나갑니다
BALL_DIAMETER_CM = 7.3
BALL_DIAMETER_PX = 22.5              # 임팩트 전 공의 세로 폭(가로는 모션 블러로 늘어남)
PLAYER_HEIGHT_CM = 181.0
PLAYER_HEIGHT_PX = 450.0             # 1번 프레임 머리 끝~발, 굽힌 무릎을 편 길이로 어림
SWEET_SPOT_FRAC = 0.82               # 배트 끝에서 약 15 cm (33인치 배트)


def load_frames(video):
    tmp = tempfile.mkdtemp()
    subprocess.run(["ffmpeg", "-v", "error", "-i", video, "-start_number", "1",
                    os.path.join(tmp, "f%03d.png")], check=True)
    n = len([f for f in os.listdir(tmp) if f.endswith(".png")])
    return {i: cv2.imread(os.path.join(tmp, "f%03d.png" % i)) for i in range(1, n + 1)}


def white_mask(im, bg, diff=25, sat=80, val=140):
    g = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
    return ((cv2.absdiff(g, bg) > diff) & (hsv[..., 1] < sat) & (hsv[..., 2] > val)).astype(np.uint8) * 255


def track_bat(fr, bg, pose):
    sk = pose["overlays"]["skeleton"]; J = sk["joints"]; W = pose["overlays"]["wrists"]
    out = {}
    for f in BAT_FRAMES:
        m = white_mask(fr[f], bg)
        p = sk["pts"][f - 1]
        for a, b in [("left_hip", "left_knee"), ("left_knee", "left_ankle"), ("right_hip", "right_knee"),
                     ("right_knee", "right_ankle"), ("left_hip", "right_hip")]:
            cv2.line(m, tuple(map(int, p[J.index(a)])), tuple(map(int, p[J.index(b)])), 0, 60)
        hy = min(p[J.index("left_hip")][1], p[J.index("right_hip")][1])
        cv2.rectangle(m, (0, int(hy) + 10), (m.shape[1], m.shape[0]), 0, -1)   # 바지(흰색) 제외
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        wl, wr = W["l"][f - 1], W["r"][f - 1]
        w = np.array([(wl[0] + wr[0]) / 2, (wl[1] + wr[1]) / 2])
        n, lab, st, _ = cv2.connectedComponentsWithStats(m)
        best = None
        for k in range(1, n):
            if st[k][4] < 60:
                continue
            ys, xs = np.nonzero(lab == k)
            pk = np.stack([xs, ys], 1).astype(float)
            d = np.hypot(*(pk - w).T)
            if d.min() > 45:
                continue
            if best is None or d.max() > best[0]:
                best = (d.max(), pk, d)
        if best is None:
            continue
        _, pk, d = best
        head = pk[d >= np.percentile(d, 99.5)].mean(0)
        manual = f in MANUAL_HEAD
        if manual:
            head = np.array(MANUAL_HEAD[f], float)
        u = (head - w) / np.linalg.norm(head - w)
        near = pk[np.abs((pk - w) @ np.array([-u[1], u[0]])) < 12]
        knob = w + u * min(np.percentile((near - w) @ u, 1), 0) if len(near) else w
        if manual:
            knob = w - u * 10
        out[f] = (knob, head, manual)
    fs = sorted(out)
    K = savgol_filter(np.array([out[f][0] for f in fs]), 7, 2, axis=0)
    H = savgol_filter(np.array([out[f][1] for f in fs]), 5, 2, axis=0)
    return {f: (K[i], H[i], out[f][2]) for i, f in enumerate(fs)}


def track_ball(fr, bg):
    def cands(f, min_a):
        m = white_mask(fr[f], bg, diff=30, val=130)
        n, _, st, cen = cv2.connectedComponentsWithStats(m)
        return [(cen[k][0], cen[k][1]) for k in range(1, n)
                if min_a <= st[k][4] <= 900 and 0.6 < st[k][2] / st[k][3] < 1.8]

    pre = {}
    for step in (-1, 1):
        pos = BALL_SEED[:2]; last = None
        f = BALL_SEED[2]
        while 1 <= f < IMPACT_FRAME:
            c = [x for x in cands(f, 150) if np.hypot(x[0] - pos[0], x[1] - pos[1]) < 40]
            if not c:
                break
            b = min(c, key=lambda x: np.hypot(x[0] - pos[0], x[1] - pos[1]))
            pre[f] = b
            pos = (2 * b[0] - last[0], 2 * b[1] - last[1]) if last else b
            last = b; f += step
    post = {}
    pos = BALL_POST_SEED[:2]
    for f in range(BALL_POST_SEED[2], BALL_POST_SEED[2] + 15):
        c = [x for x in cands(f, 300) if np.hypot(x[0] - pos[0], x[1] - pos[1]) < 60]
        if not c:
            break
        b = min(c, key=lambda x: np.hypot(x[0] - pos[0], x[1] - pos[1]))
        pos = (2 * b[0] - post[f - 1][0], 2 * b[1] - post[f - 1][1]) if f - 1 in post else (b[0] + 47, b[1] - 31)
        post[f] = b
    return pre, post


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--pose", required=True, help="리포트 pose.json (wrists 포함)")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "tracking.json"))
    a = ap.parse_args()

    fr = load_frames(a.video)
    bg = np.median(np.array([cv2.cvtColor(fr[i], cv2.COLOR_BGR2GRAY) for i in sorted(fr)[:150]]), 0).astype(np.uint8)
    pose = json.load(open(a.pose, encoding="utf-8"))

    bat = track_bat(fr, bg, pose)
    pre, post = track_ball(fr, bg)

    # 축척 (임팩트 지점 깊이)
    f = np.array(sorted(pre)); t = (f - f[0]) / FPS
    y = np.array([pre[i][1] for i in f]); x = np.array([pre[i][0] for i in f])
    py = np.polyfit(t, y, 2); px = np.polyfit(t, x, 1)
    scale_g = 9.81 / (2 * py[0])                       # m/px
    scale_d = BALL_DIAMETER_CM / 100 / BALL_DIAMETER_PX
    scale = (scale_g + scale_d) / 2
    scale_body = PLAYER_HEIGHT_CM / 100 / PLAYER_HEIGHT_PX

    # 타구
    f2 = np.array(sorted(post)); t2 = (f2 - f2[0]) / FPS
    vx = np.polyfit(t2, [post[i][0] for i in f2], 1)[0]
    vy = np.polyfit(t2, [post[i][1] for i in f2], 1)[0]
    exit_kmh = float(np.hypot(vx, vy) * scale * 3.6)
    launch = float(np.degrees(np.arctan2(-vy, vx)))
    vin = np.hypot(px[0], 2 * py[0] * t[-1] + py[1])
    pitch_kmh = float(vin * scale * 3.6)

    # 배트: 앞뒤 프레임 차이로 속도
    def speed(fr_no, frac):
        k0, h0, _ = bat[fr_no - 1]; k1, h1, _ = bat[fr_no + 1]
        p0 = k0 + frac * (h0 - k0); p1 = k1 + frac * (h1 - k1)
        return float(np.linalg.norm(p1 - p0) / 2 * FPS * scale * 3.6)
    rng = [i for i in range(IMPACT_FRAME - 6, IMPACT_FRAME + 2) if i - 1 in bat and i + 1 in bat]
    sweet = {i: speed(i, SWEET_SPOT_FRAC) for i in rng}
    head = {i: speed(i, 1.0) for i in rng}
    peak = max(sweet, key=sweet.get)

    res = {
        "schema": "arcmo.demo_tracking.v1",
        "fps": FPS,
        "impact_frame": IMPACT_FRAME,
        "frame_index_base": 1,
        "bat": {
            "rows": [[i, round(float(bat[i][0][0]), 1), round(float(bat[i][0][1]), 1),
                      round(float(bat[i][1][0]), 1), round(float(bat[i][1][1]), 1)] for i in sorted(bat)],
            "row_format": ["frame", "knob_x", "knob_y", "head_x", "head_y"],
            "manual_head_frames": sorted(MANUAL_HEAD),
        },
        "ball": {
            "pre": [[int(i), round(float(pre[i][0]), 1), round(float(pre[i][1]), 1)] for i in sorted(pre)],
            "post": [[int(i), round(float(post[i][0]), 1), round(float(post[i][1]), 1)] for i in sorted(post)],
        },
        "scale": {
            "m_per_px": round(scale, 6),
            "from_gravity_m_per_px": round(float(scale_g), 6),
            "from_ball_diameter_m_per_px": round(scale_d, 6),
            "body_plane_from_height_m_per_px": round(scale_body, 6),
            "player_height_cm": PLAYER_HEIGHT_CM,
            "note": "공·배트가 만나는 깊이의 축척. 몸(키 기준)은 카메라에서 더 멀어 축척이 더 큽니다.",
        },
        "metrics": {
            "bat_speed_kmh": round(sweet[peak], 1),
            "bat_speed_point": "sweet_spot_15cm_from_tip",
            "bat_speed_frame": peak,
            "bat_head_speed_kmh": round(max(head.values()), 1),
            "exit_velocity_kmh": round(exit_kmh, 1),
            "launch_angle_deg": round(launch, 1),
            "pitch_speed_kmh": round(pitch_kmh, 1),
            "sweet_spot_speed_by_frame": {str(k): round(v, 1) for k, v in sweet.items()},
            "head_speed_by_frame": {str(k): round(v, 1) for k, v in head.items()},
            "basis": "2d_image_plane",
        },
    }
    with open(a.out, "w", encoding="utf-8") as fo:
        json.dump(res, fo, ensure_ascii=False, indent=1)
    m = res["metrics"]
    print("배트 스피드(스윗스팟) %.0f km/h · 배트 끝 %.0f km/h · 타구 %.0f km/h · 발사각 %.0f° · 투구 %.0f km/h"
          % (m["bat_speed_kmh"], m["bat_head_speed_kmh"], m["exit_velocity_kmh"], m["launch_angle_deg"], m["pitch_speed_kmh"]))
    print("축척 %.3f cm/px (중력 %.3f · 공 지름 %.3f · 키 기준 몸 %.3f)"
          % (scale * 100, scale_g * 100, scale_d * 100, scale_body * 100))


if __name__ == "__main__":
    main()
