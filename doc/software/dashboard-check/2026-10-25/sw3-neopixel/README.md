# SW3 NeoPixel 배포·검증

2026-10-25 후속 문제: 대시보드의 NeoPixel 진단은 작동하지만 실물 SW3로 바닥 조명이 켜지지 않음.

원인: 이전 작업이 Windows 소스·UF2 생성에 그쳤고 Nano 소스와 Pico flash에 반영되지 않았다. `preflight.log`에서 Nano의 `PATTERN_PRESS=False`, `light_patterns.rs` 없음, 정상 SW3 Released 입력과 대시보드 NeoLeft/NeoRight 시험 완료를 확인했다.

조치: 변경 소스 6개 반영, Nano ARM 네이티브 검사 20개 통과, RP2350 release 빌드, USB 서비스 중지, 4MiB 기존 flash 백업, 새 UF2 쓰기·verify·앱 복귀 확인, 대시보드 재시작. 배포 중 SSH 출력 대기 timeout이 한 번 발생했으나 flash 전이었고 서비스 active를 확인한 후 출력 스트리밍 경로로 빌드·업데이트를 완료했다.

- 원본 소스/이미지 백업(Nano): `/home/jetson/ict_makerton_2026/tmp/sw3-neopixel-backup-20261025T001104Z/sources-and-image.tgz`
- 기존 전체 flash 백업(Nano): `/home/jetson/ict_makerton_2026/tmp/pico-flash/20261025T001446.064002Z-linux/previous-flash.bin`
- [배포 로그](deploy.log): 검사·새 이미지 해시·flash readback·서비스 active.
- [상태 검증](verification.json): completed/flash_verified/application_status_verified=true, USB connected, faults 0, OE HIGH, 양쪽 `[4,4,10]`.
- [실물 입력 상태 수집](button-watch.log): SW3 최근 입력 및 `light_active=true`.
- [사용자 실물 확인](physical-confirmation.json): “불빛이 켜지고 패턴도 바뀜”.

실물 10종 전수·행/열 방향·전원 부하 계측은 수행하지 않았다. Windows용 `build-info.json`과 Nano의 실제 배포용 `linux-build-info.json`은 빌드 환경과 이미지 해시가 다르며, 실제 업로드 이미지는 후자를 따른다.

사용자 실물 확인과 `light_active=true` 수집 이후 Nano 네트워크 연결에 timeout이 생겨 추가 수집을 종료했다. `verification.json`과 `linux-build-info.json`은 업로드 직후 성공한 명령 출력에서 보존한 내용이다. 배포용 UF2 다운로드와 수정된 문서의 Nano 재복사는 하지 못했으며, 이 폴더 및 최신 설명 문서는 Windows 작업 저장소에 보관했다.
