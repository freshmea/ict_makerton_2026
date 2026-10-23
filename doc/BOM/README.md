# 보유 부품 BOM 자료실

사진 확인 및 수집일: **2026-10-23** (한국 시간).

- [v8 P5 — 6서보·Yaw / Pitch / Roll 개정 중](mechanical_v8/README.md): 최신 사용자 기준은 좌우 각 Yaw·Shoulder Pitch·Wrist Roll이다. 손 길이 방향 X동축 서보·하우징과6축 설정·출력 패키지를 P5로 개정 중이다. P4의 두 Pitch 구성과 P0~P3 자료는 이전 이력이며 P5 완료 근거로 사용하지 않는다.
- [P5 조립·X동축 손목·6축 구동 상세](mechanical_v8/source/ASSEMBLY_JOINTS_P5.md): 서보6개 배정, 실제축과 부모 링크, 3분할 손·분리 베어링 캡의 조립 의도와 검사 진행 상태.
- [이전 P4 두 Pitch 구성](mechanical_v8/source/ASSEMBLY_JOINTS_P4.md): Yaw·Shoulder Pitch·Wrist Pitch로 작성했던6서보 설계·검사 이력. 최신 P5 손목과 출력물을 혼용하지 않는다.
- [v7 내장 서보·감싸는 관절·곡선 외형](mechanical_v7/README.md): 이전 P1 CAD·3면도·관절 상세·출력 부품 22개. 원본 혼 포켓 재분석 및 SolidCraft 가져오기 제한 기록.
- [v6 치수 기반 CAD 이력](mechanical_v6/README.md): 이전 P0 배치와 치수 출처·끼움 시험편. 관절 참고 2페이지는 v7 P1으로 교체했다.
- [재료 목록과 사용 전 확인 사항](재료%20목록.md): 사진 기반 식별, 최소 수량, 확정/미정 사양, 전원·카메라 호환성.
- [마이크·스피커·네오픽셀 추가 자료](오디오_LED_추가부품.md): BA-R9 제조사 설명서, WS2812B 후보 데이터시트, 네오픽셀 가이드, 마이크·USB 어댑터 식별 상태.
- [LED 매트릭스·터치 센서 추가 자료](매트릭스_터치_추가부품.md): MAX7219 모듈 1개, 터치 센서 6개, 제조사 데이터시트와 Jetson 신호 전압 검토.
- [수집 자료와 원문 출처](자료_출처.md): 자료별 로컬 파일, 원문 URL, 접근 실패 현황.
- [Balancer Guard V 연결 안내](Balancer_Guard_V_연결안내.md): 추가로 찾은 밸런서의 역할, 충전기 필요 여부, 연결 전 확인 사항.
- [SpotMicroJetson 로봇개 원본 자료](SpotMicroJetson/README.md): 부품이 일치하는 G-Camp/Road-Balance 저장소, BOM, 25강 목록, 핵심 4강 자동자막 및 원본 전원·서보 설정.
- [수집 기록 JSON](sources.json): 요청/최종 URL, UTC 다운로드 시각, HTTP 상태, 파일 크기, SHA-256, PDF 페이지 수.
- `datasheets/`: IC 데이터시트 및 카메라 제품 개요 PDF.
- `manuals/`: Jetson 사용 설명서, 일반 LiPo 안전 참고 PDF, BA-R9 제조사 설명서 JPG 및 NeoPixel 가이드 PDF.
- `web/`: 접근 가능한 제품 페이지·사용 가이드 HTML 원본과 NVIDIA GPIO README. HTML은 외부 CSS/이미지를 포함하지 않으므로 오프라인 화면이 원문과 다를 수 있다.

추가 사진 3장의 복사 해시와 수집 자료 6개의 검사는 [추가 검증 기록](verification_20261023_audio_led.json)에 보관했다.

매트릭스·터치 사진 2장과 추가 자료는 [별도 검증 기록](verification_20261023_matrix_touch.json)에 보관했다.

기존 `design sample*` 문서와 `img/` 디자인 자료는 보존했다. 실제 부품 사진은 저장소 루트 `img/`에 있는 원본을 연결했다. 이 폴더의 자료는 하드웨어 동작 검증 결과가 아니다. 제조사, 정부 인증 조회, 판매처, 다른 제품의 일반 참고자료를 구분해서 이용한다. 원문 저작권은 각 권리자에게 있으며 자료 자체를 프로젝트 라이선스로 재허가하지 않는다.

`collect_sources.py`는 이번에 사용한 수집 도구다. 실행에는 Python의 `requests`, `PyMuPDF`가 필요하다. 기존 파일 내용이 다르면 덮어쓰지 않지만 `sources.json`은 실행 결과로 갱신되므로 재수집 전 기존 기록을 보존한다.
