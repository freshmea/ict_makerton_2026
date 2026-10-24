# 300 Seconds 장치 대시보드

추가 구현·Nano 배포: **두 카메라 10초 간격 연속 관찰·SQLite 저장·기간/키워드 조회·CSV/JSONL 내보내기·검토 라벨**, **SW1/대시보드 GPT Live 10분 대화** 검증실. [설계·API·실연결 검증·운영 비용](../../doc/software/연속_관찰_DB와_GPT_Live.md). 실제 연속 저장, 한국어 Live 인사 음성 PCM·자막·정상 종료를 확인했다. GPT‑4.1 mini와 GPT Live 모두 유료 API다.

최신 운영 변경(2026-10-24): 새 공유기에서 사용자 요청으로 모니터를 다시 **enabled/active**로 전환하고 `DASHBOARD_BIND=192.168.184.76`을 적용했다. 웹과 상태 API에서 Pico·카메라 두 대·마이크 연결을 확인했다. 이전 [Rust runtime 전환](../../doc/software/Rust_마이크로아키텍처_실행과_검증.md)의 모니터 중지는 당시 기록이다. 저장소 루트의 [enable-dashboard.sh](../../enable-dashboard.sh)·[disable-dashboard.sh](../../disable-dashboard.sh)로 현재 IP 반영과 실행·부팅 자동 시작을 함께 켜거나 끈다.

Nano의 실제 장치를 FastAPI로 읽고, 하나의 Rust 브리지를 통해 Pico를 제어한다. ROS는 사용하지 않는다.

- 대시보드: <http://192.168.184.76:8000> (공유기·DHCP 변경 시 활성화 스크립트가 현재 IP를 반영)
- 상태 JSON: `/api/status`, 2 Hz WebSocket: `/ws/status`
- 카메라 RTSP: `rtsp://192.168.184.76:8554/cam0`, `/cam1`
- 브라우저 영상: `/api/cameras/0/stream.mjpg`, `/api/cameras/1/stream.mjpg`
- 사진: `/api/cameras/{0,1}/snapshot.jpg`
- 마이크: `/api/audio/recent.wav` (최근 3초, 48 kHz S16_LE mono)

## 설치와 운영

책상 학습 관찰: `JEV · 20장 분석`은 얼굴용·학습 공간용 카메라에서 1초 간격으로 각 10장, 총 20장을 모아 한 번 분석한다. 기본 배치는 카메라 1(SENSOR 0)이 얼굴, 카메라 2(SENSOR 1)가 손·책상·학습 자료이며 화면에서 서로 바꿀 수 있다. `GPT · 10장 분석`은 선택한 한 대의 사진 10장을 사용한다. 15개 행동, 집중·시선 0~10, 자리비움을 표시한다. 사용자 설정에 따라 자리 상태 판단 불가는 자리비움으로 처리하고 근거가 부족한 점수는 보류한다. API 키는 별도 `300seconds-observer` 서비스에만 전달한다. 현재 GPT 로컬 5회 테스트를 마쳤고 JEV 무료 한도는 대기 중이다. [실제 결과·비용·키·검증 범위](../../doc/software/10프레임_학습행동_분석과_대시보드.md)를 참고한다.

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

2026-10-24 사용자가 **스위치 6개와 MAX7219 도트매트릭스 2개 배선 완료**를 확인했다. `installation.json`의 `touch_inputs_connected`, `matrix_connected`를 true로 바꾸고 Nano 저장소와 `/opt/300seconds/dashboard/app`에 반영했다. 화면의 미연결 표시를 해제하고, 스위치 입력 해석과 매트릭스/전체 시험 API를 활성화했다. 브라우저에서 여섯 입력의 RELEASED 표시와 눈 시험 버튼 활성화를 확인했다. 눈 재시험은 Pico의 ACK Ok·`Matrix done=true, fault=false`, 종료 후 faults 0/OE HIGH이며, 사용자가 **양쪽 시험 패턴 표시와 종료 후 소등**을 확인했다. [매트릭스 재시험 결과](../../doc/software/dashboard-check/2026-10-24/matrix-connection-retest.json). SPI 단방향 출력의 명령 완료와 사용자 발광 관찰은 별도로 기록한다.

