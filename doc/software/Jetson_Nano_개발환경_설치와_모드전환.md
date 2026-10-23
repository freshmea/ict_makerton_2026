# Jetson Nano 개발 환경 설치와 프로젝트/데스크톱 모드

작업일: **2026-10-24, 한국 시간**. 대상: `jetson@192.168.219.127` / 호스트 `nano`, Nano 4GB, Ubuntu 20.04.6, L4T R32.6.1.

**보드에 실제 적용했다. 최종 상태는 프로젝트 모드이며 ROS도 별도로 비활성화했다.** 필요한 개발 패키지와 격리된 Rust 1.90을 설치하고, 프로젝트 → 데스크톱 복원 → 프로젝트 전환을 실제 시험했다. 이전 [01:25 초기 보드 조사](Jetson_Nano_보드_정보.md)와 이번 설치 이후 상태를 구분한다.

후속 실물 결과: [디바이스 권한·실물 점검](Jetson_Nano_디바이스_권한과_실물점검.md)에서 USB 오디오·Pico 인식/접근을 확인하고 별도 계정·udev 규칙을 추가했다. IMX708 두 카메라는 취득 실패로 기록했다. 아래의 미시험 표기는 이 문서의 환경 설치 단계 당시 범위이며 후속 결과와 구분한다.

## 1. 지금 사용하는 명령

SSH/VS Code 원격 터미널에서 실행한다. 스크립트는 보드의 **`/opt/300seconds/jetson`**에 root 소유로 설치돼 있다.

```bash
# GUI와 불필요한 서비스를 끄는 프로젝트 모드
sudo /opt/300seconds/jetson/project-mode.sh

# 처음 저장한 GUI/서비스/커널 모듈 정책으로 복원
sudo /opt/300seconds/jetson/desktop-mode.sh

# 현재 모드, 서비스, 메모리 확인
sudo /opt/300seconds/jetson/jetson-mode.sh status
```

전환은 즉시 적용되며 다음 부팅의 기본 target도 바뀐다. GUI를 끄면 로컬 그래픽 로그인 세션과 그 안의 앱은 종료된다. 데스크톱 복원은 디스플레이 매니저와 서비스 설정을 복구하며, 종료된 앱·작업 중이던 GUI 세션을 재생성하지 않는다. SSH와 VS Code Remote-SSH 경로는 유지한다.

ROS 비활성화는 두 GUI 모드와 **독립적**이다. 데스크톱으로 전환해도 ROS 저장소·키·예약 실행이 돌아오지 않는다.

```bash
# ROS 비활성화 정책 재적용 — 현재 이미 적용돼 있음
sudo /opt/300seconds/jetson/disable-ros.sh

# 프로젝트 전용 Rust를 현재 터미널에 적용
source "$HOME/.local/share/300seconds/rust/env.sh"
rustc --version
cargo --version
```

`dialout` 그룹을 추가했으므로 기존 SSH/VS Code 세션은 다시 연결해야 새 그룹 권한을 받는다. 펌웨어가 USB `c0de:cafc`로 열거되면 udev 규칙이 `/dev/pico-device` 별칭과 `dialout` 접근을 부여한다. 아직 실제 Pico 열거·포트 접근을 시험한 결과는 아니다.

## 2. 설치한 라이브러리와 도구

Rust/Tokio, USB serial, GStreamer/ALSA, TLS, SQLite를 사용하는 [현재 아키텍처](소프트웨어_아키텍처_계획.md)를 기준으로 선정했다. 기존 CUDA·cuDNN·TensorRT·OpenCV·GLib/GStreamer 런타임과 실행 커널은 교체하지 않았다.

