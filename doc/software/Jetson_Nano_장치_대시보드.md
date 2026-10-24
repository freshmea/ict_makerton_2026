# Jetson Nano FastAPI 장치 대시보드

최신 운영 변경(2026-10-24): 새 공유기에서 사용자 요청으로 이 모니터를 **enabled/active**로 복원했다. 현재 주소는 <http://192.168.184.76:8000>다. 이어서 사용자가 스위치 6개와 도트매트릭스 2개 연결을 확인해 `installation.json`의 두 연결 항목을 true로 반영했다. 실제 브라우저에서 미연결 표시 해제와 눈 시험 버튼 활성화를 확인했으며, 매트릭스 명령 시험은 `done=true, fault=false`, 종료 후 faults 0/OE HIGH다. [이번 시험 원본](dashboard-check/2026-10-24/matrix-connection-check.json). SW6 로컬 선택은 비활성으로 유지하며 스위치 입력은 수신·표시한다. 아래 이전 주소·미연결 시험·Rust 전환은 당시 검증 이력이다.

2026-10-24 KST, 실제 `192.168.219.127` Nano와 USB Pico 2 W에서 구현·배포·점검했다. 소스는 [apps/device-dashboard](../../apps/device-dashboard/README.md)에 있다.

## 후속 스위치·매트릭스 연결 점검

- 설치 설정은 로컬·Nano 저장소·`/opt` 실행본의 SHA-256 일치를 확인했다. 변경 전 실행 설정은 Nano의 `/opt/300seconds/dashboard/backups/20261024T024145Z/installation.json`에 보존했다. 서비스는 enabled/active다.
- 브라우저에서 스위치 6개 상태 표시, 미연결 문구 없음, 눈 시험 버튼 활성화, 콘솔 오류 0개를 확인했다. [화면 점검 JSON](dashboard-check/2026-10-24/connection-browser-qa.json).
- 매트릭스는 API 명령 ACK와 phase 0~19, 최종 `Matrix done=true, fault=false`를 확인했다. 사용자가 재시험에서 **양쪽 패턴 표시와 종료 후 소등**을 확인했다. 단방향 SPI이므로 명령 완료와 사용자 관찰을 구분해 기록한다. [최초 시험 원본](dashboard-check/2026-10-24/matrix-connection-check.json), [새 재시험·사용자 관찰](dashboard-check/2026-10-24/matrix-connection-retest.json).
- **SW1~SW6 모두 눌림·해제를 확인했다.** 처음 미검출이던 SW4는 IO가 물리 16번(GP12/서보 OE)에 꽂혀 있었고, 사용자가 물리 12번(GP9)으로 옮긴 뒤 정상 작동을 확인했다. 같은 Pico 세션의 실제 SW4 Pressed/Released 이벤트와 최근 눌림 3,567ms도 수집했다. [입력 점검 원본](dashboard-check/2026-10-24/switch-connection-check.json)의 최종 `seen_press_mask=63`, `seen_release_mask=63`, `all_six_press_release_verified=true`이며 이전 미확인 결과는 `earlier_capture_summary`에 보존했다. 숫자 63은 누적 검증 비트 합이며 현재 눌림 상태가 아니다.
- 기존 회귀 검사 3개가 모두 통과했다. [검사 로그](dashboard-check/2026-10-24/connection-regression.log), [설정 해시·서비스·API 상태](dashboard-check/2026-10-24/connection-final.json).

`local_tests_enabled=false`, `test_switch=0`을 유지했으므로 SW6 조작으로 로컬 구동 시험을 시작하지 않는다. 여섯 입력의 실시간 감지와 원격 눈 시험은 사용 가능하다.

## 표정 50종과 기기 기준 눈 좌우

대시보드에 **눈으로 전하는 마음**을 추가했다. 드롭다운은 10개 묶음·50종이며 선택은 양쪽 8×8 미리보기만 바꾼다. 2026-10-25부터 기본 눈을 상시 켜 두고 20초마다 버튼·기기 활동·관찰 행동과 키워드로 자동 표정을 선택한다. **표정 시험**은 3/5/10초 우선 표시한 뒤 자동 표정으로 복귀한다. 자동 모드가 꺼져 있으면 종료 후 소등한다. [자동 표정 동작과 검증](눈_LED_상시_표시와_20초_자동_표정.md). 기존 배선·행열 진단과 50종 애니메이션도 유지한다.