`pico-config.json`은 `local_tests_enabled=false`, `test_switch=0`을 유지한다. 여섯 스위치의 입력 수신·표시는 동작하며, SW6을 눌렀다 놓아 서보 등을 시작하는 로컬 선택 기능만 비활성이다. 이전 미연결 GP11 HIGH를 정지 조건으로 해석하던 Request Fault 수정 이력과 LED·서보 실물 확인은 [기존 검증 기록](../../doc/software/Jetson_Nano_장치_대시보드.md)에 보존한다.

후속 실제 입력 수집과 이벤트에서 **SW1~SW6 모두 눌림·해제**를 확인했다. SW4는 IO선이 물리 16번(GP12/서보 OE)에 꽂혀 있었으며, 사용자가 **물리 12번(GP9)**으로 옮긴 뒤 정상 작동을 확인했다. 보드에서도 SW4 Pressed/Released와 최근 눌림 3,567ms를 확인했다. 누적 검증 mask는 press/release 모두 63이다. [스위치 입력 원본](../../doc/software/dashboard-check/2026-10-24/switch-connection-check.json), [브라우저 점검](../../doc/software/dashboard-check/2026-10-24/connection-browser-qa.json).

실물 확인한 배선: **가까운 첫 MAX7219가 기기의 왼쪽 눈**, 먼 두 번째 모듈이 오른쪽 눈이다. 가까운 왼쪽 눈의 반시계 방향 90도 장착과 시계 방향 90도 출력 보정은 유지한다. 호스트 표정 데이터는 기기 기준 정방향이며, 정면 미리보기의 화면 오른편에 왼쪽 눈을 표시한다. [구현·업로드 기록](../../doc/software/Jetson_Nano_장치_대시보드.md).

서보 시험 명령 완료와 OE 상태는 외부 V+ 전압·실제 각도 피드백이 아니다. 물리 움직임에는 [배선 문서](../../doc/software/Pico2_핀배정_및_전원.md)의 외부 서보 전원과 공통 GND가 필요하다. SW6 로컬 선택을 사용하려면 스위치 극성과 동작 모드를 확인한 뒤 별도로 활성화한다.

- Pico: 통합 `c0de:cafc` 펌웨어, 세션·입력 raw/pressed mask, 터치 6개 눌림·유지·횟수, 모듈 실행 상태, OE, fault bit, 누락 이벤트 수를 표시한다. NeoPixel/MAX7219는 단방향 출력이다. Status/ACK는 실제 발광·각도·전원 측정 결과가 아니다.
- `status`, `stop`, 지정 모듈의 유한 `test`만 허용한다. API가 shell이나 임의 GPIO를 노출하지 않는다. Stop은 별도 UDP 요청으로 기존 요청을 선점할 수 있다. ACK와 시험 완료 이벤트는 구분한다.
- 서비스 시작 시 Hello/Configure/상태 확인만 한다. 모듈 시험, 스피커 재생을 자동 실행하지 않는다. USB 연결이 종료되면 상태를 OFFLINE으로 표시하며, 새 테스트를 재전송하지 않는다. `USB 연결 재시도`는 새 세션을 연다.
- USB는 Rust 프로세스 한 개가 독점한다. 다른 도구로 펌웨어 업데이트/직접 CDC 접근 전 서비스를 중지하고, 작업 후 시작한다. 부팅 때 Pico가 없으면 연결 후 재시도 버튼을 사용한다.
- 마이크는 약 6초짜리 메모리 링 버퍼만 사용한다. `최근 3초 듣기`는 브라우저에서, `녹음 → 스피커`는 Nano의 스피커에서 최근 2초를 재생한다. 스피커 PCM 성공은 실제로 들렸다는 피드백을 대신하지 않는다.
- API 상태가 1.5초 이상 오래되면 Pico/마이크를 정상 연결로 표시하지 않는다. 카메라는 현 worker 세대와 2초 내 촬영·JPEG·H.264 활동을 요구한다. JSON이나 JPEG 파일이 남아 있어도 종료된 worker를 LIVE로 표시하지 않는다.

## 서보별 각도 슬라이더

Pico 영역의 **각도를 직접 골라 보세요**에서 서보 1~6번(CH0~CH5)의 0~180° 목표를 각각 선택한다. **서보 제어 시작** 후 슬라이더에서 손을 놓거나 해당 **이동** 버튼을 누르면 선택한 채널만 보낸다. 페이지 진입·제어 시작·USB 재연결만으로 모터를 움직이지 않는다. 이동 중에는 다음 요청을 쌓지 않으며, 완료 후 다음 각도를 적용한다.

