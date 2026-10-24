# 연속 관찰·GPT Live 검증 원본

2026-10-24 KST. 모의 UI와 실제 보드를 구분한다.

- `nano-dashboard-tests.log`: Nano Python 3.8 대시보드 회귀 검사 73개 통과.
- `nano-provider-tests.log`: 공급자·기존 분석 검사 68개 통과.
- `nano-provider-greeting-tests.log`: Live 인사 추가 후 공급자 5개 검사 통과.
- `provider-preflight.json`: 실제 두 사진 분석·Live 시작/종료. 원본 JPEG와 키는 포함하지 않음.
- `live-verification.json`: 실제 보드 오디오·자막·종료, 수집 DB·CSV·API 보호 검증. 사용자 음성 원음은 포함하지 않음.
- `final-verification.json`: v3 실제 기록 24건 성공, 약 10초 간격, 수집 켜짐·현재 오류 없음 확인.
- `preview-desktop.png`: **모의 데이터** 화면.
- `live-desktop.png`: **실제 Nano 운영** 화면.
- `live-session.png`: **실제 GPT Live 카드** 화면. 10초 시험 종료 후 상태다.
- `install.log`, `start-services.log`, `stop-services.log`: 백업·설치·서비스 적용 결과.

실제 Live는 10초 시험이며 최종 사용량 10.0초 확정, PCM 입력 441,600 bytes·출력 360,000 bytes다. 한국어 인사 자막을 저장하고 정상 종료했다. 스피커 실청취, SW1 실제 누름, 10분 전체 세션 안정성은 아직 검증 완료로 주장하지 않는다.

초기 분석 형식 오류와 뒤따른 보류를 DB에 보존했다. 운영 중 출력 지침·스키마를 v2/v3으로 보완했으며 각 기록의 `prompt_version`으로 구분한다. 이후 검증 상태는 [설계·운영 문서](../../../연속_관찰_DB와_GPT_Live.md)를 따른다. 운영 수집은 켜져 있고 GPT‑4.1 mini·GPT Live는 유료 API다.