| 구분 | 실제 처리·버전 |
| --- | --- |
| Rust | 프로젝트 전용 **1.90.0**, `aarch64-unknown-linux-gnu`; Cargo 1.90.0, rustfmt·Clippy·rust-analyzer |
| Rust 위치 | `/home/jetson/.local/share/300seconds/rust/{cargo,rustup}`; 쉘 시작 파일·기존 전역 Rust 설정은 수정하지 않음 |
| TLS 개발 | 신규 `libssl-dev 1.1.1f-1ubuntu2.24` |
| USB/udev 개발 | 신규 `libudev-dev 245.4-4ubuntu3.24` |
| bindgen용 Clang | 신규 `libclang-dev 1:10.0-50~exp1`, libclang/LLVM10 및 의존 패키지 |
| 셸 검사 | 신규 `shellcheck 0.7.0-2build2` |
| 기존 패키지 확인 | build-essential·CMake·pkg-config·Git·curl·CA 인증서, GLib/GStreamer/base 개발 파일, ALSA·SQLite 개발 파일 |
| 기존 런타임 확인 | GStreamer base/good/bad/alsa·tools, alsa-utils, v4l-utils |
| 장치 접근 준비 | `jetson`에 `dialout` 추가, `/etc/udev/rules.d/90-pico-device.rules` 설치·udev 규칙 재로드 |

Debian 패키지는 **10개 신규 설치**, 기존 패키지 업그레이드·제거는 **0개**였다. libclang/LLVM 의존성을 포함한 APT 표시 추가 디스크 사용량은 약 332MB이며 Rust 도구·빌드 캐시는 별도다. 설치 스크립트는 전체 upgrade/autoremove를 하지 않는다.

재설치/점검:

```bash
sudo /opt/300seconds/jetson/install-project-deps.sh jetson
/opt/300seconds/jetson/validate-environment.sh
```

설치기는 누락된 패키지만 선정하고 시뮬레이션에서 제거 또는 보호한 NVIDIA/미디어 기반 패키지 변경이 나타나면 중단한다. Ubuntu 의존성 설치에는 별도의 Ubuntu Focal 공식 소스 목록을 사용하고 기존 vendor source/key 파일은 바꾸지 않는다. 이 별도 목록은 `/var/lib/300seconds/dependencies/ubuntu-focal.list`에 필요할 때 생성된다. 이번 최초 설치는 보드의 기존 소스에서 Ubuntu 패키지를 받아 성공했고, 이후 ROS 저장소를 별도로 비활성화했다.

## 3. 프로젝트 모드에서 줄인 항목

| 범위 | 정책과 판단 근거 |
| --- | --- |
| GUI | 기본 target을 `multi-user.target`으로 변경, GDM 중지. Weston·GUI 저메모리 경고도 중지 |
| 인쇄 | cups service/socket/path·cups-browsed 중지. 프린터 미사용 |
| Bluetooth | bluetooth·blueman-mechanism 중지. Bluetooth 어댑터가 조회되지 않음 |
| 자동 장치 검색 | avahi service/socket 중지. 현재는 IP로 SSH 연결 |
| GPS·모뎀 | gpsd service/socket·ModemManager 중지. 프로젝트에 미사용하며 serial 장치 자동 탐색도 줄임 |
| 데스크톱 보조 | colord·PackageKit·switcheroo-control·geoclue·spice-vdagentd 중지/시작 조건 제한 |
| 보고·원격 GUI | whoopsie·kerneloops·TeamViewer 중지. SSH 연결은 별도로 유지 |
| 컨테이너 | Docker service/socket·containerd 중지. 적용 전 **기존 컨테이너 0개** 확인 |
| Snap | snapd service/socket·snap-repair timer/service 중지. 설치된 snap service 없음 확인. snap 패키지·mount 이미지는 유지 |
| PackageKit APT 알림 | `/etc/apt/apt.conf.d/20packagekit`의 알림 훅을 프로젝트 모드에서 비움. 꺼진 PackageKit에 대한 DBus 호출 시간 초과를 방지하고 데스크톱 복원 시 원문 복구 |

