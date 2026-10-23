# Jetson Nano 보드 정보 — 2026-10-24 실측

확인 시각: **2026-10-24 01:25:06~01:25:28 KST (Asia/Seoul)**. 사용자에게 받은 주소로 SSH 접속해 수집했다. VS Code 연결은 사용자 확인 사항이며, 이번 조사는 SSH 세션에서 수행했다.

후속 변경: 같은 날 개발 패키지·격리 Rust1.90 설치, 프로젝트/데스크톱 모드 전환·복원 시험과 ROS 비활성화를 적용했다. **이 문서의 표와 JSON은 설치 전 스냅샷**이며 최신 적용 상태는 [개발 환경 설치와 모드 전환](Jetson_Nano_개발환경_설치와_모드전환.md)을 따른다.

현재 보드는 **Jetson Nano 4GB, device tree 기준 B01 구성, 64GB SD 루트 파일시스템**이다. Ubuntu 20.04.6 / L4T R32.6.1을 실행 중이며 CUDA 드라이버에서 Tegra X1 GPU 1개를 인식했다. Rust 도구 준비와 실제 Pico·카메라·USB 오디오 연결 시험은 남아 있다.

## 1. 접속과 식별

| 항목 | 확인값 | 근거 |
| --- | --- | --- |
| 접속 | `ssh jetson@192.168.219.127`, TCP 22 | 실제 인증·명령 실행 성공 |
| 호스트 이름 | `nano` | `hostname` |
| 모델 | `NVIDIA Jetson Nano Developer Kit` | `/proc/device-tree/model` |
| SoC | `nvidia,tegra210`; CUDA 장치명 `NVIDIA Tegra X1` | device tree / CUDA Driver API |
| 모듈·캐리어 구성 | `p3448-0000-b00` + `p3449-0000-b00` | `/proc/device-tree/compatible` |
| DT 소스 이름 | `tegra210-p3448-0000-p3449-0000-b00.dts` | `/proc/device-tree/nvidia,dtsfilename` |
| CPU | ARM Cortex-A57, 4코어/4스레드, aarch64, 최대 1,479MHz | `lscpu`, cpufreq sysfs |
| RAM | 4GB급; OS 인식 `4,156,661,760 bytes` (약 3.87GiB) | `free -b`, `/proc/meminfo` |
| GPU | 1개, Compute Capability **5.3** | `cuInit=0`, `cuDeviceGetCount=0`, device count 1 |
| 네트워크 | `wlan0`, `192.168.219.127/24`, DHCP, 기본 게이트웨이 `192.168.219.1` | `ip -4` |
| Wi-Fi 어댑터 | Realtek RTL8188EUS, USB `0bda:8179`, 드라이버 `r8188eu` | `lsusb`, `lsusb -t` |

모듈·캐리어 리비전은 **실행 중인 device tree의 식별값**이다. 보드 실크·사진·EEPROM을 대조한 물리 식별은 아직 하지 않았다. GPU 메모리 조회값은 시스템 RAM과 같은 값이며 별도의 4GB 전용 VRAM을 뜻하지 않는다.

SSH 호스트 키는 로컬 OpenSSH `known_hosts`와 일치했다. Ed25519 지문은 `SHA256:F9LSPfxsC2zJS1tYvh4YwfDLMITLuVVLOfXHxN6Ga7c`이다. 비밀번호·개인키·환경변수·MAC 주소·하드웨어 고유 일련번호는 수집 파일에 넣지 않았다.

## 2. OS와 저장장치