- 현재 대시보드 프로필의 펄스 범위는 **500~2500µs**이고 보간 속도는 최대 **30°/s**다. 2026-10-24 사용자가 0~180° 명령에서 실제 회전폭이 약 90°라고 보고하여, 이전 [무부하 확대 시험](../../doc/software/test-results/2026-10-23/RUN-20261023-02.md)의 범위를 복원했다. 매핑은 0°=500µs, 90°=1500µs, 180°=2500µs이며 주파수는 기존 약 50Hz를 유지한다. 0~180°는 명령 각도이며 실제 각도 측정이나 축별 기구 보정을 뜻하지 않는다. 기본 90° 표시는 미리보기이고, **마지막 완료 명령**도 위치 센서 피드백이 아니다.
- **서보 출력 정지**는 진행 중 명령과 예약 전송을 취소하고 Pico의 공용 Stop을 요청한다. 눈·조명도 함께 정지한다. 탭 숨김·창 닫힘·연결 만료는 정지를 요청하고 재연결 후 자동으로 재개하지 않는다. 브라우저 lease는 2초이며 Stop 응답이 없으면 USB 브리지 keepalive를 중단한다. 출력 차단 후에는 서보가 하중을 유지하지 못할 수 있다.
- 새 펌웨어의 개별 제어 capability, 최신 USB 세션 및 PCA9685 정상 상태가 필요하다. **서보 보드 연결 재확인**은 출력을 차단한 상태에서 드라이버만 재초기화한다. 오류를 무시하거나 모터를 자동 시험하지 않는다.

API는 `GET /api/pico/servos`, `POST /api/pico/servos/session`(`action`: enable/keepalive/stop/probe), `POST /api/pico/servo`(`control_id`, `servo`: 1~6, `degrees`: 정수 0~180)이다. enable의 `control_id`로 keepalive와 이동 요청을 보낸다. POST는 기존 CSRF·동일 Origin 검사를 적용한다. 임의 핀·펄스 폭·설정 파일을 브라우저에서 받지 않는다.

2026-10-24 BOOTSEL 연결 후 4MiB 기존 flash를 백업하고 새 펌웨어 쓰기·읽기 검증과 통합 CDC 상태 확인을 완료했다. 초기 슬라이더 검증에서는 PCA9685 I2C fault가 남아 실제 회전을 수행하지 않았다. 해당 시점의 화면·개별 요청·정지 동작과 실기 제한은 [서보 슬라이더 검증 기록](../../doc/software/dashboard-check/2026-10-24/servo-sliders/README.md)에 보존한다.

후속 재부팅 진단에서 펌웨어·브리지·대시보드에 `servo_driver` 상세 상태를 추가해 배포했다. `0x40/0x41` MODE 레지스터 응답을 구분하고 정확히 한 주소만 유효할 때 선택한다. 초기에는 두 주소 모두 ACK가 없었지만, 사용자의 PCA VCC 약 3.3V 측정 후 재조회에서 **0x41 응답·초기화 성공·fault 0**으로 복구됐다. 사용자는 측정 중 배선을 바꾸지 않았다고 보고했으며 이전 무응답의 직접 원인은 확정하지 못했다. [상세 진단·백업·업로드·회귀 검사](../../doc/software/dashboard-check/2026-10-24/servo-i2c/README.md).

500~2500µs는 `pico-config.json`에 저장하고 Nano 저장소·설치본에 반영했다. 대시보드 재시작 뒤 Pico `DeviceConfig`와 서보 API 모두 같은 값을 읽는 것을 확인했다. 일반 펌웨어의 초기 기본값은 그대로이며 대시보드 브리지가 연결할 때 이 프로필을 Configure한다. [펄스 범위 복원·배포·실기 설정 확인](../../doc/software/dashboard-check/2026-10-24/servo-pwm-range/README.md).

```bash
cd ~/ict_makerton_2026/apps/device-dashboard
/opt/300seconds/dashboard/venv/bin/python -B -m unittest -v test_servo_controls
```

## 눈 표정 · 감정 50종