실제 관리 대상은 **29개 unit**이다. 없는 unit은 건너뛰고 alias는 canonical unit으로 합쳤다. 설치 서비스처럼 static인 unit에는 무조건 enable/disable을 적용하지 않는다. 원래 enabled인 항목은 disable하고, 관리 대상에는 별도 drop-in의 `ConditionPathExists=!/var/lib/300seconds/jetson-mode/project.enabled`를 적용해 DBus/socket/의존성에 의한 재시작도 제한한다.

**유지한 기반:** SSH, NetworkManager·Wi-Fi·DNS, DBus·udev·로그·시각 동기화·cron, 방화벽/보안 업데이트, NVIDIA GPU·전력 제어·Argus 카메라, ALSA, 팬 제어 `automagic-fan`, zram/swap 및 진단용 jtop 등. NVIDIA AI Lab의 일반 최적화 예제와 달리 이 프로젝트에는 카메라가 필요하므로 `nvargus-daemon`은 유지했다.

### 실행 커널과 모듈

- 설치·부팅 가능한 커널은 **`4.9.253-tegra` 하나**였다. `/boot/Image`, DTB, initramfs, 실행 커널·커널 패키지는 변경하지 않았다.
- 미사용 Bluetooth PAN **`bnep`**만 강제 옵션 없이 unload했다. 프로젝트 모드에서는 별도 modprobe 파일로 자동/명시 로드를 제한하고 데스크톱 복원 시 원래 파일·로드 상태를 복구한다.
- `/etc/modules-load.d/cups-filters.conf`의 `lp`·`ppdev`·`parport_pc` 자동 로드 요청은 프로젝트 모드에서 비우고 복원 시 원문을 되돌린다. 이 보드에서 별도 로드된 프린터 모듈은 확인되지 않았다.
- `nvgpu`, Wi-Fi의 `r8188eu`·`cfg80211`, USB/저장장치·ALSA·카메라·zram·네트워크 필터링 모듈은 유지했다. 커널을 제거하는 방식의 경량화는 하지 않았다.

## 4. ROS 비활성화

사용자는 **이번 프로젝트에서 ROS를 사용하지 않는다**고 명시했다. 조사에서 ROS 프로세스는 없었지만, `jetson` crontab에는 다음 작업이 매분 실행되도록 남아 있었다.

```cron
* * * * * bash -ic "ros2 launch digitalphoto digitalphoto.launch.py" > /home/jetson/cront.log
```

이를 주석 처리하고 다음을 적용했다.

| 대상 | 실제 적용 |
| --- | --- |
| ROS APT | `/etc/apt/sources.list.d/ros2.list`의 ROS 저장소 행 주석 처리 |
| 만료된 키 | `C1CF6E31E6BADE8868B172B4F42ED6FBAB17C654`를 담은 `/usr/share/keyrings/ros-archive-keyring.gpg`를 활성 경로에서 제거. 원본 공개키 전체는 root 전용 baseline에 보관 |
| `ros_init.service` | 원래 disabled/inactive였음. stop 상태 유지 및 별도 ROS 금지 조건 추가 |
| 사용자 예약 작업 | ROS 행만 주석 처리. 다른 cron 설정·작업과 cron 서비스는 유지 |
| 셸 초기화 | `.bashrc`의 ROS/colcon 관련 행은 이미 주석 처리돼 있어 추가 수정하지 않음 |
| 실행 프로세스 | 비활성화 후 일치하는 ROS 프로세스 **0개** |
| 보존 | `/opt/ros` 약 84MB, 기존 `colcon_ws`·소스·설정은 보존. 삭제/패키지 purge는 하지 않음 |

유효한 Canonical `ubuntu-pro-ros.gpg`는 이번 만료 키와 다른 키이며 수정하지 않았다. 최종 `apt-get update`는 ROS 서명 오류·PackageKit timeout 없이 **종료 코드 0**으로 끝났다.