| 항목 | 확인값 |
| --- | --- |
| OS | Ubuntu **20.04.6 LTS (Focal Fossa)** |
| NVIDIA L4T | **R32.6.1**, `nvidia-l4t-core 32.6.1-20210726122000` |
| 커널 | `4.9.253-tegra`, aarch64, 빌드일 2021-07-26 |
| glibc | **2.31**, Ubuntu package `2.31-0ubuntu9.12` |
| 원본 SD 이미지·JetPack 표기 | **미정**. 원본 URL·파일명·해시·플래시 이력 미확인; `nvidia-jetpack` 메타패키지는 조회 목록에 없음 |
| SD | `/dev/mmcblk0`, `type=SD`, 이름 `SC64G`, 제조월 표기 `12/2021` |
| SD 전체 크기 | `63,864,569,856 bytes` (약 59.48GiB, 64GB급) |
| 루트 | `/dev/mmcblk0p1`, ext4, read/write |
| 루트 사용량 | 사용 `44,225,867,776 bytes`, 여유 `15,735,873,536 bytes` (약 14.66GiB), 사용률 **74%** |
| 메모리 가용량 | 수집 순간 약 **1.87GiB** (`2,011,324,416 bytes`); 실행 부하에 따라 변동 |
| Swap | 약 3.94GiB: `/var/swapfile` 약 2GiB + zram 4개 약 1.94GiB |
| 보드 시간대 | **Europe/Amsterdam**, 당시 UTC+02:00; `NTP=yes`, `NTPSynchronized=yes` |
| 부팅 상태 | SSH 접속 중 정상 응답, 조회 당시 uptime 약 8분. 반복 재부팅·복구 시험은 미수행 |

Ubuntu 사용자 공간과 NVIDIA L4T 버전은 각각 실제 출력값이다. 이 조합만으로 원본 이미지의 배포처나 공식 이미지 여부를 확정하지 않는다. 보드 시각 `2026-10-23 18:25 +02:00`은 한국 시각 `2026-10-24 01:25 +09:00`과 같은 시각이며, 시간대 설정은 변경하지 않았다.

## 3. 개발 도구와 GPU·영상 라이브러리

| 항목 | 확인값·범위 |
| --- | --- |
| Python | **3.8.10** |
| GCC / G++ | **8.4.0** |
| CMake / Make | **3.16.3** / GNU Make **4.2.1** |
| Git / pkg-config | **2.25.1** / **0.29.1** |
| Rust | `rustc`·`cargo`·`rustup`을 `jetson` 계정 PATH와 기본 `~/.cargo/bin`에서 찾지 못함. Rust 빌드·실행은 미시험 |
| Node.js | PATH에서 찾지 못함 |
| Docker CLI | **24.0.5**; 컨테이너 실행은 미시험 |
| CUDA | **10.2**, `nvcc V10.2.300`; toolkit 패키지 `10.2.460-1` |
| CUDA 드라이버 조회 | 초기화 성공, API 버전 `10020`, Tegra X1 / CC 5.3 인식. 커널 연산·추론 성능은 미시험 |
| cuDNN | 패키지 **8.2.1.32-1+cuda10.2** |
| TensorRT | `tensorrt` **8.0.1.6-1+cuda10.2**, `libnvinfer8` **8.0.1-1+cuda10.2**; 추론 미시험 |
| GLib | **2.64.6** (`pkg-config`) |
| GStreamer | **1.16.3** (`gst-launch-1.0`, `pkg-config`) |
| ALSA | **1.2.2** (`pkg-config`) |
| OpenCV | `pkg-config opencv4`와 실제 Python `cv2` import 모두 **4.6.0** |
| OpenCV 빌드 옵션 | CUDA **10.2**, cuDNN **8.2.1**, GPU arch **53**, GStreamer **1.16.2**, FFmpeg·V4L2 지원 표기 |
| NumPy 실제 import | **1.18.5**, `/home/jetson/.local/lib/python3.8/site-packages/numpy` |
| PyTorch / torchvision | 배포 메타데이터 **1.12.0a0+git67ece03** / **0.13.0a0+da3794e**; import·추론은 미시험 |
| TensorFlow | 배포 메타데이터 **2.4.1**; import·추론은 미시험 |
| Jetson 도구 | 배포 메타데이터 `jetson-stats 4.2.3`, `Jetson.GPIO 2.0.17` |

