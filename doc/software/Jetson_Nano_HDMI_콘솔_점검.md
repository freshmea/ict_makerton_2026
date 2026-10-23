# Jetson Nano HDMI 텍스트 로그인 점검

2026-10-24 04:47 KST, `192.168.219.127`의 실제 설정과 가상 콘솔 화면 메모리를 SSH로 확인했다. **이미 서버처럼 텍스트 로그인을 제공하는 설정이다.** 설정 변경과 재부팅은 하지 않았다.

| 항목 | 실제 확인 결과 |
| --- | --- |
| 기본 부팅 대상 | `multi-user.target` |
| GUI | `display-manager.service` inactive |
| 로그인 서비스 | `getty@tty1.service` enabled / active / running |
| 현재 전경 콘솔 | VT1 (`fgconsole` → `1`) |
| 커널 콘솔 | `ttyS0 tty0`, 부팅 인자 `console=tty0 fbcon=map:0` |
| 프레임버퍼 | `fb0: tegra_fb`, framebuffer console bind=`1` |
| 실제 tty1 화면 메모리 | `Ubuntu 20.04.6 LTS nano tty1`, `nano login:` |
| USB 키보드 지원 | `CONFIG_USB_HID=y`, `CONFIG_HID_GENERIC=y`; 점검 당시 USB 키보드는 열거되지 않음 |
| HDMI 감지 | `panel_connected=0`, display controller enable=`0`, EDID=`No EDID` |
| 화면 절전 | `consoleblank=600` (10분) |
| 필수 서비스 | SSH / NetworkManager / nvargus-daemon / dashboard 모두 active |
| 대시보드 health | API ok, Pico / cameras / microphone 모두 true |

HDMI 감지 결과는 점검 당시 모니터가 감지되지 않았다는 뜻이다. 콘솔 설정과 로그인 문구는 확인했지만 **실제 모니터 표시와 USB 키보드 입력은 이번 점검에서 실물 검증하지 않았다.** GUI를 끈 설정만으로 판단하지 않고 framebuffer console 바인딩과 `/dev/vcsa1`의 실제 문구까지 확인했다.

## 사용 방법

1. 전원이 켜진 HDMI 모니터와 USB 키보드를 Nano에 연결하고 모니터 입력을 HDMI로 선택한다.
2. `nano login:`에서 사용자 이름 `jetson`을 입력하고 기존 계정 암호로 로그인한다. 자동 로그인은 설정되어 있지 않다.
3. 10분 이상 유휴 상태로 화면이 꺼졌다면 Shift 등의 키로 깨운다. 다른 가상 콘솔이 선택되어 있다면 `Ctrl+Alt+F1`로 VT1을 선택한다.

화면에 커널 로그가 출력되어 로그인 문구가 위로 밀렸다면 Enter로 로그인 문구를 다시 표시할 수 있다. 이번 화면 메모리에는 부팅 후 약 23~63초의 `soctherm: OC ALARM 0x00000001` 메시지와 약 1159초의 I2C 주소 `0x50` 응답 없음 메시지도 남아 있었다. 이 기록만으로 원인을 확정하지 않으며, 경고를 숨기기 위한 커널 로그 설정 변경은 하지 않았다.

모니터 연결 후에도 신호가 없으면 SSH에서 다음을 확인한다. `panel_connected=0` 또는 `No EDID`가 계속되면 HDMI 케이블·모니터 전원·입력 선택과 연결 감지를 먼저 구분한다.

```bash
systemctl get-default
systemctl status getty@tty1.service --no-pager
sudo fgconsole
cat /sys/class/graphics/fb0/device/panel_connected
sudo cat /sys/kernel/debug/tegradc.0/edid
```

## 모드 전환과 기록

기존 `project-mode.sh`는 `multi-user.target`으로 부팅하고 GUI를 중지한다. getty와 USB HID는 비활성화 대상에 포함하지 않으므로 HDMI 텍스트 로그인을 유지한다. GUI가 필요한 경우에만 기존 `desktop-mode.sh`로 최초 데스크톱 상태를 복원한다. 두 모드의 상세 절차는 [개발환경 설치와 모드 전환](Jetson_Nano_개발환경_설치와_모드전환.md)을 따른다.

원본 증거:

- [서비스·부팅 인자·프레임버퍼 점검](board-info/2026-10-24/hdmi-console-inspect.log)
- [화면 메모리·EDID·절전 설정](board-info/2026-10-24/hdmi-console-confirm.log)
- [HDMI 감지·행 단위 로그인 문구·키보드 지원·health](board-info/2026-10-24/hdmi-console-final.log)