Pico 장치 영역의 **눈으로 전하는 마음**에서 표정 드롭다운을 선택한다. 기본·시선, 기쁨, 애정, 자신감, 슬픔, 놀람·긴장, 분노·불만, 피곤·휴식, 장난·호기심, 기호·응원의 **10개 묶음에 5종씩, 총 50종**이다. 50개 기본 눈 비트맵 쌍은 서로 다르며 깜빡임·하트 두근거림·눈물·소용돌이 등 짧은 동작을 포함한다.

- 선택·이전/다음 버튼은 미리보기만 바꾼다. **표정 시험**을 누르면 양쪽 실제 눈에 3/5/10초 표시한 뒤 자동으로 끈다. 기본값은 5초다.
- **왼쪽 눈·오른쪽 눈은 기기 본체 기준**이다. 기기를 정면에서 보는 미리보기의 화면 왼편에는 **오른쪽 눈**, 화면 오른편에는 **왼쪽 눈**을 표시한다. 윙크와 좌우 보기 이름도 같은 기준이다.
- 논리 `left`는 기기 왼쪽 눈(가까운/첫 번째 모듈), `right`는 기기 오른쪽 눈(먼/두 번째 모듈)이다. 실물 관찰로 확인한 이 배선에 맞춰 펌웨어가 공통 SPI 출력에서 한 번만 매핑한다. 기존에 90도 돌려 장착한 **가까운 모듈의 회전 보정은 유지**하며, 호스트에서 중복으로 데이터를 바꾸거나 회전하지 않는다.
- **표정 끄기**와 **Pico 전체 정지**는 예약된 애니메이션을 취소하고 Stop ACK를 확인한다. 새 표정은 Stop → 서보 비활성 Arm → Eyes 순서로 보낸다. USB가 끊기거나 세션이 바뀌면 이전 표정을 재생하지 않는다. 화면을 여는 것만으로 출력을 켜지 않는다.
- 기존 **배선·행열 검사**는 기기 기준 왼쪽 눈 L → 오른쪽 눈 R, 행/열/체커 패턴을 확인하는 별도 진단으로 유지한다.

API는 `GET /api/pico/expressions`(50종과 프레임), `POST /api/pico/expression`(`preset_id`, `seconds`)이다. POST는 기존 세션 CSRF 헤더가 필요하며 등록된 ID와 3/5/10초만 수락한다. 임의 GPIO·서보 명령은 이 API에 노출하지 않는다. 강도는 기존 눈 시험과 같은 1이다.

```bash
cd ~/ict_makerton_2026/apps/device-dashboard
/opt/300seconds/dashboard/venv/bin/python -B -m unittest -v test_eye_expressions test_hardware
# 카탈로그 조회만 수행 (구동 없음)
python3 verify_expressions.py --host http://192.168.184.76:8000
# 명시적 50종 실제 시험·자동 소등·Stop 검사
python3 verify_expressions.py --host http://192.168.184.76:8000 --run --output /tmp/eyes-verification.json
```

화면·API·실제 Applied 이벤트 검증은 [표정 검증 원본](../../doc/software/dashboard-check/2026-10-24/eye-expressions/live-verification.json), [기기 눈 좌우 교정](../../doc/software/dashboard-check/2026-10-24/eye-side-correction/)을 따른다. 최종 펌웨어에서 50/50 Applied, 자동 소등·Stop, 브라우저 실행·끄기를 확인했다. 사용자가 왼쪽 눈 윙크 때 **보는 사람의 오른편 눈이 감김 — 이제 맞음**을 확인했다. 실제 관찰과 명령 완료는 별도로 기록한다.

현재 별도 제한: **PCA9685 서보 보드 I2C fault bit 1**은 남아 있다. OE는 HIGH이며 눈 SPI의 fault bit 2는 없다. 최종 50종 검사는 `--run --matrix-only`로 수행해 서보 오류를 그대로 기록하면서 눈 경로를 검증했다. 전체 장치 무오류 판정은 아니다. 소프트웨어 Bootloader 요청도 이 오류로 거부되어 사용자의 BOOTSEL 재연결 후 전체 flash 백업·검증을 거쳐 업로드했다. 서보 전원·SDA/SCL·GND 연결은 별도로 점검해야 한다.

## 마이크 증폭과 녹음

