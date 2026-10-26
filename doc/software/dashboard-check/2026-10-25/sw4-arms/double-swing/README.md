# SW4 스윙 폭 2배 확대

2026-10-25 사용자 요청으로 10종 전체 패턴의 기준각 대비 진폭을 ±6°에서 **±12°**로 2배 확대했다. 전체 왕복 폭은 최대 24°다. 1초 키프레임 간격·약 9초 실행을 유지해 최대 속도를 12°/초에서 24°/초로 변경했다. 범위 0~180°, 기준각 누적 방지, Stop·lease·fault 및 CH4/CH5 목표 보존을 유지한다.

- Windows와 Nano에서 펌웨어 검사 **24개 통과**. 기존 23개와 함께 실제 기준 `[28,65,106,77]°`에서 상단 `[40,77,118,89]°`, 하단 `[16,53,94,65]°`에 도달하는 검사를 추가했다.
- [배포 로그](deploy.log): 24개 검사, release 빌드, 4MiB 백업, 새 flash 쓰기·readback, 서비스 active.
- [verification.json](verification.json): 최신 이미지 및 소스 해시, Pico connected/faults 0/OE HIGH, 기존 참조각 복원, 설치 모듈 일치.
- 실제 Nano 배포 SHA256: `42d741a5a563f6b83bbd7cc77624b6ffa3a5771191d8341c11e754dcacd756c5`.
- 소스/이미지 백업(Nano): `tmp/sw4-double-backup-20261025T025032Z/sources-and-image.tgz`.
- 전체 flash 백업(Nano): `tmp/pico-flash/20261025T025127.279959Z-linux/previous-flash.bin`.

앞선 “서보 1~4번 모두 정상 동작” 사용자 확인과 실제 PWM 수집은 확대 전 버전의 기록이다. 확대 버전의 각도 센서 계측 및 10종 전수 실물 관찰은 수행하지 않았다.
