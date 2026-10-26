# SW4 팔 패턴 구현·배포·실제 입력 검증

2026-10-25 완료 범위: 서보 1~4번(CH0~CH3) 10종 랜덤 패턴, 짧은 누름 즉시 선택, 유지 중 재선택 방지, 이동 중 새 패턴의 연속 보간, 기준각 ±6°/최대 12°/초, 9초 후 복귀와 PWM 해제.

## 배포

- [deploy.log](deploy.log): Nano의 펌웨어 23개·프로토콜 13개·브리지 13개·Python 41개, **90개 검사 모두 통과**, release 빌드와 flash readback, 서비스 active.
- 실제 배포 이미지 SHA256: `21c60796f2f3d9d1be1cabe49ef74843b3789593d51c7b27f953329701fff400`. [Linux 빌드 정보](linux-build-info.json).
- [verification.json](verification.json): 동일 USB serial 복귀, faults 0·OE HIGH, 설치 Python 3파일/브리지 해시, 참조각 복원.
- 마지막 수동 완료 목표 `[28,65,106,77,177,134]°`를 boarddash 소유 `/var/lib/300seconds-dashboard/servo-targets.json`에 보존하고, 부팅 90° 추정으로 갑자기 움직이지 않도록 출력 없는 `SeedServoPositions`로 복원했다. CH0~CH3 참조가 없으면 SW4는 모터를 켜지 않는다.
- 원본 SW3 소스/이미지 백업(Nano): `tmp/sw4-arms-backup-20261025T023248Z/sources-and-image.tgz`. 이후 참조 복원 보완으로 첫 빌드를 flash 전에 중단하고 재빌드했다.
- 후속 소스/설치본 백업(Nano): `tmp/sw4-arms-backup-20261025T023737Z/`.
- 전체 기존 flash 백업(Nano): `tmp/pico-flash/20261025T024427.605719Z-linux/previous-flash.bin`.

## 실제 스위치 입력

[button-watch.json](button-watch.json)과 [telemetry-summary.json](telemetry-summary.json)은 실제 SW3→SW4 입력을 수집했다. 4번은 278ms 짧은 누름이었다.

- `pose_active=true` 및 OE LOW, 서보 1~4번 모두 목표 변화.
- 수집된 명령 범위: 1번 22.57~33.99°, 2번 59.63~70.99°, 3번 100.57~112°, 4번 71.58~83°.
- 5/6번 목표는 177°/134° 유지.
- 약 9초 뒤 `[28,65,106,77,177,134]°`로 복귀, `pose_active=false`, OE HIGH.
- 모든 수집에서 faults 0, 종료 시 SW3 `light_active=true` 유지.

명령각·OE·I2C 성공은 물리 각도나 기구 간섭의 센서 측정값이 아니다. 10종 전체 실물 전수 확인은 수행하지 않았다. 반복 선택·속도·범위·종료·입력 극성·버튼 분리는 자동 검사로 확인했다.

사용자 실물 확인: **“서보 1~4번 모두 정상 동작”**. [확인 기록](physical-confirmation.json).

Windows의 전체 Python 검사는 현지 Pydantic v2와 기존 앱의 v1 문법 불일치로 5개 import 오류가 있었으며, 실제 운영 Nano venv에서 동일 41개가 모두 통과했다. Windows UF2와 실제 Linux 배포 UF2의 해시는 빌드 환경 차이로 다르다. 수정된 Rust 소스와 설치 Python은 로컬 파일과 동일하며, 기존 `picotool_reset.rs`는 줄바꿈만 달라 정규화 후 일치한다.
