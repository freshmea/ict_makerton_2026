# Jetson Nano · Pico 작업 종합 기록

기준일: **2026-10-24 KST**. 보드 환경 조사부터 개발 환경·장치 권한·펌웨어·대시보드·HDMI 콘솔까지 이번 작업의 최종 상태를 정리한다. 원본 로그와 상세 재현 절차는 각 항목의 링크를 따른다. 담당자나 미측정 성능값은 임의로 지정하지 않는다.

최신 작업과 Git 공유 상태는 [Windows·Jetson GitHub 공유 및 작업 정리](Windows_Jetson_GitHub_공유와_작업정리_2026-10-24.md)를 먼저 확인한다. 아래에는 초기 점검 이력도 포함되어 있다. 이후 스위치 6개·눈 표정 50종, BA-R9·문장 TTS·마이크 증폭, 개별 서보·PCA 진단과 500~2500µs 설정, 두 카메라 관찰 DB·GPT Live가 추가됐다. PCA는 후속 점검에서 0x41·오류 0으로 복구됐지만 보드 저전압·OC 경고의 장기 안정성은 미해결이다.

후속 변경: 새 공유기의 <http://192.168.184.76:8000>에서 대시보드를 다시 활성화했다. 사용자가 스위치 6개·MAX7219 2개 연결을 확인한 뒤 설치 설정의 두 연결 항목을 true로 배포해 미연결 표시와 눈 시험 차단을 해제했다. 눈 시험은 `Matrix done=true, fault=false`, 종료 후 faults 0/OE HIGH를 확인했다. [후속 연결 점검](Jetson_Nano_장치_대시보드.md). 아래 초기 주소와 미연결 판정은 이전 작업 시점의 이력이다.

최종 연결 확인: SW4 IO를 잘못 연결한 물리 16번에서 **12번(GP9)**으로 옮긴 뒤 **스위치 6개 모두 실제 눌림·해제**를 확인했다. 매트릭스 재시험의 ACK Ok·완료 이벤트에 더해 사용자가 **양쪽 패턴 표시와 종료 후 소등**을 확인했다. [스위치 원본](dashboard-check/2026-10-24/switch-connection-check.json), [눈 재시험 원본·관찰](dashboard-check/2026-10-24/matrix-connection-retest.json).

## 현재 운영 구성

| 항목 | 구성·상태 |
| --- | --- |
| Nano | 4GB / B01 계열 DT, Ubuntu 20.04.6, L4T R32.6.1, kernel 4.9.253-tegra |
| 저장소 | PC `D:\repository\ict_makerton_2026`, Nano `/home/jetson/ict_makerton_2026`, GitHub `freshmea/ict_makerton_2026` |
| 접속 | SSH `jetson@192.168.219.127`; 암호는 저장소에 기록하지 않음 |
| 네트워크 | 해당 IP의 실제 인터페이스는 USB RTL8188EUS `wlan0`; 점검 당시 `eth0` DOWN |
| 부팅 | 프로젝트 모드, `multi-user.target`, GUI 중지, ROS 별도 비활성화 |
| Pico | Pico 2 W / RP2350, 통합 `c0de:cafc`, `/dev/pico-device`, Rust/Embassy |
| 카메라 | Camera V2 / IMX219 두 대, CSI, `/dev/video0`·`/dev/video1` |
| 오디오 | C-Media USB `0d8c:0014`, named ALSA `robot_capture`·`robot_playback` |
| 앱 | [FastAPI 대시보드](../../apps/device-dashboard/README.md), Rust 단일 USB 브리지, 별도 미디어 프로세스 |
| 서비스 | `300seconds-dashboard.service` enabled / active, 비root `boarddash` 계정 |
| 접속 주소 | 웹 `http://192.168.219.127:8000`, RTSP `rtsp://192.168.219.127:8554/cam0`·`cam1` |

## 수행한 작업과 실제 검증

