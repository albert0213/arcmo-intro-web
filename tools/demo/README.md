# 데모 리포트 (arcmo.xyz/demo) 만들기

공개 데모는 실제 스윙 한 개(150fps, 2026-09-10 야외 타격장)를 가명으로 바꿔 올린 것입니다.
화면은 분석 엔진 저장소(`AIMotionAnalysisProject`)의 `web/arcmo_web.html` 을 그대로 쓰고,
데이터는 이 폴더(`demo/`)의 정적 파일에서 읽습니다.

| 파일 | 내용 |
|---|---|
| `demo/index.html` | `arcmo_web.html` + 데모 shim (`build_demo.py` 가 만듦) |
| `demo/summary.json` · `series.json` · `pose.json` · `video.mp4` | 분석 결과 (시선 움직임 · 어깨-골반 회전 · 체중이동 · 손 궤적) |
| `demo/bat.json` | 프레임별 배트(그립·끝) — `tracking.json` 에서 |
| `demo/benchmarks.json` | 기준점(상위 n%) 표 — 리포트 분포 숫자만 |
| `demo/swing-overlay.mp4` | 소개 페이지 첫 화면 영상 (이 도구들이 건드리지 않음) |

## 순서

1. **분석 결과 준비** — 분석PC/클라우드에서 최신 코드로 다시 계산한 리포트 폴더
   (`summary.json`, `series.json`, `pose.json`(wrists 포함), `video.mp4`).
2. **배트·공 추적** (영상이 바뀔 때만)
   ```bash
   python tools/demo/track_demo.py --video <video.mp4> --pose <pose.json>
   ```
   `tracking.json` 이 바뀝니다. 블러가 심한 77~79 프레임의 배트 끝은 확대 이미지를 보고 직접 찍은 값입니다(`MANUAL_HEAD`).
3. **데모 리포트**
   ```bash
   python tools/demo/build_demo.py --web <arcmo_web.html> --src <리포트 폴더> --bench <benchmarks_table.json> --out demo
   ```
4. **소개 페이지 첫 화면** (`index.html` 의 `const ARC`)
   ```bash
   python tools/demo/update_landing.py --series demo/series.json
   ```

## 배트 스피드 · 타구 속도 · 발사각 (데모 전용 어림값)

- 축척은 공·배트가 만나는 깊이에서 잽니다: 임팩트 전 공이 떨어지는 가속도를 중력에 맞춘 값(0.314 cm/px)과
  공 지름 7.3cm(약 22.5px)로 잰 값(0.324 cm/px)의 평균 0.319 cm/px.
  키 181cm 로 잰 몸 위치 축척은 0.40 cm/px 로, 몸이 카메라에서 더 멀어 값이 큽니다.
- 배트 스피드는 배트 끝에서 약 15cm(스윗스팟) 지점의 최고 속도(임팩트 직전), 타구 속도·발사각은 임팩트 뒤 9프레임의 직선 맞춤입니다.
- 모두 화면 평면(2D) 기준이라 카메라 쪽·반대쪽 성분은 빠집니다.