ROS 복구는 GUI 복원과 별개인 `restore-ros.sh`에만 있다. 이 명령은 **예전 만료 키와 매분 예약 작업까지 원래대로 되돌리므로 이번 프로젝트에서는 실행하지 않는다.** 향후 ROS가 필요한 별도 작업에서 원본 복구가 필요할 때만 사용하고, APT를 쓰기 전 키를 갱신해야 한다. 비활성화 후 사용자가 바꾼 설정/cron이 있으면 복구 스크립트는 덮어쓰지 않고 수동 대조를 요구한다.

## 5. 복원 데이터와 실패 시 처리

| 위치 | 내용 |
| --- | --- |
| `/var/lib/300seconds/jetson-mode/baseline.json` | 최초 기본 target, 선택 unit의 enabled/active 상태, 관련 systemd 심볼릭 링크, 모듈/프린터/PackageKit/override 파일 원문 |
| `/var/lib/300seconds/jetson-mode/last-result.json` | 최근 모드·시각·메모리·bnep unload 결과 |
| `/var/lib/300seconds/ros-disabled/baseline.json` | ROS 저장소 행·공개키·cron·service의 원래 상태 |
| `/var/log/300seconds/` | 패키지 설치·APT 계획·설치 전후 package manifest·전환 로그 |

상태 폴더는 root 전용 `0700`이다. 반복 project 호출은 최초 baseline을 덮어쓰지 않는다. 복원은 관리 대상의 원래 파일/링크만 처리하며 `/etc/systemd/system` 전체를 교체하지 않는다. 원래 disabled/static이던 서비스를 일괄 enable하지 않는다. Docker 컨테이너나 snap service가 이후 추가되면 프로젝트 모드 진입 시 검사를 거쳐 해당 workload를 임의 중단하지 않도록 거부한다.

프로젝트 모드 적용 중 오류가 나면 baseline 복원을 시도하고, 복원 실패는 종료 오류로 보고한다. 최초 적용 때는 5분 임시 복원 타이머를 걸고 새 SSH 연결로 생존 확인 후 취소했다. 이 타이머는 최종 상태에서 남아 있지 않으며 프로젝트 프로세스를 자동 시작하는 서비스도 등록하지 않았다.

보드에 SSH로 들어갈 수 있다면 `sudo /opt/300seconds/jetson/desktop-mode.sh`로 복구한다. 네트워크 외부 문제가 있으면 로컬 텍스트 콘솔에서 같은 명령을 실행한다. baseline 파일은 지우지 않는다. 모드 복원은 **GUI/서비스/모듈 정책 복원**이며 새로 설치한 라이브러리, `dialout` 권한, udev 규칙, 별도의 ROS 정책을 제거하지 않는다.

## 6. 실제 검증 결과와 한계

| 검증 | 결과 |
| --- | --- |
| Bash 문법·ShellCheck | 보드에서 전체 셸 파일 통과 |
| 네이티브 라이브러리 | C 프로그램을 보드에서 컴파일·링크·실행. GLib/GStreamer·ALSA·libudev·OpenSSL·SQLite 로드/초기화 성공 |
| GStreamer | NVIDIA camera/convert/H.264 및 ALSA/WebRTC element 등록 확인. 합성 오디오 → WebRTC DSP(`echo-cancel=false`) → fakesink가 EOS 도달 |
| Rust 호스트 | 현재 저장소 파일의 별도 스냅샷에서 **host 테스트 8개 통과**, CLI debug 빌드 성공 |
| Tokio IPC | 보드의 실제 aarch64 Rust 프로그램에서 AF_UNIX pair 왕복 성공 |
| 데스크톱 복원 | **29 unit의 UnitFileState, 32 설정 파일, 28 심볼릭 링크**가 원래 값과 일치. 원래 active인 unit의 복귀와 bnep 재로드 확인 |
| 동적 서비스 | 복원 중 geoclue는 GUI 요청으로 inactive→active가 됨. 부팅/활성화 정책은 원래대로이며 GUI의 런타임 DBus 활성화는 가능 |
| 최종 프로젝트 모드 | 기본 `multi-user.target`, 관리 unit **29개 전부 inactive**, bnep 미로드, SSH·네트워크·팬·Argus 유지 |
| 반복 실행 | project 호출과 ROS disable 재호출 성공, 원본 baseline 유지 |
| 최종 APT | 업데이트 성공, ROS 서명 오류·PackageKit 알림 timeout 없음 |

