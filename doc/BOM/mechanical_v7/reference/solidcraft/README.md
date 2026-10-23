# SolidCraft MCP v7 P1 불러오기 확인

확인일: 2026-10-23. 실행 중인 사용자 SolidCraft 창은 제어하거나 변경하지 않았다. `solidcraft_P1_analysis.py`가 `solidcraft-cli.exe mcp`로 별도 분석 프로세스를 열었다.

- 입력: `../../cad/fold_wing_v7_P1_assembly.step`
- 원본 좌표의 조립 배치를 가져왔고 47개 바디, mm 단위를 확인했다.
- [네이티브 저장 파일](fold_wing_v7_P1_assembly.solidcraft): 6,688,388 bytes.
- [모델 스크린샷](P1_assembly_iso.png): SolidCraft `screenshot(source=model, view=iso)`, 1200×850, GPU 렌더. 곡선 팔·둥근 몸체·양쪽 감싸는 관절 외형을 화면으로 확인했다.
- MCP open/inspect/save/screenshot 응답을 각각 JSON으로 보존했다.

## 남은 가져오기 문제

`P1_open.json`은 오류 0과 함께 **닫히지 않은 바디로 가져왔다는 경고 4건**을 반환했다. STEP 엔티티와 제품 이름을 직접 대응한 결과는 다음과 같다.

| STEP 솔리드 엔티티 | 바디 |
|---|---|
| #44729 | L_WRAP_HAND_FRONT_part |
| #54231 | L_WRAP_HAND_REAR_part |
| #81662 | R_WRAP_HAND_FRONT_part |
| #91214 | R_WRAP_HAND_REAR_part |

네 감싸는 손 외장 부품은 SolidCraft에서 화면에 나타나지만 **SolidCraft 편집용 완전한 닫힌 솔리드로 검증되지는 않았다**. CadQuery 원본 BREP 유효성 및 STL 폐합 검사는 별도 결과이며 이를 대신하지 않는다. 곡면 가져오기 변환에서 발생한 것으로 추정하지만 원인을 확정하지 않았다. 제조용 기준은 CAD/치수와 실제 끼움 시험을 사용하며 이 네 바디를 SolidCraft에서 추가 Boolean 편집하기 전에는 가져오기 수리를 확인해야 한다.

사용자가 `.solidcraft` 파일을 직접 열 수 있도록 저장했으며, 기존 실행 중인 창에 열려 있는 모델과 동기화한 결과는 아니다.
