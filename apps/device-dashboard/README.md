# 300 Seconds 장치 대시보드

최신 운영 변경(2026-10-24): 사용자 요청으로 이 모니터는 **disabled/inactive**다. 아래 자동 시작·화면 결과는 이전 구현 검증 이력이며, 이후 [Rust runtime 전환](../../doc/software/Rust_마이크로아키텍처_실행과_검증.md)을 따른다.

Nano의 실제 장치를 FastAPI로 읽고, 하나의 Rust 브리지를 통해 Pico를 제어한다. ROS는 사용하지 않는다.

- 대시보드: <http://192.168.219.127:8000>
- 상태 JSON: `/api/status`, 2 Hz WebSocket: `/ws/status`
- 카메라 RTSP: `rtsp://192.168.219.127:8554/cam0`, `/cam1`
- 브라우저 영상: `/api/cameras/0/stream.mjpg`, `/api/cameras/1/stream.mjpg`
- 사진: `/api/cameras/{0,1}/snapshot.jpg`
- 마이크: `/api/audio/recent.wav` (최근 3초, 48 kHz S16_LE mono)

## 설치와 운영

대상은 이 프로젝트에서 설정한 Jetson Nano / Python 3.8 / IMX219 두 대다. 기존 udev 규칙, ALSA `robot_capture`·`robot_playback`, Rust 네이티브 브리지, NVIDIA Argus/GStreamer 플러그인이 필요하다. 설치는 펌웨어를 덮어쓰지 않는다.

```bash
cd ~/ict_makerton_2026
# 먼저 Linux 펌웨어/호스트 도구 문서에 따라 네이티브 브리지를 빌드한다.
source ~/.local/share/300seconds/rust/env.sh
cargo +1.90.0 build --release --locked --manifest-path tools/pico-device-bench/Cargo.toml
sudo bash apps/device-dashboard/install.sh
sudo systemctl status 300seconds-dashboard
```

전용 `boarddash` 계정과 audio/video/render/robot-device/dialout 그룹을 사용한다. 앱·바이너리·venv는 root 소유 `/opt/300seconds/dashboard`, 설정은 `/etc/300seconds/dashboard.env`, 선택한 프로필은 `/var/lib/300seconds-dashboard/settings.json`에 둔다. 전역 Python과 TensorFlow를 변경하지 않고 venv에 distro `gi`, `numpy`, `psutil` 세 패키지만 연결한다.

```bash
sudo systemctl restart 300seconds-dashboard
sudo journalctl -u 300seconds-dashboard -n 60 --no-pager
sudo systemctl disable --now 300seconds-dashboard # 자동 시작과 실행 중지
sudo systemctl enable --now 300seconds-dashboard  # 복원
```

서비스는 한 개의 Uvicorn worker만 사용한다. `--reload`나 다중 worker는 USB·CSI 장치 중복 소유를 일으키므로 사용하지 않는다. 기존의 GUI/프로젝트 모드 및 ROS 비활성화 설정은 별도로 유지한다. 서비스 주소 변경 시 환경 파일의 `DASHBOARD_BIND`를 수정하고 재시작한다. DHCP 주소 예약을 권장한다.

## 실제 데이터와 제어 범위

현재 스위치와 도트매트릭스는 **미연결**이다(사용자 확인). `installation.json`의 해당 두 항목을 false로 두며, UI는 미연결 GPIO를 눌림으로 해석하지 않고 매트릭스/전체 시험 API를 거부한다. `pico-config.json`은 `local_tests_enabled=false`, `test_switch=0`으로 SW6 로컬 입력을 사용하지 않는다. 스위치가 없는 상태에서 GP11이 HIGH이면 이전 설정의 정지 조건으로 시험이 Fault 거부될 수 있었고, 이 설정을 바로잡은 뒤 LED 양손과 서보 명령 시험이 모두 완료됐다. 사용자가 실제 LED 점등과 서보 움직임도 확인했다. 서보는 처음에 외부 전원 미연결로 물리 확인을 못 했으나 후속 답변에서 움직임 확인을 받았다. 개별 6축의 각도·부하를 계측한 것은 아니다.

서보 시험 명령 완료와 OE 상태는 외부 V+ 전압·실제 각도 피드백이 아니다. 물리 움직임에는 [배선 문서](../../doc/software/Pico2_핀배정_및_전원.md)의 외부 서보 전원과 공통 GND가 필요하다. 향후 스위치/매트릭스를 연결하면 설치 파일의 실제 연결 여부를 수정하고, 스위치 극성 확인 후에만 SW6 설정을 활성화한다.

