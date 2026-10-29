# Wi-Fi 주소 자동 선택 적용

2026-10-29 한국 시간. Jetson Nano `192.168.219.127`에 실제 적용했다.

- `wifi_network.py`가 연결된 무선 인터페이스의 IPv4를 선택하고 Uvicorn과 카메라 작업자에 전달한다. 유선·루프백·링크 로컬 주소는 선택하지 않는다. Wi-Fi가 여러 개면 기본 경로와 metric을 우선한다.
- Wi-Fi가 없으면 서비스가 대기하며 IP가 생긴 뒤 시작한다.
- NetworkManager dispatcher가 연결·해제·DHCP 변경 이벤트를 처리한다. 선택된 주소가 바뀌었을 때 서비스를 다시 시작한다. 주소가 그대로면 유지하며, 수동으로 중지한 서비스는 시작하지 않는다.
- `/etc/300seconds/dashboard.env`의 기존 고정 `DASHBOARD_BIND`를 제거했다. 서비스는 이후에도 파일에 남아 있는 옛 주소보다 자동 탐색한 주소를 우선한다.
- `enable-dashboard.sh`는 IP 인수를 받지 않고 자동 선택을 사용한다. 보드 설치본: `/opt/300seconds/dashboard/enable-dashboard.sh`.
- 카메라 RTSP는 실행 시 선택한 주소를 상속한다. 브라우저의 WebSocket·RTSP 주소는 기존 `location.host`/`location.hostname` 처리를 사용한다.
- 기존 파일과 환경 설정은 보드의 `/opt/300seconds/dashboard/backups/wifi-auto-20261029T021421Z`에 백업했다. 원격 hardware.py의 기존 차이는 보존하고 필요한 한 줄만 수정했다.

## 검증

- PC와 Jetson Python에서 네트워크 동작 테스트 5개 통과: Wi-Fi 선택·주소 변경, 미연결/링크 로컬 대기, 복수 Wi-Fi 경로 선택, 이벤트별 재시작/수동 중지 유지, 부팅 대기 후 오래된 bind 값 대체.
- 셸 문법 검사 통과. systemd unit 검증 종료 코드 0. 기존 snapd/varlink 등 무관한 시스템 경고는 `wifi-validation.txt`에 기록했다.
- 실제 보드의 주소가 유지된 DHCP 이벤트: PID 7285 유지, 불필요한 재시작 없음.
- 런타임 상태 파일에 이전 주소를 모의한 후 DHCP 이벤트 실행: PID 7745로 변경, 실제 Wi-Fi `192.168.219.127`로 정상 복구.
- 환경 파일에는 고정 IP가 없고, 실행 프로세스의 환경에는 자동 탐색한 IP가 들어간 것을 확인했다.
- 서비스 enabled/active, `192.168.219.127:8000`에서만 HTTP listener 확인.
- Windows에서 `/`, `/api/health`, `/api/session` 모두 HTTP 200. API 상태 `ok`.
- Pico·카메라·마이크는 health=false 상태다. 네트워크 수정으로 주변장치까지 복구됐다는 의미가 아니다.
- 실제 DHCP 주소 변경, Wi-Fi 해제, 재부팅 시험은 수행하지 않았다. 주소 변경 분기는 단위 테스트와 보드의 모의 이전 주소 이벤트로 검증했다.

주소가 바뀌면 진행 중인 대시보드 세션이 재시작되므로 브라우저도 새 주소로 다시 접속해야 한다. 고정 호스트명/mDNS를 추가한 작업은 아니다.

이 변경은 이전 `diagnosis.md`의 대시보드 bind 실패를 해결한다. SquashFS 커널 충돌 원인과 해결 여부는 별개다.
