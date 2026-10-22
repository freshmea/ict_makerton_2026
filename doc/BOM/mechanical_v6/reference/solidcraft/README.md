# SolidCraft MCP를 통한 원본 관절 분석

확인일: 2026-10-23. SolidCraft 0.16.2의 MCP stdio 서버를 통해 원본 STEP 2개와 STL 1개를 열고 `inspect_design`, `measure`, `body_topology`, `screenshot`, `save`를 실행했다. `mcp_initialize.json`의 instructions는 실제 사용한 백엔드를 **headless in-process SolidCraft session**으로 명시한다. 재실행 코드는 상위 폴더의 `solidcraft_analysis.py`다.

## 실행 중인 GUI 연결 상태

기존 SolidCraft GUI 프로세스는 확인되었지만, 그 프로세스가 연 TCP 리스너는 없었다. control 폴더에는 과거의 `45541.token` 파일만 있었고 `--connect 127.0.0.1:45541`은 연결 시간 초과를 반환했다. 따라서 기존 앱의 현재 설계를 바꾸지 않고, 별도의 SolidCraft MCP 세션에서 분석을 완료했다. `live_connection_status.json`에 비밀 토큰 값을 제외한 확인 결과를 저장했다. 이는 실행 중인 GUI에 화면이 표시되었다는 증거가 아니다.

## MCP 분석 결과와 치수 채택 기준

| 원본 | SolidCraft 결과 | 치수 해석 |
|---|---|---|
| `I_shoulder_cls_modi.stp` | 단일 PartBody, 원본 커널 4,700면, 타임라인 BaseFeature 오류 없음 | **정확한 에지 끝점 범위 110 × 52.5 × 70 mm**. CadQuery로 읽은 STEP 외형과 일치 |
| `O_shoulder_cls_grooved_modi.stp` | 단일 PartBody, 원본 커널 3,488면, 타임라인 오류 없음 | 정확한 에지 끝점 범위 **110 × 5 × 66 mm**. Z좌표 2–68 |
| `L_arm_cover.stl` | 메시 바디, 삼각형 7,128개 | 메시 좌표 외형 **41.159442 × 45 × 143.547668 mm**. 직접 읽은 STL 좌표와 일치 |

`I_shoulder`의 SolidCraft `inspect_design/measure` 바디 전체 bbox는 X좌표 -0.55035–110.78328, 폭 약 111.33363 mm를 반환했다. 그러나 같은 MCP의 `body_topology` 에지 끝점 범위는 X=0–110 mm이며 원본 STEP/CadQuery도 110 mm다. 전체 bbox는 이 파일에서 표시/샘플링 경계가 원본 기하를 넘는 것으로 보이므로 **제작 치수에는 110 mm를 채택**했다. 표시 bbox의 차이 자체는 보존했고 원인을 확정하지 않았다. 원본 파일은 변경하지 않았다.

STL의 `body_topology`는 매끈한 BREP 원통/에지를 생성하지 않는다. 따라서 베어링 자리의 Ø18.2/Ø16.3 mm는 STL 꼭짓점에서 직접 맞춘 원 분석(`../SpotMicro_original_bearing_seat.json`)을 사용한다. 메시 가져오기 성공을 정밀 원통 CAD 복원으로 간주하지 않는다.

각 모델에 다음 파일이 있다.

- `*_open.json`, `*_inspect.json`, `*_measure.json`, `*_topology.json`: MCP 실제 응답.
- `*_iso.png`: MCP `screenshot`으로 저장한 1000 × 760 모델 렌더.
- `*.solidcraft`: 각 원본을 별도 문서로 저장한 SolidCraft 네이티브 파일. 실행 중인 사용자 문서에 덮어쓰지 않았다.
- `analysis_summary.json`: 입력별 분석 요약, 정확한 에지 끝점의 최소/최대좌표.
- `mcp_tools.json`, `relevant_commands.json`: 이 CLI가 제공한 도구 및 가져오기·검사 명령 스키마.

네이티브 파일은 사용자가 SolidCraft에서 직접 열 수 있도록 제공한다. 렌더는 CAD 모델 출력이며 기존 앱 창 스크린샷이 아니다. 정밀 조립 여부, 출력 오차와 실제 하중은 여기서 검증하지 않았다. `measure`의 질량은 기본 재료 밀도 1.29 g/cm³를 적용한 소프트웨어 값으로 실제 PLA 출력 질량이나 인필을 반영한 값이 아니다.