- Pico: 통합 `c0de:cafc` 펌웨어, 세션·입력 raw/pressed mask, 터치 6개 눌림·유지·횟수, 모듈 실행 상태, OE, fault bit, 누락 이벤트 수를 표시한다. NeoPixel/MAX7219는 단방향 출력이다. Status/ACK는 실제 발광·각도·전원 측정 결과가 아니다.
- `status`, `stop`, 지정 모듈의 유한 `test`만 허용한다. API가 shell이나 임의 GPIO를 노출하지 않는다. Stop은 별도 UDP 요청으로 기존 요청을 선점할 수 있다. ACK와 시험 완료 이벤트는 구분한다.
- 서비스 시작 시 Hello/Configure/상태 확인만 한다. 모듈 시험, 스피커 재생을 자동 실행하지 않는다. USB 연결이 종료되면 상태를 OFFLINE으로 표시하며, 새 테스트를 재전송하지 않는다. `USB 연결 재시도`는 새 세션을 연다.
- USB는 Rust 프로세스 한 개가 독점한다. 다른 도구로 펌웨어 업데이트/직접 CDC 접근 전 서비스를 중지하고, 작업 후 시작한다. 부팅 때 Pico가 없으면 연결 후 재시도 버튼을 사용한다.
- 마이크는 약 6초짜리 메모리 링 버퍼만 사용한다. `최근 3초 듣기`는 브라우저에서, `녹음 → 스피커`는 Nano의 스피커에서 최근 2초를 재생한다. 스피커 PCM 성공은 실제로 들렸다는 피드백을 대신하지 않는다.
- API 상태가 1.5초 이상 오래되면 Pico/마이크를 정상 연결로 표시하지 않는다. 카메라는 현 worker 세대와 2초 내 촬영·JPEG·H.264 활동을 요구한다. JSON이나 JPEG 파일이 남아 있어도 종료된 worker를 LIVE로 표시하지 않는다.

## 영상 경로

`media_worker.py`가 CSI를 한 번씩 열고 NVMM에서 두 갈래로 나눈다. H.264는 NVIDIA 하드웨어 인코더와 공유 RTSP 서버로, 브라우저는 CPU JPEG 640×360/최대 15fps로 보낸다. 브라우저는 RTSP를 직접 재생하지 않는다. 여러 RTSP 클라이언트도 CSI 소스를 추가로 열지 않는다. 웹 탭이 숨겨지거나 미리보기를 정지하면 브라우저의 WebSocket/MJPEG 연결을 줄이며, 보드의 RTSP 촬영은 계속한다.

기본 `720p30`, `360p30`, `720p60`, `1080p30`을 `profiles.json`에서 관리한다. 변경은 두 카메라 파이프라인을 함께 재시작한다. 적용 실패 시 이전 프로필로 되돌리며 저장은 성공 후에만 한다. 런타임 로그(256 KiB 순환), 최신 JPEG 두 장과 상태 JSON은 `/run/300seconds-dashboard` tmpfs에 두어 SD에 계속 영상을 쓰지 않는다.

NVMM H.264 입력 queue는 최신 1프레임, RTSP queue는 2프레임으로 제한한다. 인코더 SPS/PPS와 1초 I-frame 간격, RTSP payloader `config-interval=1`, 공유 factory를 사용한다. 클라이언트에서는 TCP + 100 ms 버퍼를 기준으로 확인했다.

```bash
gst-launch-1.0 rtspsrc location=rtsp://192.168.219.127:8554/cam0 protocols=tcp latency=100 \
  ! rtph264depay ! h264parse ! avdec_h264 ! autovideosink sync=false
```

검증 스크립트는 실제 H.264를 I420으로 디코딩하며 설정 FPS와 수신 FPS를 구분한다. 자세한 실측 결과 및 사진은 [구현·검증 기록](../../doc/software/Jetson_Nano_장치_대시보드.md)을 참고한다.

## 검증 재현

```bash
cd /opt/300seconds/dashboard/app
/opt/300seconds/dashboard/venv/bin/python -B -m unittest -v test_hardware
/opt/300seconds/dashboard/venv/bin/python -B verify_live.py --output /tmp/dashboard-verification.json
# 선택적으로 유한 시험음 재생과 Stop ACK까지 확인:
/opt/300seconds/dashboard/venv/bin/python -B verify_live.py --speaker-stop --output /tmp/dashboard-audio-stop.json
```

POST는 `/api/session`의 메모리 CSRF 토큰을 `X-CSRF-Token` 헤더에 보내야 한다. 외부 Origin은 거부한다. 인증 기능은 없으며 현재 지정된 LAN 주소에서만 제공한다. 포트는 HTTP 8000, RTSP 8554, USB IPC는 loopback 37920이다. OpenAPI JSON은 `/openapi.json`에 있다.

`static/fonts`의 Pretendard는 SIL OFL 1.1이며 라이선스를 함께 보관했다. 런타임 화면은 외부 CDN을 요구하지 않는다.