2026-10-24 **Britz BA-R9**의 기본음·Typecast 서연 TTS를 실제 재생하고 사용자가 둘 다 청취했음을 확인했다. BA-R9는 USB 전원과 3.5mm 오디오 입력을 사용하며, **볼륨 다이얼 위 별도 전원 버튼**을 켜야 한다. 첫 시험에서는 PCM 재생 성공에도 소리가 없었고, 사용자가 전원 버튼을 켠 뒤 해결됐다. 이어진 작은 음량 개선 요청으로 기존 C-Media 어댑터와 `robot_playback` 경로의 USB 출력을 **92%(-3 dB), 음소거 해제**로 올려 저장했다. [첫 시험 결과·설정 백업](../../doc/software/dashboard-check/2026-10-24/ba-r9/README.md).

### 문장 입력 → 보드 TTS 재생

오디오 패널의 **문장을 목소리로**에 문장을 입력하고 **TTS 재생**을 누른다. 입력한 문장만 Typecast `ssfm-v30` / 서연으로 합성해 BA-R9에서 재생한다. 페이지 진입이나 Enter 줄바꿈으로 합성하지 않는다. 최대 240자(UTF-16 기준)이며 **재생 완료 후 고정 대기 없이 다음 문장을 요청**할 수 있다. 2026-10-24 연속 생성 요청에 따라 로컬 분당 2회 제한, HTTP 0/5xx 뒤 60초 및 인증/429 뒤 1시간 고정 차단을 제거했다. Typecast Free 공식 동시 요청 한도 2개와 로컬 분당 2회는 다른 개념이다. 단일 스피커 재생은 한 번에 하나씩 처리한다. 기존 24시간 500자·30일 12,000자 및 매 요청의 계정 크레딧 검사·유료 플랜 차단은 유지한다. 별도 요금제나 자동 fallback을 활성화하지 않는다.

`POST /api/audio/tts`는 `{"text":"안녕하세요."}`만 수락하며 기존 세션 CSRF·동일 Origin 검사가 적용된다. 대시보드의 스피커 잠금은 시험음·녹음 재생·TTS 합성부터 재생 종료까지 공유하므로 재생 중 추가 합성 비용이 발생하지 않는다. 합성 중/재생 중/완료/오류를 표시하고 입력 문장은 남겨 둔다. 재생 음성은 마이크 증폭 설정과 독립적으로 **최대 +6 dB**를 적용하되 전체 파형의 피크를 **-1 dBFS** 아래로 제한한다. 원본 44.1 kHz WAV는 로컬에서 48 kHz mono S16으로 변환한다.

합성은 별도 `300seconds-tts.service`가 담당한다. 키는 root0600 `/etc/300seconds/tts.env`에서 이 서비스에만 전달하고, 대시보드·브라우저에는 전달하지 않는다. 기존 Rust 합성기의 계정/문자 ledger를 재사용한다. Unix socket은 `/run/300seconds-tts/tts.sock`, 허용 peer는 root/boarddash이며 오디오 장치는 대시보드만 연다. 임시 WAV는 성공·실패·시간 초과 때 제거하고 문장이나 음성 파일을 영구 저장하지 않는다.

[실제 버튼 재생·사용자 음량 확인·모바일 화면·배포 검증](../../doc/software/dashboard-check/2026-10-24/tts-input/README.md). 이전 자산 캐시로 이벤트 연결이 누락되지 않도록 앱 스크립트·스타일 URL에 버전을 적용하고 HTML 및 해당 자산을 재검증한다.

통신 오류는 DNS·서버 연결·응답 시간 초과·TLS·연결 끊김을 구분해 표시하고 합성 서비스 로그에 분류만 남긴다. 실패 후 자동 재전송은 하지 않지만 새 명시적 요청을 로컬 타이머로 막지 않는다. 실제 Typecast 429·인증·크레딧 오류는 그대로 실패로 처리하며 제공자의 제한을 우회하지 않는다. 예전 장부의 `cooldown_until`은 새 코드에서 0으로 이행하고 기존 문자 사용 이력은 보존한다.

[고정 대기 제거·11.048초 동안 실제 API 3회 연속 성공](../../doc/software/dashboard-check/2026-10-24/tts-continuous/README.md)을 확인했다. 이 정책은 첫 입력창 추가 기록의 분당2회·실패 후 대기 설명을 대체한다.

```bash
# typecast-sample WAV [TEXT]를 지원하는 갱신된 런타임 바이너리를 먼저 배포한다.
sudo bash apps/device-dashboard/install-tts.sh
sudo systemctl status 300seconds-tts.service
cd apps/device-dashboard
/opt/300seconds/dashboard/venv/bin/python -B -m unittest -v test_audio test_tts_worker
```