OpenCV의 **빌드 시 GStreamer 1.16.2**와 현재 설치된 **GStreamer 1.16.3**은 구분한다. Debian 목록에는 OpenCV 4.1.1 및 4.2.0 패키지도 있으며, Python 배포 메타데이터에는 NumPy 1.18.5·1.19.5·1.17.4가 공존한다. 이번 세션에서 실제 선택된 `cv2`는 `/usr/lib/python3/dist-packages/cv2`, NumPy는 사용자 `.local` 경로다. 패키지 목록만으로 모든 실행 환경이 같은 라이브러리를 쓴다고 가정하지 않는다.

전체 GStreamer 재검색에서 `nvarguscamerasrc`, `nvvidconv`, `nvv4l2camerasrc`, `nvv4l2h264enc`, `omxh264enc`, `webrtcdsp`, `webrtcechoprobe`, `alsasrc`, `alsasink`가 등록 목록에 나타났다. 이는 실제 촬영·인코딩·AEC 파이프라인 성공을 의미하지 않는다.

## 4. 현재 연결 장치와 접근 권한

| 대상 | 관찰 결과 | 아직 확인하지 않은 것 |
| --- | --- | --- |
| USB | Realtek USB 2.1/3.1 허브와 RTL8188EUS Wi-Fi, root hub | 외부 USB 장치의 부하·장시간 안정성 |
| Pico 2 | `/dev/ttyACM*`, `/dev/ttyUSB*`와 Pico USB ID가 조회 목록에 없음 | 실제 연결·Hello/Status·출력·터치 왕복 |
| 카메라 | `/dev/video*`, `/sys/class/video4linux/*/name` 항목 없음 | CSI 물리 연결·센서 식별·실제 프레임 취득 |
| 오디오 | HDMI 및 내장 `tegra-snd-t210ref-mobile-rt565x`/ADMAIF 장치 열거 | 외부 USB 오디오 인식·녹음·재생·full duplex·AEC |
| I2C | `/dev/i2c-0`~`/dev/i2c-8`, `root:i2c`, `0660` | 버스 스캔·실제 주변장치 접근 |
| GPIO | `/dev/gpiochip0`, `/dev/gpiochip1`, `root:root`, `0600` | 일반 계정의 실제 GPIO 접근 |
| 사용자 그룹 | `sudo`, `audio`, `video`, `i2c`, `gpio`, `plugdev` 등; `dialout`은 목록에 없음 | Pico 연결 후 serial 권한·udev 정책 |
| 프로젝트 systemd unit | `picod`, `controllerd`, `camerad`, `visiond`, `audiod`, `dialogued`, `memoryd` 모두 `LoadState=not-found`, `ActiveState=inactive` | 다른 이름의 서비스나 수동 실행 바이너리 존재 여부 |

장치 노드가 없다는 것은 **이번 조회에서 OS에 열거되지 않았다는 뜻**이다. 물리 미연결·전원·드라이버 중 어느 원인인지 확정하지 않았다. 내장 ALSA 장치가 보인다는 사실도 외부 마이크·스피커의 작동 증거는 아니다.

## 5. 수집 중 확인한 오류와 후속 확인 사항

| 항목 | 실제 출력·관찰 | 다음 확인 범위 |
| --- | --- | --- |
| NVIDIA compositor | `libgstnvcompositor.so` 로딩 경고. `ldd`에서도 **`libgstbadvideo-1.0.so.0 => not found`** | 해당 기능을 사용할 경우 의존성·ABI 조합 확인. 다른 NV 플러그인의 등록 여부와 구분 |
| libudev 개발 메타데이터 | `pkg-config --modversion libudev`에서 `libudev.pc`를 찾지 못함 | Rust serial 도구 빌드에 필요한 개발 패키지 확인. 런타임 libudev 전체 부재로 해석하지 않음 |
| 전력 모드 조회 | `nvpmodel -q`: **MAXN, ID 0**, `fan mode is not set` 경고, EMC 경로 읽기 오류 **13** | 일반 계정에서 조회 가능한 범위가 제한됨. 전체 전력 상태 검증·모드 변경은 미수행 |
| 순간 온도 | sysfs CPU **38°C**, GPU **39°C**, PMIC **50°C** | 짧은 수집 시점 값; 장시간·실부하 열 시험 미수행 |
| tegrastats | 3초 제한으로 표본 2개 수집; 종료 코드 **124** | 명시적 `timeout 3s`에 따른 정상적인 수집 종료. 성능 통과 판정 없음 |
| Rust / native 연결 | Rust 도구 미발견, 실제 프로젝트 빌드 미수행 | 보드에 맞는 toolchain과 native dependency를 고정하고 최소 실행 확인 |
| SD 재현·복구 | 원본 이미지·백업·반복 부팅·복원 증거 없음 | 기존 데이터 보존 필요와 복구 경로 확인 |

