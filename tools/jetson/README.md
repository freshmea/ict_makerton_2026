# Jetson 보드 관리 도구

대상 실측 구성: Jetson Nano4GB / Ubuntu20.04.6 / L4T R32.6.1. 실제 적용·복구 시험과 제한은 [개발 환경 설치와 모드 전환](../../doc/software/Jetson_Nano_개발환경_설치와_모드전환.md)에 기록한다.

| 파일 | 용도 |
| --- | --- |
| `collect_board_info.py` | 설치·장치 구동 없이 하드웨어/환경 JSON 수집 |
| `dashboard-network.py status/apply/restore` | RTL8188EUS Wi-Fi 정책 백업·복원과 최대 16MiB 영구 진단 로그. 드라이버 옵션은 다음 로드 때 반영 |
| `install-project-deps.sh` | Ubuntu 개발 패키지·격리 Rust1.90·Pico udev/dialout 준비 |
| `project-mode.sh` / `desktop-mode.sh` | headless 정책 적용 / 최초 GUI·서비스·모듈 정책 복원 |
| `jetson-mode.sh status` | 현재 상태 JSON |
| `disable-ros.sh` | ROS 소스·만료 키·cron·service 별도 비활성화 |
| `restore-ros.sh` | 명시적으로 요청할 때만 ROS 원본 복구. 예전 만료 키와 매분 cron도 복구하므로 이번 프로젝트에서는 실행하지 않음 |
| `validate-environment.sh` / `validate-native.c` | 네이티브 링크·합성 DSP 확인. 실제 오디오/카메라는 열지 않음 |
| `native-uds-smoke.rs` | 기존 host crate의 example로 실행한 실제 Tokio AF_UNIX 왕복 소스 |
| `configure-device-access.sh` / `device_access.py` | Pico/audio/camera 그룹·서비스 계정·udev·named ALSA PCM 설정 |
| `check-device-access.sh` / `probe-device-access.py` | 비root systemd transient 프로세스에서 실제 장치 open 확인 |
| `check-usb-audio.py` | 짧은 실물 녹음·시험음 재생·full duplex와 주파수 확인 |
| `check-csi-camera.py` | sensor-id0/1의 실제 프레임 취득. 수신 프레임이 없으면 실패 |
| `verify-csi-cameras.py` | 비root에서 각 카메라와 두 카메라 동시 90프레임 수신·PTS 측정·실제 RGB PNG 저장 |

보드에는 `/opt/300seconds/jetson`에 root 소유로 설치했다. `.sh`는 `0755`, Python 엔진은 root 소유이며 상태 폴더는 `/var/lib/300seconds/` 아래 root 전용이다. 일반 사용자가 수정 가능한 스크립트 경로를 서비스나 root 자동 시작 경로로 등록하지 않는다.

```bash
sudo /opt/300seconds/jetson/project-mode.sh
sudo /opt/300seconds/jetson/desktop-mode.sh
sudo /opt/300seconds/jetson/jetson-mode.sh status
source "$HOME/.local/share/300seconds/rust/env.sh"
```

새 보드에 복사할 때는 해당 보드의 서비스·컨테이너·장치 현황을 먼저 조사한다. ROS 비활성화 도구는 이번 보드의 `ros_init.service`·기존 ROS 공개키·root/jetson cron 구성을 대상으로 한다. 다른 사용자의 ROS 환경 전체를 자동 탐지하는 범용 제거기는 아니다. 보드별 baseline을 다른 보드에 복사해 적용하지 않는다.

저장소에서 재배포할 때는 셸 파일의 LF 줄바꿈과 실행 권한을 유지한다.

```bash
sudo install -d -m 0755 /opt/300seconds/jetson
sudo install -o root -g root -m 0755 tools/jetson/*.sh tools/jetson/*.py /opt/300seconds/jetson/
sudo install -o root -g root -m 0644 tools/jetson/*.c tools/jetson/*.rs /opt/300seconds/jetson/
```

프로젝트 서비스/펌웨어를 자동 시작하거나 ROS 패키지·기존 작업 디렉터리를 삭제하는 도구는 아니다.

실제 연결 장치의 최신 결과는 [디바이스 권한·실물 점검](../../doc/software/Jetson_Nano_디바이스_권한과_실물점검.md)을 따른다. IMX708 취득 실패 후 Camera V2로 교체했고, [IMX219 두 개의 비root 개별·동시 촬영과 실제 PNG](../../doc/software/Jetson_Nano_Camera_V2_실물검증.md)를 확인했다. `camera` 권한 probe와 실제 프레임 수신 시험을 구분한다.

Nano clone의 Linux 펌웨어 빌드/업로드는 저장소 루트의 `firmware/setup-linux.sh`, `build-pico-device.sh`, `flash-pico.sh`를 사용한다. RP2350 BOOTSEL `2e8a:000f`도 `robot-device:0660`을 적용한다. [설정·업데이트·검증 범위](../../doc/software/Jetson_Nano_Linux_펌웨어_업데이트.md)를 확인한다.

실시간 장치 모니터는 [FastAPI 대시보드](../../apps/device-dashboard/README.md)를 사용한다. 해당 앱의 별도 `install.sh`는 사용자 요청에 따라 `300seconds-dashboard.service`를 자동 시작으로 등록한다. [실제 영상·오디오·LED/서보 확인과 네트워크 제한](../../doc/software/Jetson_Nano_장치_대시보드.md)을 참고한다.

프로젝트 모드에서도 HDMI 텍스트 로그인은 유지된다. 2026-10-24에는 `getty@tty1` enabled/active, VT1 화면의 `nano login:`, framebuffer console 연결을 확인했다. [HDMI 콘솔 점검과 실제 화면 검증 범위](../../doc/software/Jetson_Nano_HDMI_콘솔_점검.md)를 참고한다.