| 작업 | 결과·검증 범위 | 상세 문서 |
| --- | --- | --- |
| 보드 정보 수집 | OS/L4T·커널·메모리·패키지·GPU·USB·개발 도구 원본 manifest 기록 | [보드 정보](Jetson_Nano_보드_정보.md) |
| 개발 라이브러리 | native 개발 패키지와 격리 Rust 1.90 설치. Nano Rust host·Tokio AF_UNIX 왕복·C 링크·합성 DSP 확인 | [설치·모드 전환](Jetson_Nano_개발환경_설치와_모드전환.md) |
| GUI·서비스 정리 | 프로젝트/데스크톱 두 모드와 최초 baseline 복원 시험. GPU·카메라·네트워크·SSH 등 필요한 경로 유지 | [설치·모드 전환](Jetson_Nano_개발환경_설치와_모드전환.md) |
| ROS·만료 키 | ROS APT 소스·만료 공개키·cron·서비스를 가역적으로 비활성화. ROS 복원은 GUI 복원과 별도 | [ROS 정책](Jetson_Nano_개발환경_설치와_모드전환.md) |
| 장치 접근 권한 | udev 별칭, robot-device/audio/video/render/dialout 그룹, 서비스 계정, 0660 접근. 비root 실제 open·촬영·오디오 확인 | [디바이스 점검](Jetson_Nano_디바이스_권한과_실물점검.md) |
| 마이크·스피커 | 실제 녹음·재생·48kHz 전이중, 시험음 주파수 검출. 사용자가 정상 청취 확인 | [오디오 실측](Jetson_Nano_디바이스_권한과_실물점검.md) |
| CSI 카메라 | V3/IMX708의 0프레임 실패를 보존. V2 교체 뒤 두 센서 개별·동시 720p 약30fps, 실제 PNG 확인 | [Camera V2 검증](Jetson_Nano_Camera_V2_실물검증.md) |
| Linux 펌웨어 도구 | Rust 크로스/native 빌드, picotool 2.3.1 USB 지원. GNU 8.4 Release formatter 충돌을 Debug 빌드와 파일 정보 smoke 검사로 구분·대응 | [Linux 업데이트](Jetson_Nano_Linux_펌웨어_업데이트.md) |
| 통합 펌웨어 적용 | 사용자 승인 후 기존 4MiB flash 백업, 쓰기·readback/verify·동일 serial의 통합 CDC·Status 확인 | [실제 flash 결과](board-info/2026-10-24/dashboard-pico-flash-result.json) |
| 대시보드 | 상태·실제 영상·마이크 파형/최근 녹음·스피커 유한 재생·Pico 수동 시험·Stop, systemd 자동 시작 확인 | [대시보드 검증](Jetson_Nano_장치_대시보드.md) |
| Request Fault 수정 | 미연결 SW6 입력을 정지로 해석하던 설정 수정. `local_tests_enabled=false`, `test_switch=0`; LED 양손·서보 시험 완료, 사용자 실제 점등·움직임 확인 | [원인·구동 증거](Jetson_Nano_장치_대시보드.md) |
| 네트워크 진단 | 끊김 원인 미확정. NM 절전 비활성, 다음 드라이버 로드용 옵션, 최대16MiB 영구 journal과 baseline 복원 도구 구성 | [Wi-Fi 진단](Jetson_Nano_장치_대시보드.md#wi-fi-연결과-제한된-진단-로그) |
| HDMI 콘솔 | `getty@tty1` enabled/active, 전경 VT1, framebuffer console 바인딩과 실제 `nano login:` 확인. 설정 변경·재부팅 불필요 | [HDMI 점검](Jetson_Nano_HDMI_콘솔_점검.md) |

미사용 커널 전체를 교체·삭제한 것은 아니다. 기존 NVIDIA BSP를 유지하며, 모드 정책에서 선택한 미사용 모듈·데몬·활성화 경로만 관리한다. 기존 상태는 보드의 root 전용 `/var/lib/300seconds/` baseline으로 복원한다.

## 장치별 최종 판정

- **NeoPixel·서보:** 보드의 ACK와 완료 이벤트를 확인했고, 사용자가 실제 LED 점등 및 서보 움직임을 확인했다. 서보 외부 전원은 처음 미연결이었으며 후속 물리 확인으로 보완됐다. 6축 각도·하중 계측이나 NeoPixel 전원 주입 실부하 검증은 별도다.
- **스위치·도트매트릭스:** 초기 미연결 상태 이후 연결 설정을 반영했다. SW4를 GP9로 옮긴 뒤 스위치 6개 눌림·해제를 확인했고, 눈 표정 50종·양쪽 패턴·종료 후 소등을 검증했다. [최종 눈 좌우 확인](dashboard-check/2026-10-24/eye-side-correction/)을 따른다.
- **카메라:** 최종 기본값은 두 대 모두 1280×720 / 30fps, 브라우저 JPEG는 640×360 / 최대15fps다. H.264 하드웨어 인코딩과 공유 RTSP/RTP를 사용한다. 최종 경로 실측은 약30fps이며 10ms 미만의 종단 지연을 달성했다는 뜻은 아니다.
- **오디오:** 실제 입력·출력·전이중과 사용자 청취 확인을 완료했다. 이후 BA-R9 기본음·Typecast 문장 TTS 청취, 마이크 증폭, GPT Live 음성 PCM·자막 저장을 검증했다. Live의 실제 스피커 청취·SW1 물리 시작·10분 연속 대화와 AEC·음성 끼어들기는 별도 검증 대상이다. [연속 관찰·Live 결과](연속_관찰_DB와_GPT_Live.md).
- **HDMI:** 로그인 프롬프트는 화면 메모리에서 확인했다. 점검 당시 `panel_connected=0`, `No EDID`여서 실제 모니터 표시·USB 키보드 입력은 미확인이다. 10분 유휴 화면 절전은 유지한다.

## 실행·정지·복원

Nano SSH 터미널에서 실행한다. 펌웨어 갱신 전에는 대시보드를 중지해 USB 독점을 해제한다. Git pull만으로 `/opt` 실행 배포본이나 Pico flash가 갱신되지는 않는다.

```bash
cd ~/ict_makerton_2026
sudo systemctl status 300seconds-dashboard --no-pager
curl -fsS http://192.168.219.127:8000/api/health
sudo journalctl -u 300seconds-dashboard -n 60 --no-pager

# 대시보드 실행·자동 시작 중지 / 복원
sudo systemctl disable --now 300seconds-dashboard
sudo systemctl enable --now 300seconds-dashboard

# GUI·미사용 서비스 정책 전환
sudo /opt/300seconds/jetson/project-mode.sh
sudo /opt/300seconds/jetson/desktop-mode.sh

# Wi-Fi 정책 조회 / 최초 상태 복원
sudo python3 tools/jetson/dashboard-network.py status
sudo python3 tools/jetson/dashboard-network.py restore
```

ROS 복원은 이번 프로젝트에서 사용하지 않는다. 전체 flash 백업, 원래 시스템 설정 baseline, SSH 자격증명·개인 음성 파일은 Git에 추가하지 않는다. 대시보드는 지정 LAN에서 인증 없이 제공하며 POST는 동일 Origin·CSRF를 검사한다.

## 남은 확인 사항

1. 네트워크 단절 원인과 장시간 동시 부하 안정성. 드라이버 내부 절전 옵션은 다음 로드 이후 실제 반영값을 확인해야 한다.
2. HDMI 모니터 실표시·USB 키보드 로그인. 콘솔에 남은 `soctherm: OC ALARM` 기록의 원인도 별도 진단 대상이며 원인을 확정하지 않았다.
3. 스위치·매트릭스 연결·눈 표정 시험은 후속 작업에서 확인했다. SW1에 의한 GPT Live 시작·종료의 물리 시험은 별도로 남아 있다.
4. 서보 각축 보정·기구 결합·전원 부하, NeoPixel 추가 전원·전원 주입 시험.
5. USB 분리·reset·서비스 종료·lease 만료·복구의 체계적인 실물 장애 회귀와 정지 지연 계측.
6. 기준 SD 백업·다른 카드 복원 부팅, Rust 미디어 binding과 설계된 controller/SHM/PCM 서비스 통합.
7. 두 카메라 관찰 DB와 짧은 GPT Live 세션은 후속 작업에서 검증했다. AEC·장시간 대화·행동 인식 정확도 평가·학습 기억을 활용한 최종 사용자 시나리오는 추가 검증 대상이다.

최신 진행 항목은 [개발 단계 및 점검표](개발_단계_및_점검표.md)를 따른다. 설치 이전 원본 JSON·과거 실패 로그는 당시 증거로 보존하며, 그 안의 과거 장치 ID나 잘못된 BOOTSEL 추론을 현재 상태로 재사용하지 않는다.

## 문서 정리·Git 동기화 전 재검증

이번 정리에서는 Rust 호스트 9개 검사(Windows), 대시보드 회귀 3개와 Linux 업로더 방어 11개 검사(Nano)가 통과했다. 업로더 검사는 장치 flash를 실행하지 않는다. Linux용 Bash 구문도 Nano에서 확인했다. 소스 manifest의 핵심 8개 파일 해시와 로컬 소스가 일치하며 대시보드/tty1 enabled·active, `multi-user.target`, API/Pico/카메라/마이크 health를 재확인했다.

문서가 가리키던 `RUN-20261023-08.md`, 일부 reset 검사 로그와 별도 picod 템플릿은 현재 checkout에 없어 존재하는 증거·실제 서비스로 안내를 교정했다. 과거 결과 파일을 새로 만들어 원본으로 주장하지 않았다. 현재 펌웨어 로직 10개와 공통 protocol 10개 검사를 실행해 별도 기록했다.

- [대시보드 회귀·실제 서비스 상태](board-info/2026-10-24/git-sync-service-verification.log)
- [Linux 업로더 방어·셸 검사](board-info/2026-10-24/git-sync-linux-tests.log)
- [현재 펌웨어 로직 10개 검사](board-info/2026-10-24/git-sync-firmware-tests.log)
- [현재 공통 protocol 10개 검사](board-info/2026-10-24/git-sync-protocol-tests.log)

Git 동기화는 소스·설정·문서·허용된 진단 로그/사진을 대상으로 한다. Nano clone에 먼저 복사했던 변경은 보존용 stash로 보관한 뒤 원격 `main`을 fast-forward한다. 보드 로컬의 생성 `build-info.json`은 별도 백업 후 보존하며, `/opt` 실행 배포본·systemd 설정·Pico flash를 Git 동기화만으로 재설치하지 않는다.