후속 사용자 지시에 따라 눈 이름과 데이터를 **기기 본체 기준**으로 통일했다. 기기를 정면에서 볼 때 화면 왼편은 **오른쪽 눈**, 화면 오른편은 **왼쪽 눈**이다. `SetEyes.left/right`와 표정 카탈로그는 이 기기 기준을 사용한다. 첫 교정에서 가까운 모듈을 오른쪽 눈으로 가정했으나, 실제 왼쪽 눈 윙크가 보는 사람의 왼편에 나타났다는 사용자 관찰로 배선 대응을 정정했다. **가까운 첫 모듈=기기 왼쪽 눈, 먼 두 번째=기기 오른쪽 눈**이며, `matrix_mount_frame`은 `near = CW90(logical.left)`, `far = logical.right`로 전송한다. 가까운 모듈의 기존 90도 보정은 유지한다. 정면 미리보기에서 right/left를 화면 왼편/오른편에 배치하며 L/R 진단도 같은 기기 기준이다.

처음 눈을 시작할 때는 **Stop ACK → 서보 비활성 Arm → Eyes ACK** 순서로 적용한다. 자동 표정이 같은 눈 전용 세션을 소유하고 있으면 이후에는 Eyes만 갱신해 소등·재-Arm 없이 전환한다. 자동 모드에서는 수동 표정 종료 후에도 Eyes만 갱신해 복귀한다. Stop은 예약 프레임을 취소하고 진행 중 요청을 선점한다. 사용자의 전체 정지·표정 끄기는 자동 모드도 중지하며 다시 켜기 전까지 재점등하지 않는다. USB 세션 변경 시 과거 재생 작업은 중단하고, 자동 모드가 켜져 있으면 별도의 새 선택·새 세션으로 복구한다. 자동 모드는 서버에서 동작해 브라우저를 닫아도 유지된다.

검증 원본: [카탈로그·배포·회귀·50종 Applied 검사](dashboard-check/2026-10-24/eye-expressions/), [기기 좌우 매핑·빌드·플래시 검증](dashboard-check/2026-10-24/eye-side-correction/). 펌웨어 단위 검사 14개와 Nano 대시보드 검사 16개가 통과했다. 최종 펌웨어에서 50/50 표정 Applied, 자동 소등·Stop을 확인했고 실제 브라우저의 실행·끄기, 50개 선택·키보드 조작, 모바일 가로 넘침 없음, 콘솔 오류 0개를 확인했다. 사용자가 최종 왼쪽 눈 윙크 때 **보는 사람의 오른편 눈이 감김 — 이제 맞음**을 확인했다. [사용자 실물 확인](dashboard-check/2026-10-24/eye-side-correction/user-physical-confirmation.json)은 통신 완료와 별도로 기록한다.

최종 상태에서 **PCA9685 서보 I2C fault bit 1은 남아 있다**. 위 연결 점검 당시의 faults 0은 이전 시험 기록이다. 현재 OE HIGH·서보 출력 차단이며 눈 SPI fault bit 2는 없다. 최종 50종은 `verify_expressions.py --run --matrix-only`로 검사해 오류 원값 1을 보존했다. 서보 오류 때문에 소프트웨어 Bootloader 요청이 거부되어, 사용자가 BOOTSEL로 재연결한 동일 serial Pico를 전체 4MiB 백업 → load → 별도 verify → CDC Status 순서로 복구했다. 서보 보드 전원·SDA/SCL·GND 연결의 별도 점검이 필요하며, 이번 눈 시험 통과를 전체 장치 무오류로 해석하지 않는다.

## 왼눈 반시계 방향 90도 장착 보정 펌웨어

아래는 **화면 기준 ‘왼눈’이라는 이전 명칭**으로 수행한 첫 보정 이력이다. 최신 눈 명칭·데이터 매핑은 위의 기기 기준 절을 따른다. 물리적으로 회전한 모듈을 다시 바꾼 것이 아니다.

