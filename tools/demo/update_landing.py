# -*- coding: utf-8 -*-
"""
update_landing.py — 소개 페이지(index.html) 첫 화면 패널의 데모 데이터(const ARC)를 갱신합니다.

  - bat/batWin/impact : tools/demo/tracking.json 의 프레임별 배트 (임팩트 전 0.3초 ~ 후 0.2초)
  - ball              : 임팩트 전·후 공 위치와 타구 속도·발사각
  - sh/hip/sep        : --series 를 주면 리포트 series.json 의 어깨·골반 회전 (패널은 150 프레임)

사용법
  python tools/demo/update_landing.py [--series demo/series.json]
"""
import argparse
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
ARC_RE = re.compile(r"const ARC=(\{.*?\});\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", default=os.path.join(ROOT, "index.html"))
    ap.add_argument("--tracking", default=os.path.join(HERE, "tracking.json"))
    ap.add_argument("--series", default=None)
    a = ap.parse_args()

    with open(a.html, "r", encoding="utf-8") as f:
        html = f.read()
    m = ARC_RE.search(html)
    if not m:
        raise SystemExit("index.html 에서 const ARC 를 찾지 못했습니다.")
    arc = json.loads(m.group(1))
    tr = json.load(open(a.tracking, encoding="utf-8"))
    F = len(arc["pts"])
    fps, imp = tr["fps"], tr["impact_frame"]

    arc["impact"] = imp
    arc["batWin"] = [imp - int(round(0.3 * fps)), imp + int(round(0.2 * fps))]
    arc["bat"] = [r for r in tr["bat"]["rows"] if 1 <= r[0] <= F]
    mt = tr["metrics"]
    arc["ball"] = {
        "pre": [r for r in tr["ball"]["pre"] if r[0] <= F],
        "post": [r for r in tr["ball"]["post"] if r[0] <= F],
        "kmh": round(mt["exit_velocity_kmh"]),
        "deg": round(mt["launch_angle_deg"]),
        "batKmh": round(mt["bat_speed_kmh"]),
    }
    if a.series:
        s = json.load(open(a.series, encoding="utf-8"))["series"]["shoulder_hip_rotation"]
        r1 = lambda v: None if v is None else round(float(v), 1)
        for key, src in (("sh", "shoulder_deg"), ("hip", "hip_deg"), ("sep", "separation_deg")):
            vals = [r1(v) for v in s[src][:F]]
            # 패널 그래프는 빈 값을 못 그립니다 — 앞 값으로 채웁니다
            last = next((v for v in vals if v is not None), 0.0)
            arc[key] = [last := (v if v is not None else last) for v in vals]

    new = "const ARC=" + json.dumps(arc, ensure_ascii=False, separators=(",", ":")) + ";\n"
    html = html[:m.start()] + new + html[m.end():]
    with open(a.html, "w", encoding="utf-8") as f:
        f.write(html)
    print("ARC 갱신: 배트 %d프레임 · 창 %s · 공 %d+%d · 타구 %s km/h %s° · 배트 %s km/h%s" % (
        len(arc["bat"]), arc["batWin"], len(arc["ball"]["pre"]), len(arc["ball"]["post"]),
        arc["ball"]["kmh"], arc["ball"]["deg"], arc["ball"]["batKmh"], " · 회전 갱신" if a.series else ""))


if __name__ == "__main__":
    main()
