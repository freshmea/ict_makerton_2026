# 서보별 각도 슬라이더 · 2026-10-24

대시보드의 기존 서보 순차 시험 안내를 개별 서보 제어 패널로 연결했다. [실기 대시보드](http://192.168.184.76:8000/#servo-controls)를 새로고침하면 서보 1~6(CH0~CH5)의 슬라이더와 개별 이동 버튼이 표시된다. 제어 시작 후 손을 놓거나 이동을 눌러 선택한 서보만 명령한다. 시작·페이지 로드 자체에는 Arm/이동이 없다.

## 구현과 검증 범위

- UI: 0~180° 정수 목표, 키보드 지원 native range, 각 채널 label·현재 선택·마지막 완료 명령, 데스크톱 3열/모바일 1열. 요청 처리 중에는 추가 이동을 예약하지 않는다. Stop은 debounce 예약도 취소한다.
- 서버: 단일 소유자 토큰과 2초 lease, USB 세션 검사, 완료 Applied 대기, 정지 선점·늦게 끝나는 Arm 차단. 연결 상태가 오래된 경우에도 실행 중인 브리지를 종료하여 MCU keepalive를 철회한다. 재연결 시 이전 요청을 재생하지 않는다.
- 펌웨어: 기존 wire v2 태그를 유지한 개별 Servo·capability·출력 차단 상태의 PCA probe 확장. CH0~CH5 중 선택한 PWM만 갱신하고 기존 전체 Pose와 순차 진단은 유지한다. 다른 활성 채널은 이전 PWM을 유지하며 Stop은 모두 끈다.
- 범위: 임시 수동 Arm에서 기존 1000~2000µs를 유지하고 명령 범위 0~180°·보간 속도 최대 30°/s를 적용한다. 실제 축의 각도·속도를 측정한 것은 아니다. 영구 런타임 보정 파일이나 펄스 범위를 넓히지 않았다.

Python 회귀 51개가 통과했다([로그](python-tests.log)). 개별 채널 매핑, 구형 펌웨어·fault 차단, 세션 변경, 브라우저 lease, 정지 중 늦은 Arm, 오래된 텔레메트리의 브리지 철회, probe 및 API 범위를 포함한다. Rust 프로토콜·펌웨어 host lib·브리지 단위/통합 검사와 RP2350 cross build·Nano native build도 통과했다. [빌드 정보](build-info.json).

브라우저 검사는 실제 화면의 6개 슬라이더와 구동 전 미리보기를 확인하고, 모든 제어 POST를 모의 응답으로 가로챈 뒤 6축 개별 요청·슬라이더 자동 적용·Stop 뒤 예약 취소를 검사했다. 실제 모터 구동 명령으로 이 화면 검사를 수행하지 않았다. [브라우저 결과](browser-qa.txt), [데스크톱](desktop.png), [모바일](mobile.png).

## 업로드와 현재 실기 상태

사용자가 외부 서보 6V OFF 및 BOOTSEL 재연결을 확인한 뒤 RP2350 serial `E679675A69C4039B`를 검증했다. 기존 4MiB flash를 Nano에 백업하고 새 UF2 쓰기·읽기 검증 및 CDC STATUS 복귀를 완료했다. [업로드 결과](flash-result.json).

- UF2 SHA-256: `3388d8cb2c326faf4886fdd914a2ff89609e5d83dc9ba8183ef798db42a6ea85`
- 이전 flash: `/home/jetson/ict_makerton_2026/tmp/pico-flash/20261024T100450.360694Z-linux/previous-flash.bin`
- 이전 flash SHA-256: `ab9b9cfbeedd26a447f87fa1902af856986eeb4ec5eef874101cf5d58a83c154`

**개별 제어 capability는 확인됐지만 PCA9685 주소 0x41의 I2C fault bit 1은 계속된다.** 출력 차단 상태의 probe도 거부됐다. UI와 API는 이를 표시하고 제어 시작·실제 이동을 막는다. 확인된 출력은 `armed=false`, `pose_active=false`, `oe_high=true`다. 사용자 요청의 실제 1번 서보 0~180° 회전과 6축 실물 동작은 아직 검증하지 않았다. 서보 외부 전원 OFF 상태를 유지했고 구동 시험을 자동 실행하지 않았다.

다음 실물 점검은 PCA VCC 3.3V·GND·SDA GP4(물리6)·SCL GP5(물리7)와 주소 설정 0x41이다. 소프트웨어가 어느 배선 또는 보드 부품이 원인인지는 판별하지 못했다. 배선·주소가 확인되면 **서보 보드 연결 재확인**으로 모터를 움직이지 않고 응답부터 확인할 수 있다.

[실제 API·범위/CSRF 거부·probe 결과](live-api.json), [최종 배포 확인 범위·HTTP 출력 상태](final-deployment.json). 최종 패치의 51개 시험과 설치·서비스 재시작은 exit 0이며 이후 대시보드 HTTP 응답과 브라우저 검증도 성공했다. 추가 설치 파일 해시 조회는 SSH 세션 연결 실패로 완료하지 못했다. 기존 오디오 설정은 변경하지 않았다.