2026-10-24 사용자 요청으로 LED 정면 기준 왼쪽 매트릭스를 반시계 방향으로 90도 장착하는 구성을 적용했다. `matrix_mount_frame`이 왼쪽 비트맵을 시계 방향으로 90도 회전하며, 공통 `Matrix::frame`에서 한 번 적용한다. 진단·일반 `SetEyes` 모두 정방향 논리 좌표를 유지하고 오른눈·체인 순서는 바꾸지 않는다. [구현 설명](../../firmware/pico2-device-bench/README.md#기기-기준-눈-좌우와-90도-장착-보정).

- 회전 방향·오른눈 유지·행/열 스캔·blank를 포함한 펌웨어 단위 검사 **14개 통과**. Nano의 RP2350 Release와 네이티브 업데이트 도구 빌드 성공. [검증 요약](dashboard-check/2026-10-24/left-matrix-rotation/validation.json), [빌드 로그](dashboard-check/2026-10-24/left-matrix-rotation/nano-release-build.log).
- 새 UF2: 155,648바이트, SHA-256 `1a0908cb4ee0ac80dfd7771e2b4039b889ebcd832b05bbf8c9858aed6664e55b`. [실제 빌드 manifest](dashboard-check/2026-10-24/left-matrix-rotation/build-info.json).
- 같은 Pico `E679675A69C4039B`의 기존 **4MiB 전체 flash 백업 → load 검증 → 별도 verify → 동일 serial USB Status**를 확인했다. 백업은 Nano의 `tmp/pico-flash/20261024T042353.245798Z-linux/previous-flash.bin`에만 보존한다. [업로드 결과](dashboard-check/2026-10-24/left-matrix-rotation/flash-result.json).
- 업로드 후 대시보드 enabled/active, Pico 재연결과 faults 0, OE HIGH를 확인했다. 새 펌웨어의 눈 시험 진행·완료와 실제 방향 관찰 여부는 [업로드 후 눈 시험](dashboard-check/2026-10-24/left-matrix-rotation/matrix-after-flash.json)에 구분해 기록한다. 후속 사용자 확인: 반시계 방향으로 90도 장착한 왼눈과 오른눈 모두 정방향으로 표시됨. 실제 방향 확인까지 완료했으며 이 관찰은 명령 ACK와 구분해 기록했다.

## 접속과 최종 배포 상태

- 웹: <http://192.168.219.127:8000>
- RTSP/RTP: `rtsp://192.168.219.127:8554/cam0`, `rtsp://192.168.219.127:8554/cam1`
- JSON: `/api/status`, `/api/health`, `/openapi.json`; WebSocket: `/ws/status` (2 Hz)
- `300seconds-dashboard.service`: **enabled / active(running)**. 사용자가 전원을 다시 켠 뒤에도 자동 시작된 것을 SSH에서 확인했다. 최종 안정 경로로 재배포 후 상태도 다시 확인했다.
- 기본 영상은 두 채널 **1280×720 / 30fps**, 브라우저는 **640×360 / 최대 15fps**다.
- GUI는 `multi-user.target` / display-manager inactive, ROS 실행 unit 0개를 유지했다. ROS/DDS RTPS는 사용하지 않으며 요청의 영상 전송은 RTSP/RTP로 구현했다.

마지막 실제 연결 상태·설치는 [최종 상태 JSON](board-info/2026-10-24/dashboard-final-safety-config.json), [배포 파일 해시](board-info/2026-10-24/dashboard-source-manifest.json)를 따른다. 핵심 소스 8개의 Nano clone/실행 배포본/로컬 저장소 바이트 일치를 확인했다.

## 화면과 실제 데이터

![실제 데스크톱 대시보드](dashboard-check/2026-10-24/dashboard-desktop.png)

[모바일 전체 화면](dashboard-check/2026-10-24/dashboard-mobile.png), [카메라 0 원본](dashboard-check/2026-10-24/camera0.jpg), [카메라 1 원본](dashboard-check/2026-10-24/camera1.jpg).

| 장치 | 구현·실제 확인 | 판정의 한계 |
| --- | --- | --- |
| Pico USB | 통합 `c0de:cafc`, `/dev/pico-device`, 세션·상태 수신, Stop ACK `Ok`, OE HIGH, faults 0 | USB 응답을 물리 구동 성공으로 해석하지 않음 |
| 터치 6개 | **미연결**, 사용자 확인. UI에서 미연결 표시, 로컬 시험 비활성 | 미연결 GPIO의 raw `55` 등은 실제 눌림으로 해석하지 않음 |
| NeoPixel | 왼손/오른손 각각 4+4+10=18개, ACK Ok·done=true·fault=false 및 **사용자 실제 LED 점등 확인** | 발광 센서 피드백은 없음 |
| MAX7219 | **미연결**, 사용자 확인. 눈/전체 시험 API와 버튼 비활성 | SPI 출력만으로 설치 여부를 자동 감지하지 않음 |
| PCA9685/서보 | 6채널 유한 순차 시험 ACK Ok·done=true·fault=false, 종료 후 OE HIGH, **사용자 실제 움직임 확인** | 개별 6축 각도·부하 계측은 별도 |
| CSI 0·1 | IMX219 두 대 동시 촬영, H.264 인코딩, 실제 RTSP 디코딩과 MJPEG 표시 | 카메라 방향은 실제 설치 상태를 그대로 표시 |
| 마이크 | C-Media, 48,000 Hz / S16_LE / mono, 파형·RMS·peak, 최근 3초 WAV | 임의 샘플·가상 파형을 사용하지 않음 |
| 스피커 | 실제 `aplay` PCM 재생 종료 코드 0, 유한 3음 시험·최근 녹음 재생 버튼 | 이번 재생의 청감 확인을 대신하지 않음. 이전 장치 점검에서는 사용자가 시험음 청취 확인 |

사용자가 스위치와 매트릭스가 미연결이라고 확인한 뒤 `installation.json`에 반영했다. `local_tests_enabled=false`, `test_switch=0`을 적용해 미연결 SW6 입력을 정지/로컬 시험 선택에 사용하지 않는다. 미연결 터치 이벤트는 UI 이벤트 목록에도 넣지 않는다. 원본 GPIO mask는 진단용 JSON에 남기되 눌림·장치 연결의 증거로 해석하지 않는다. 향후 실제 스위치 연결 시 설치 정보와 극성을 확인한 뒤 기능을 활성화한다.

이전 설정에서는 미연결 GP11 HIGH를 SW6 정지 입력으로 취급해 `RunTest`가 `Fault`로 거부됐다. 설정을 고친 뒤 왼손·오른손·서보 세 시험이 모두 완료됐다. [구동 시험 원본 로그](board-info/2026-10-24/dashboard-actuator-check.log), [전체 JSON](board-info/2026-10-24/dashboard-actuator-results.json)의 각 모듈은 HTTP 200/ACK Ok, `done=true,fault=false`이고 최종 Stop 후 faults 0/OE HIGH다. 사용자가 LED 점등을 확인했고, 서보는 처음에는 외부 V+ 전원 미연결이었으나 후속 답변에서 실제 움직임도 확인했다. 개별 축의 정확한 각도나 부하를 계측한 것은 아니다. 명령 완료 자체가 전원·각도 센서 피드백을 뜻하지 않으며, [핀·전원 문서](Pico2_핀배정_및_전원.md)의 외부 서보 전원과 공통 GND가 필요하다.

## 구성과 라이브러리

```text
브라우저 ─ HTTP/MJPEG + WebSocket ─ FastAPI (Uvicorn 1 worker)
                                   ├─ Rust USB owner ─ COBS/Postcard/CRC ─ Pico
                                   ├─ media_worker ─ Argus CSI 0 / CSI 1
                                   │                ├─ NVMM / H.264 ─ 공유 RTSP
                                   │                └─ 640×360 / JPEG ─ 최신 사진
                                   └─ ALSA capture/playback ─ USB 오디오
```

API와 네이티브 멀티미디어를 별도 프로세스로 분리했다. USB는 Rust만 연다. FastAPI는 검증한 JSON 명령을 loopback UDP `127.0.0.1:37920`으로 전달한다. 세션·lease·Stop 선점·상관된 Status/ACK 확인은 기존 Rust 경계를 유지한다. 구동 명령 재생이나 자동 시험은 없다.

Python 3.8 호환 조합을 전용 `/opt/300seconds/dashboard/venv`에 설치했다: FastAPI 0.115.12, Uvicorn 0.33.0, Pydantic 1.10.24, websockets 13.1. 정확한 의존성은 [freeze](board-info/2026-10-24/dashboard-python-freeze.txt), 검사 결과는 [pip check](board-info/2026-10-24/dashboard-pip-check.txt)에 보존했다. distro `gi`, `numpy`, `psutil` 세 패키지만 venv에 연결하며 `/usr/local`의 전역 TensorFlow 의존성을 가져오지 않는다. FastAPI/RTSP 의존 패키지 외에 GUI나 ROS를 추가 설치하지 않았다.

전용 계정은 `boarddash`(uid 996), 그룹은 audio/video/render/robot-device/dialout이다. `/dev/video*`는 video 0660, USB 오디오는 audio 0660, Pico는 기존 robot-device udev 규칙으로 접근한다. root 웹 서버나 0666 권한을 사용하지 않는다. [서비스·권한 실제 상태](board-info/2026-10-24/dashboard-service-state.txt)를 따른다.

앱/바이너리는 root 소유, runtime은 `/run/300seconds-dashboard` tmpfs, 저장 설정은 `/var/lib/300seconds-dashboard`, 환경은 `/etc/300seconds/dashboard.env`다. 마이크는 최대 약 6초 RAM 링 버퍼, 카메라는 JPEG 두 장과 현재 상태만 보관한다. 네이티브 로그는 256 KiB에서 순환한다. 웹 탭이 숨겨지면 WebSocket과 MJPEG를 닫고 다시 보일 때 연결한다. HTTP POST는 동일 Origin과 랜덤 CSRF 토큰을 검사한다. 인증은 없는 지정 LAN 주소 서비스다.

## 영상 최적화와 실측

최종 경로는 `nvarguscamerasrc → NVMM NV12 → tee`를 사용한다. 각 H.264 갈래는 최신 1프레임 queue와 `nvvidconv → omxh264enc → h264parse`를 거친다. JPEG 갈래는 `nvvidconv(I420 640×360) → videorate(15fps) → jpegenc quality=72`다. RTSP는 appsrc로 인코딩 결과를 공유하며 카메라를 다시 열지 않는다. H.264 약 2.5 Mbps/채널, I-frame 간격 30, SPS/PPS 삽입, `rtph264pay config-interval=1`, RTSP queue 2프레임을 사용한다. 검증 클라이언트는 TCP, `latency=100`으로 설정했다.

이 보드의 GStreamer/NVIDIA 버전 조합에서 `nvv4l2h264enc`는 프레임을 만들지만 `gst_buffer_resize_range` critical 경고가 반복됐다. 같은 조건의 `omxh264enc`는 해당 경고 없이 동작해 최종 기본값으로 선택했다. 전역 GStreamer 교체나 경고 숨김을 하지 않았다. 이는 이 이미지에서의 비교 결과이며 다른 JetPack에도 OMX를 권장한다는 뜻은 아니다. 관련 공식 참고: [NVIDIA 버퍼 풀 설명](https://forums.developer.nvidia.com/t/bufferpool-issue-with-v4l2-elements-jetpack-5-0-2/243916), [GStreamer shared RTSP factory](https://gstreamer.freedesktop.org/documentation/gst-rtsp-server/rtsp-media-factory.html).

최종 재부팅·안정 경로의 [원본 검증 JSON](board-info/2026-10-24/dashboard-final.json)에서:

| 항목 | 카메라 0 | 카메라 1 |
| --- | ---: | ---: |
| 실제 촬영 FPS | 30.01 | 30.00 |
| 실제 인코딩 FPS | 30.00 | 30.00 |
| JPEG 전달 FPS | 15.02 | 15.00 |
| H.264 Mbps | 2.502 | 2.481 |
| RTSP 실제 I420 디코딩 | 90프레임 / 30.24fps | 90프레임 / 30.01fps |

샘플 12개의 전체 보드 CPU 평균은 29.8%, 사용 메모리 평균 1,535 MiB, 최고 센서 온도 50°C였다. 이는 앱 프로세스 전용 메모리나 장시간 벤치마크가 아니다. 원격 개발 등 다른 보드 작업을 포함한다. FPS는 설정값과 분리해 실제 프레임 PTS 및 전달 시각으로 계산한다. 인코더 최신 PTS 차이는 0~수십 ms였지만 실제 유리창 간 영상 지연을 측정한 것은 아니다.

Windows에서도 [cam0](board-info/2026-10-24/dashboard-lan-rtsp0.log), [cam1](board-info/2026-10-24/dashboard-lan-rtsp1.log)을 ffmpeg로 각각 60프레임 디코딩했다. ffmpeg 처리 속도 `speed`는 영상의 실제 FPS와 구분한다.

### 후보 프로필 시험과 제외한 변경

360p30, 720p60, 1080p30, 720p30을 두 센서에서 시험했다. 아래 후보 측정은 **미리보기의 videorate를 NVMM 단계로 옮긴 실험 경로**의 짧은 측정이다. 최종 배포 경로의 성능표로 사용하지 않는다.

| 후보 | RTSP 디코딩 FPS 0 / 1 | 전체 CPU 평균 | 원본 |
| --- | --- | ---: | --- |
| 640×360 / 30 | 30.01 / 30.23 | 24.2% | [JSON](board-info/2026-10-24/dashboard-360p30.json) |
| 1280×720 / 60 | 59.98 / 59.98 | 36.6% | [JSON](board-info/2026-10-24/dashboard-720p60.json) |
| 1920×1080 / 30 | 30.01 / 29.98 | 23.1% | [JSON](board-info/2026-10-24/dashboard-1080p30.json) |
| 1280×720 / 30 | 30.02 / 30.01 | 24.2% | [JSON](board-info/2026-10-24/dashboard-720p30.json) |

이 실험 뒤 최종 반복 검증 중 Nano의 SSH/HTTP/ping 응답이 모두 끊겼다. 개발 PC는 같은 LAN에 남아 있었고, 사용자 전원 재인가로 복구됐다. 이전 부팅의 persistent journal이 없어 원인을 확정할 수 없다. 실험 경로와 단절의 인과관계를 입증하지 않았다. 보수적으로 videorate를 CPU 프레임 변환 뒤의 기존 경로로 되돌렸고 기본값을 720p30으로 유지했다. 기존 경로에서도 네트워크 단절을 다시 관찰했으므로 영상 변경을 원인 또는 해결책으로 단정하지 않는다. 최종 경로에서는 양 채널 재디코딩·오디오·Pico Stop·브라우저 검증을 다시 통과했다. 60fps는 최종 경로에서 실제 표시 FPS와 부하를 확인하며 선택한다.

## Wi-Fi 연결과 제한된 진단 로그

실제 `192.168.219.127` 경로는 유선 eth0가 아니라 USB `0bda:8179` RTL8188EUS / `r8188eu` / wlan0다. 복구 후 eth0는 DOWN, Wi-Fi 링크 72.2 Mbps, WEXT Power Management off, USB `power/control=on`을 확인했다. 드라이버 내부 `rtw_power_mgnt=1`, `rtw_ips_mode=1`, `rtw_enusbss=0`이 별도로 남아 있었다. 재연결 뒤 보드 uptime도 짧아 이전 부팅의 단절 로그를 보존하지 못했다. 드라이버·전원·호스트 정지 중 무엇이 원인인지는 미확정이다.

[dashboard-network.py](../../tools/jetson/dashboard-network.py)는 기존 값을 `/var/lib/300seconds/dashboard-network/baseline.json`에 백업한다. 활성 wlan0 프로필의 NetworkManager powersave를 disable(2)로 명시했고, 다음 드라이버 로드 때 내부 절전을 끄도록 modprobe 옵션을 저장했다. **현재 런타임 내부 값 1을 0으로 바꾼 것은 아니다.** SSH를 유지하려고 드라이버 재로드나 NetworkManager 재시작은 하지 않았다. 값의 의미는 [NetworkManager 공식 문서](https://networkmanager.pages.freedesktop.org/NetworkManager/NetworkManager/nm-settings-nmcli.html)를 따른다.

다음 오류를 조사할 수 있도록 기존 journald의 영구 로그를 최대 16 MiB/파일 4 MiB/2일 보존, runtime 8 MiB로 제한했다. 새 감시 데몬을 추가하지 않았다. 적용 직후 사용량은 4 MiB였다. [실제 설정 결과](board-info/2026-10-24/dashboard-wifi-after.json)를 따른다. 원인 해결 또는 장시간 무중단을 입증한 것은 아니다.

```bash
sudo python3 ~/ict_makerton_2026/tools/jetson/dashboard-network.py status
sudo python3 ~/ict_makerton_2026/tools/jetson/dashboard-network.py restore
# 다시 적용
sudo python3 ~/ict_makerton_2026/tools/jetson/dashboard-network.py apply
```

restore는 원래 Wi-Fi 프로필/모듈 정책을 복원한다. 이전 프로젝트 journald 설정이 없었다면 volatile 기록으로 돌아가며 이미 수집한 파일은 보존한다. 기존 프로젝트 설정 파일이 있었다면 그 내용을 복구한다. 모듈 옵션 변경·복원은 다음 드라이버 로드 때 반영된다.

## Pico 펌웨어 교체와 연결 복구

사용자가 통합 펌웨어 교체를 명시적으로 승인했다. 기존 NeoPixel `c0de:caff`를 picotool USB Reset으로 BOOTSEL에 진입시킨 뒤, 4 MiB 전체 flash를 먼저 백업하고 통합 UF2를 썼다. load/verify/readback, 같은 serial의 `c0de:cafc` 재열거, `pico-device-v1` Status·OE HIGH를 확인했다. [실제 flash 결과](board-info/2026-10-24/dashboard-pico-flash-result.json)를 따른다.

- 보드 chip ID: `E679675A69C4039B`
- UF2 SHA-256: `e4f2352f342465035603079809e4103ef51acfde3f9cd5986199ebc230f9d44f`
- 기존 4 MiB 백업은 Nano의 `~/ict_makerton_2026/tmp/pico-flash/20261023T182828.948488Z-linux/previous-flash.bin`에 보존한다. Git에는 백업 바이너리를 넣지 않았다.
- 백업 SHA-256: `7570ec1f26cb83e2435acf285603f02ecdb46b49bac109eee0927f07a81512b8`
- 최종 Nano 호스트 바이너리 SHA-256: `05f62a8b0461593d34b10019da87ef5add3a6ef681e86278a3e543a696dc5569`

초기 연결에서 신원 응답 CRC 오류 및 HelloReply 유실을 관찰했다. 이전 소유자의 일부 텔레메트리가 남아 있는 초기 수신 상황과 비교했으나, 모든 유실의 물리적 원인을 확정한 것은 아니다. 호스트는 최초 신원 확인 전 **정지 효과를 가진 Hello만 250ms 간격/총 3초 한도로 재시도**하도록 보완했다. 신원 확인 후 구동 명령을 재전송하는 기능은 추가하지 않았다. 신원 응답 유실 회귀 검사를 포함한 Rust 호스트 9개 테스트와 기존 Stop 선점 검사가 통과했다. [빌드·검사 로그](board-info/2026-10-24/dashboard-rust-tests-build.log)를 따른다.

## 검증과 운영

실제 검사에서는 CSRF 누락/외부 Origin 403, 허용하지 않은 명령/프로필 422, 없는 카메라 404를 확인했다. 미연결 매트릭스/전체 시험은 USB 명령 전에 409로 거부한다. 마이크 WAV는 mono 48,000 Hz, 144,000샘플(3초)이었다. 스피커 PCM 종료 코드 0, Pico Stop HTTP 200 / ACK Ok / OE HIGH / running null을 확인했다. 별도 자동 회귀 3개는 오래된 Pico 상태, 이전 카메라 worker의 남은 파일, 미연결 매트릭스 시험 차단을 검사한다. API 응답만으로 모든 장치의 물리 시험을 완료했다고 판정하지 않았다.

Playwright에서 실제 MJPEG 두 장의 naturalWidth 640, 마이크 WAV duration 3초/readyState 4/재생 종료, 미리보기 중지 시 img src 제거와 Pico 텔레메트리 유지, 모바일 390px 가로 넘침 없음, 최종 새 브라우저 세션 콘솔 오류 0개를 확인했다. 미연결 스위치·매트릭스 표시와 관련 시험 차단을 확인했다. [브라우저 QA 기록](board-info/2026-10-24/dashboard-browser-qa.json)을 참고한다.

```bash
sudo systemctl status 300seconds-dashboard
sudo journalctl -u 300seconds-dashboard -n 60 --no-pager
sudo systemctl restart 300seconds-dashboard
sudo systemctl disable --now 300seconds-dashboard # 자동 시작/실행 중지
sudo systemctl enable --now 300seconds-dashboard  # 복원
```

프로필은 화면에서 적용하고 성공 시 저장한다. 실패하면 이전 프로필로 복구한다. Pico USB가 빠졌거나 세션이 종료되면 다시 연결한 뒤 화면의 재시도 버튼을 누른다. 펌웨어 업데이트 전에는 USB 독점을 해제하기 위해 이 서비스를 중지한다. 자동 flash나 자동 구동 시험은 서비스 설치·시작에 포함되지 않는다. 설치·검증 재현 명령과 API 목록은 [앱 README](../../apps/device-dashboard/README.md)를 따른다.