첫 전환 전후 `free -b`의 사용 RAM은 **1,847.8MiB → 1,203.4MiB**, 약 **644.4MiB 감소**했다. 캐시·다른 프로세스·측정 시점이 달라지는 단발 비교이며 장시간 성능 보장이 아니다.

실제 Pico 연결/USB 권한·카메라 촬영·마이크 녹음/스피커 재생·실제 AEC·AI 추론·전원 부하·재부팅 후 동작은 이번 범위에서 시험하지 않았다. C 링크 시험은 향후 모든 Rust 미디어 binding의 버전 조합 검증을 대신하지 않는다. `nvcompositor`의 기존 `libgstbadvideo-1.0.so.0` 의존성 문제는 남아 있으며 다른 ABI 파일을 가짜 링크로 대체하지 않았다. 현재 검증 경로는 compositor를 쓰지 않는다.

호스트 CLI 산출물은 검증용 debug 빌드이며 보드 캐시의 별도 소스 스냅샷에 있다. 실제 USB bridge 또는 최종 `picod` 서비스를 설치·자동 시작한 결과가 아니다.

## 7. 저장소 파일과 증거

| 파일 | 용도 |
| --- | --- |
| [셸·Python·네이티브 확인 소스](../../tools/jetson/) | 설치기, project/desktop/ROS wrapper, 상태 복원 엔진, C·Tokio 확인 코드 |
| [설치 로그](board-info/2026-10-24/dependency-install.log) | 최초 패키지·Rust 설치의 실제 출력과 당시 ROS 서명 경고 |
| [ROS 비활성화 로그](board-info/2026-10-24/ros-disable.log) | cron/소스/키 처리 및 중간 APT 결과. 중간 PackageKit timeout은 최종 전환에서 해소 |
| [최종 적용·APT 로그](board-info/2026-10-24/mode-final-apply.log) | 재적용·반복 실행·최종 APT 성공 |
| [복원 대조 JSON](board-info/2026-10-24/mode-restore-verification.json) | 각 unit/파일/링크 원래값과 복원값, 오류 0개 |
| [최종 상태 JSON](board-info/2026-10-24/setup-final-state.json) | 적용 후 unit·ROS·모듈·패키지 차이, root baseline 사본, 배포 스크립트 해시 |
| [네이티브 확인 로그](board-info/2026-10-24/native-validation.log) | C 링크·합성 DSP·Rust 테스트·Tokio UDS·CLI 빌드 출력 |
| [검증 소스 manifest](board-info/2026-10-24/native-source-manifest.json) | 보드에 복사한 현재 소스의 SHA-256과 경로 |

CLI debug 파일 SHA-256: `bd4900c6b1e181740145834b0e80e71a0462e83fde20f5c8f4fb69a710c1c863`.

검증 소스는 `/home/jetson/.cache/300seconds-validation-20261024/source`에 필요한 crate만 복사한 것이다. Git clone이나 보드 전체 저장소 동기화로 표시하지 않는다. 비밀번호·개인키는 저장하지 않았다.

기술 기준: [NVIDIA의 GUI target 전환 안내](https://www.jetson-ai-lab.com/tutorials/ram-optimization/), [systemctl 동작](https://www.freedesktop.org/software/systemd/man/latest/systemctl.html), [modprobe 설정](https://man7.org/linux/man-pages/man5/modprobe.d.5.html), [Rust 공식 설치 안내](https://rust-lang.org/tools/install/). 실제 적용 범위·판정은 위 보드 출력과 현재 프로젝트 설계를 따른다.
