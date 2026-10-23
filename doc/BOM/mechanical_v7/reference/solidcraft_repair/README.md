# STEP 재직렬화 시험 - 채택하지 않은 스크래치 파일

확인일: 2026-10-23. **이 폴더의 STEP은 제작용이나 교체용으로 사용하지 않는다.** 정식 `cad/` 파일이나 CAD 생성 코드는 변경하지 않았다.

SolidCraft의 네 WRAP_HAND 셸 가져오기 경고를 줄일 수 있는지 확인하려고, 원본 개별 STEP을 CadQuery로 불러온 뒤 다음 설정으로 재저장했다.

- `write_pcurves=False`
- `precision_mode=1`
- 위 두 설정 조합

12개 재저장 파일 모두 재입력 시 `isValid=True`이고 경계상자는 같지만 **부피가 약 4,061~4,065 mm³ 달라졌다**. `variant_validation.json`에 기록했다. 닫힌 유효 형상이라는 사실만으로 동등한 형상이라고 판단할 수 없으므로 어떤 대안도 채택하지 않았다. 이 값은 CAD 기본 부피 적분 결과이다.

대표 `L_WRAP_HAND_FRONT.step`의 원본 셸은 `Closed=True`, ShapeAnalysis의 free edge 및 bad edge 없음이다. 같은 파일의 부피를 고정밀 적응 적분(`BRepGProp.VolumeProperties`, Eps=1e-9)으로 재확인하면 약 59,647.862 mm³, `no_pcurves` 재저장본은 약 55,576.350 mm³로 여전히 차이가 난다. 단순 기본 적분 오차로만 설명되지 않는다. SolidCraft의 경고 원인은 확정하지 않았다.

정식 STEP/폐합 STL은 보존하고, SolidCraft 네이티브 파일의 해당 네 바디 가져오기 한계를 별도로 알리는 것이 현재 검증된 처리다. 곡면을 근사 형상으로 바꾸거나 원본 외형을 재작성하는 수리는 시도하지 않았다.
