# P4 전용 출력 부품 목록

> 이전 두 Pitch 구조의 P4 출력 이력이다. 최신 P5는 손목을 X동축 Roll로 개정 중이며 이 목록을 P5 출력 목록으로 사용하지 않는다. [최신 상태](../README.md).

2026-10-23 · mm · **27종, 총 30개 출력**. `HAND_DOWEL_4x6`만 4개, 나머지는 각 1개다.

기준은 [P4 형상 부품 목록](../source/geometry_P4_parts.json)과 [출력 manifest](print/manifest.json)다. 두 목록의 부품 집합, 각 부품의 원형 STL·방향 STL·3MF 입력 해시, 단일 폐합 메시와 수량을 대조했다. 서보·혼·베어링·금속 지지축 표시 바디는 출력 수량에 포함하지 않는다.

**P4 폴더의 파일만 사용한다.** 같은 이름의 상위 P2 팔은 형상이 다르다. 아래 치수는 방향 적용 STL의 경계상자 X×Y×Z이며, 조립 좌표의 부품 크기 표와 다를 수 있다. 각 파일이 실제 출력에 성공했거나 서포트·공정이 검증됐다는 뜻은 아니다.

| 부품 | 수량 | 출력 경계상자 mm | 역할 | P4 파일 |
| --- | ---: | --- | --- | --- |
| PILL_BASE_TRAY_1 | 1 | 213.33×200.00×96.00 | 3분할 베이스 트레이 | [STEP](cad/PILL_BASE_TRAY_1.step) · [출력 STL](print/oriented_stl/PILL_BASE_TRAY_1.stl) · [3MF](print/single_part_3mf/PILL_BASE_TRAY_1.3mf) |
| PILL_BASE_LID_1 | 1 | 213.33×200.00×4.00 | 3분할 베이스 서비스 뚜껑 | [STEP](cad/PILL_BASE_LID_1.step) · [출력 STL](print/oriented_stl/PILL_BASE_LID_1.stl) · [3MF](print/single_part_3mf/PILL_BASE_LID_1.3mf) |
| PILL_BASE_TRAY_2 | 1 | 213.33×200.00×96.00 | 3분할 베이스 트레이 | [STEP](cad/PILL_BASE_TRAY_2.step) · [출력 STL](print/oriented_stl/PILL_BASE_TRAY_2.stl) · [3MF](print/single_part_3mf/PILL_BASE_TRAY_2.3mf) |
| PILL_BASE_LID_2 | 1 | 213.33×200.00×4.00 | 3분할 베이스 서비스 뚜껑 | [STEP](cad/PILL_BASE_LID_2.step) · [출력 STL](print/oriented_stl/PILL_BASE_LID_2.stl) · [3MF](print/single_part_3mf/PILL_BASE_LID_2.3mf) |
| PILL_BASE_TRAY_3 | 1 | 213.33×200.00×96.00 | 3분할 베이스 트레이 | [STEP](cad/PILL_BASE_TRAY_3.step) · [출력 STL](print/oriented_stl/PILL_BASE_TRAY_3.stl) · [3MF](print/single_part_3mf/PILL_BASE_TRAY_3.3mf) |
| PILL_BASE_LID_3 | 1 | 213.33×200.00×4.00 | 3분할 베이스 서비스 뚜껑 | [STEP](cad/PILL_BASE_LID_3.step) · [출력 STL](print/oriented_stl/PILL_BASE_LID_3.stl) · [3MF](print/single_part_3mf/PILL_BASE_LID_3.3mf) |
| PEBBLE_HEAD_FRONT_TRIAL | 1 | 160.53×140.48×25.52 | 페블 머리 전후 외장 | [STEP](cad/PEBBLE_HEAD_FRONT_TRIAL.step) · [출력 STL](print/oriented_stl/PEBBLE_HEAD_FRONT_TRIAL.stl) · [3MF](print/single_part_3mf/PEBBLE_HEAD_FRONT_TRIAL.3mf) |
| PEBBLE_HEAD_REAR_TRIAL | 1 | 192.00×155.00×96.00 | 페블 머리 전후 외장 | [STEP](cad/PEBBLE_HEAD_REAR_TRIAL.step) · [출력 STL](print/oriented_stl/PEBBLE_HEAD_REAR_TRIAL.stl) · [3MF](print/single_part_3mf/PEBBLE_HEAD_REAR_TRIAL.3mf) |
| CAPSULE_VISOR_TRIAL | 1 | 144.00×27.77×67.00 | 얼굴 베젤 | [STEP](cad/CAPSULE_VISOR_TRIAL.step) · [출력 STL](print/oriented_stl/CAPSULE_VISOR_TRIAL.stl) · [3MF](print/single_part_3mf/CAPSULE_VISOR_TRIAL.3mf) |
| L_ROUND_YAW_COLLAR_TRIAL | 1 | 82.00×82.00×35.00 | J1 베이스 칼라 | [STEP](cad/L_ROUND_YAW_COLLAR_TRIAL.step) · [출력 STL](print/oriented_stl/L_ROUND_YAW_COLLAR_TRIAL.stl) · [3MF](print/single_part_3mf/L_ROUND_YAW_COLLAR_TRIAL.3mf) |
| L_CURVED_ARM_CORE_FRONT | 1 | 138.99×219.00×34.00 | P4 개정 팔: Z225 하부 절삭·Ø88 어깨 캡·브리지 | [STEP](cad/L_CURVED_ARM_CORE_FRONT.step) · [출력 STL](print/oriented_stl/L_CURVED_ARM_CORE_FRONT.stl) · [3MF](print/single_part_3mf/L_CURVED_ARM_CORE_FRONT.3mf) |
| L_CURVED_ARM_CORE_REAR | 1 | 138.99×219.00×34.00 | P4 개정 팔: Z225 하부 절삭·Ø88 어깨 캡·브리지 | [STEP](cad/L_CURVED_ARM_CORE_REAR.step) · [출력 STL](print/oriented_stl/L_CURVED_ARM_CORE_REAR.stl) · [3MF](print/single_part_3mf/L_CURVED_ARM_CORE_REAR.3mf) |
| L_WRAP_HAND_FRONT | 1 | 171.98×90.00×34.00 | J3 손 전후 회전 외장 | [STEP](cad/L_WRAP_HAND_FRONT.step) · [출력 STL](print/oriented_stl/L_WRAP_HAND_FRONT.stl) · [3MF](print/single_part_3mf/L_WRAP_HAND_FRONT.3mf) |
| L_WRAP_HAND_REAR | 1 | 171.98×90.00×34.00 | J3 손 전후 회전 외장 | [STEP](cad/L_WRAP_HAND_REAR.step) · [출력 STL](print/oriented_stl/L_WRAP_HAND_REAR.stl) · [3MF](print/single_part_3mf/L_WRAP_HAND_REAR.3mf) |
| R_ROUND_YAW_COLLAR_TRIAL | 1 | 82.00×82.00×35.00 | J1 베이스 칼라 | [STEP](cad/R_ROUND_YAW_COLLAR_TRIAL.step) · [출력 STL](print/oriented_stl/R_ROUND_YAW_COLLAR_TRIAL.stl) · [3MF](print/single_part_3mf/R_ROUND_YAW_COLLAR_TRIAL.3mf) |
| R_CURVED_ARM_CORE_FRONT | 1 | 139.00×219.00×34.00 | P4 개정 팔: Z225 하부 절삭·Ø88 어깨 캡·브리지 | [STEP](cad/R_CURVED_ARM_CORE_FRONT.step) · [출력 STL](print/oriented_stl/R_CURVED_ARM_CORE_FRONT.stl) · [3MF](print/single_part_3mf/R_CURVED_ARM_CORE_FRONT.3mf) |
| R_CURVED_ARM_CORE_REAR | 1 | 139.00×219.00×34.00 | P4 개정 팔: Z225 하부 절삭·Ø88 어깨 캡·브리지 | [STEP](cad/R_CURVED_ARM_CORE_REAR.step) · [출력 STL](print/oriented_stl/R_CURVED_ARM_CORE_REAR.stl) · [3MF](print/single_part_3mf/R_CURVED_ARM_CORE_REAR.3mf) |
| R_WRAP_HAND_FRONT | 1 | 171.98×90.00×34.00 | J3 손 전후 회전 외장 | [STEP](cad/R_WRAP_HAND_FRONT.step) · [출력 STL](print/oriented_stl/R_WRAP_HAND_FRONT.stl) · [3MF](print/single_part_3mf/R_WRAP_HAND_FRONT.3mf) |
| R_WRAP_HAND_REAR | 1 | 171.98×90.00×34.00 | J3 손 전후 회전 외장 | [STEP](cad/R_WRAP_HAND_REAR.step) · [출력 STL](print/oriented_stl/R_WRAP_HAND_REAR.stl) · [3MF](print/single_part_3mf/R_WRAP_HAND_REAR.3mf) |
| ROUNDED_PHONE_CRADLE_TRIAL | 1 | 82.00×60.54×53.51 | 휴대폰 받침 | [STEP](cad/ROUNDED_PHONE_CRADLE_TRIAL.step) · [출력 STL](print/oriented_stl/ROUNDED_PHONE_CRADLE_TRIAL.stl) · [3MF](print/single_part_3mf/ROUNDED_PHONE_CRADLE_TRIAL.3mf) |
| SEAM_SPLICE_1_FRONT | 1 | 48.00×44.00×10.00 | 베이스 전후 접합판·정렬키·M3 좌석 | [STEP](cad/SEAM_SPLICE_1_FRONT.step) · [출력 STL](print/oriented_stl/SEAM_SPLICE_1_FRONT.stl) · [3MF](print/single_part_3mf/SEAM_SPLICE_1_FRONT.3mf) |
| SEAM_SPLICE_1_REAR | 1 | 48.00×44.00×10.00 | 베이스 전후 접합판·정렬키·M3 좌석 | [STEP](cad/SEAM_SPLICE_1_REAR.step) · [출력 STL](print/oriented_stl/SEAM_SPLICE_1_REAR.stl) · [3MF](print/single_part_3mf/SEAM_SPLICE_1_REAR.3mf) |
| SEAM_SPLICE_2_FRONT | 1 | 48.00×44.00×10.00 | 베이스 전후 접합판·정렬키·M3 좌석 | [STEP](cad/SEAM_SPLICE_2_FRONT.step) · [출력 STL](print/oriented_stl/SEAM_SPLICE_2_FRONT.stl) · [3MF](print/single_part_3mf/SEAM_SPLICE_2_FRONT.3mf) |
| SEAM_SPLICE_2_REAR | 1 | 48.00×44.00×10.00 | 베이스 전후 접합판·정렬키·M3 좌석 | [STEP](cad/SEAM_SPLICE_2_REAR.step) · [출력 STL](print/oriented_stl/SEAM_SPLICE_2_REAR.stl) · [3MF](print/single_part_3mf/SEAM_SPLICE_2_REAR.3mf) |
| L_SHOULDER_YAW_TURRET | 1 | 79.99×72.00×91.00 | P4 신설: J1 회전판·J2 고정 어깨 하우징 | [STEP](cad/L_SHOULDER_YAW_TURRET.step) · [출력 STL](print/oriented_stl/L_SHOULDER_YAW_TURRET.stl) · [3MF](print/single_part_3mf/L_SHOULDER_YAW_TURRET.3mf) |
| R_SHOULDER_YAW_TURRET | 1 | 79.99×72.00×91.00 | P4 신설: J1 회전판·J2 고정 어깨 하우징 | [STEP](cad/R_SHOULDER_YAW_TURRET.step) · [출력 STL](print/oriented_stl/R_SHOULDER_YAW_TURRET.stl) · [3MF](print/single_part_3mf/R_SHOULDER_YAW_TURRET.3mf) |
| HAND_DOWEL_4x6 | 4 | 4.00×4.00×6.00 | 손 전후 정렬용 느슨한 핀, 양손 각2개 | [STEP](cad/HAND_DOWEL_4x6.step) · [출력 STL](print/oriented_stl/HAND_DOWEL_4x6.stl) · [3MF](print/single_part_3mf/HAND_DOWEL_4x6.3mf) |

정적 출력 배치의 최대 높이는 약 **96.00 mm**다. X1 Carbon 기본 프로파일 높이 250 mm, 앞 왼쪽 18×28 mm 제외 영역, 가장자리 1 mm와 브림 5 mm 예약을 검사했다. [배치 그림](print/bed_overview.svg)과 [P4 전용 출력·조립 안내](PRINT_ASSEMBLY.md)를 함께 확인한다.

새 어깨 터릿 두 개는 자동 방향 후보(`automatic_review_required`)다. 코어 내부·케이스 서비스 개구·레일의 서포트와 제거 경로는 슬라이서 미리보기로 재검토한다. `3MF`는 단일 부품 모델·좌표만 포함하며 재료/공정 프리셋·실제 브림·서포트·G-code는 없다.

실제 슬라이싱, 서포트, 수축, 재료 강도, 끼움·체결·하중 시험은 미검증이다. CAD의 6축 구동 검사와 출력·하드웨어 동작 검증도 별개다.