이번 작업은 **현황 수집**이다. 패키지 설치·업데이트, 설정 수정, 재부팅, 서비스 등록, 서보/LED 구동, 촬영·녹음·재생은 수행하지 않았다. CUDA Driver API 조회와 OpenCV/NumPy import까지만 실행했다.

## 6. 증거와 재수집

| 파일 | 내용 |
| --- | --- |
| [원본 JSON](board-info/2026-10-24/nano-192.168.219.127.json) | 25개 probe의 실제 명령·stdout·stderr·종료 코드, UTC 수집 시각, SSH 지문, 수집기 SHA-256 |
| [수집 스크립트](../../tools/jetson/collect_board_info.py) | Python 표준 라이브러리만 사용. 각 probe 최대 30초, GStreamer registry는 `/dev/null` 사용 |

JSON에는 Debian 패키지 조회 **2,887행**(설치 상태 `ii` **2,835행**)과 Python 배포 메타데이터 **225개**가 포함된다. 배포 메타데이터의 존재와 실제 import/실행 성공은 별도로 기록했다. shell probe의 종료 코드가 0이어도 내부 명령이 경고·오류를 남길 수 있으므로 stdout·stderr도 함께 확인한다.

수집기 SHA-256: `64c6c55bebe0cfb3b666d365467720b5bdd536e8556b168f9eef489fe568a39f`

원본 JSON SHA-256: `937a0106f6d2d0980f91bf4c04152f565fd254b5ad4b66f56e0dce0c7aa86699`

SSH가 가능한 PC의 Bash에서 저장소 루트를 기준으로 다음처럼 재수집할 수 있다. 인증정보는 명령이나 파일에 넣지 않고 SSH 프롬프트 또는 기존 키를 사용한다. 이번 수집은 Windows Python/Paramiko에서 같은 스크립트를 SSH stdin으로 전달했으며 보드에 스크립트 파일을 저장하지 않았다.

```bash
ssh jetson@192.168.219.127 'python3 -B -' \
  < tools/jetson/collect_board_info.py > nano-board-info.json
```

PowerShell에서는 다음처럼 전달할 수 있다.

```powershell
Get-Content -Raw -Encoding UTF8 .\tools\jetson\collect_board_info.py |
    ssh jetson@192.168.219.127 'python3 -B -' |
    Set-Content -Encoding UTF8 .\nano-board-info.json
```

재수집한 파일의 해시는 출력 인코딩·시각·보드 상태에 따라 달라진다. 기존 날짜의 증거를 덮어쓰지 않고 새 날짜/파일명으로 보관한다.

## 7. 개발 점검표 반영 범위

- **P-01 / B-01:** Nano 현황 식별을 추가했다. 물리 리비전 대조·원본 이미지 적합성 판정은 남아 있다.
- **B-05:** 실제 부팅 중 SSH 응답·용량·네트워크를 확인했다. 반복 재부팅은 하지 않았으므로 전체 완료로 체크하지 않는다.
- **B-06:** 실제 환경 manifest 수집을 완료했다. 누락 의존성·조회 오류도 함께 기록했으며 기능 시험 성공과 구분한다.
- **B-07~B-12 / C:** Rust 실행·운영 전송 절차·영상·음성·복원·Nano–Pico 통합 시험은 미완료다.

관련 문서: [개발 단계 및 점검표](개발_단계_및_점검표.md), [소프트웨어 아키텍처 계획](소프트웨어_아키텍처_계획.md).