오디오 패널의 **녹음 증폭**은 기본 **+12 dB**(진폭 약 4배), 조절 범위는 **0~30 dB**다. `증폭 적용`을 누르면 `/api/audio/settings`에 `{"gain_db": 12}`를 POST하고, `/var/lib/300seconds-dashboard/audio-settings.json`에 저장해 재시작 후에도 유지한다. 경로는 `DASHBOARD_AUDIO_SETTINGS`로 변경할 수 있으며 카메라 프로필 파일과 분리된다. 기존 CSRF·동일 Origin 검사가 적용된다.

상단 MICROPHONE은 기존 순간 RMS 대신 **최근 3초의 녹음 출력 피크**를 표시한다. 오디오 패널에는 같은 구간의 평균(RMS), 원본 평균·피크, 설정 증폭량과 실제 적용량을 함께 표시한다. 파형은 같은 증폭량을 적용한 최신 100 ms다. `/api/status`의 `audio.rms_dbfs`·`peak_dbfs`는 증폭 후 최근 3초 값이며, 원본은 `raw_rms_dbfs`·`raw_peak_dbfs`로 제공한다. `gain_db`, `applied_gain_db`, `limiter_active`, `peak_ceiling_dbfs`, `meter_seconds`도 제공한다.

최근 3초 WAV와 보드 스피커의 2초 녹음 재생 모두 실제 PCM에 증폭을 적용한다. 각 녹음 구간 전체에 하나의 선형 배율을 사용하고, 가장 큰 샘플이 **-1 dBFS**를 넘을 경우 전체 배율을 줄여 피크를 보호한다. 파형을 잘라내거나 int16 범위를 넘겨 뒤집히는 방식이 아니다. 2초 재생과 3초 미터는 검사 구간이 달라 실제 적용량이 다를 수 있다. `0 dB`에서도 피크 보호는 유지된다.

이는 고정 증폭과 피크 보호이며 무음을 최대 음량으로 끌어올리는 자동 정규화는 아니다. 배경 소음도 증폭된다. 큰 충격음 하나가 들어오면 해당 구간 전체의 증폭량이 줄어들 수 있다. 메모리 버퍼는 원본으로 유지하고 내보낼 때 한 번만 처리하므로 중복 증폭되지 않는다. 저장 형식은 기존 48 kHz / S16_LE / mono WAV를 유지한다. MP3 여부 자체가 음량 기준을 정하지는 않는다.

```bash
cd ~/ict_makerton_2026/apps/device-dashboard
/opt/300seconds/dashboard/venv/bin/python -B -m unittest -v test_audio test_hardware test_eye_expressions test_observer_api
```

## 영상 경로

`media_worker.py`가 CSI를 한 번씩 열고 NVMM에서 두 갈래로 나눈다. H.264는 NVIDIA 하드웨어 인코더와 공유 RTSP 서버로, 브라우저는 CPU JPEG 640×360/최대 15fps로 보낸다. 브라우저는 RTSP를 직접 재생하지 않는다. 여러 RTSP 클라이언트도 CSI 소스를 추가로 열지 않는다. 웹 탭이 숨겨지거나 미리보기를 정지하면 브라우저의 WebSocket/MJPEG 연결을 줄이며, 보드의 RTSP 촬영은 계속한다.

기본 `720p30`, `360p30`, `720p60`, `1080p30`을 `profiles.json`에서 관리한다. 변경은 두 카메라 파이프라인을 함께 재시작한다. 적용 실패 시 이전 프로필로 되돌리며 저장은 성공 후에만 한다. 런타임 로그(256 KiB 순환), 최신 JPEG 두 장과 상태 JSON은 `/run/300seconds-dashboard` tmpfs에 두어 SD에 계속 영상을 쓰지 않는다.

NVMM H.264 입력 queue는 최신 1프레임, RTSP queue는 2프레임으로 제한한다. 인코더 SPS/PPS와 1초 I-frame 간격, RTSP payloader `config-interval=1`, 공유 factory를 사용한다. 클라이언트에서는 TCP + 100 ms 버퍼를 기준으로 확인했다.

```bash
gst-launch-1.0 rtspsrc location=rtsp://192.168.184.76:8554/cam0 protocols=tcp latency=100 \
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
