# P5 RPY 전용 출력 부품 목록

2026-10-23 · mm · **29종, 총 32개 출력**. `HAND_DOWEL_4x6`만 4개, 나머지는 각 1개다.

기준은 [P5 형상 부품 목록](../source/geometry_P5_parts.json)과 [출력 manifest](print/manifest.json)다. 두 목록의 부품 집합, 각 부품의 원형 STL·방향 STL·3MF 입력 해시, 단일 폐합 메시와 수량을 대조했다. 서보·혼·베어링·금속 지지축 표시 바디는 출력 수량에 포함하지 않는다.

**P5 폴더의 파일만 사용한다.** 같은 이름의 P2/P4 팔도 형상이 다르며 P4의 Y축 손목과 혼용하지 않는다. 아래 치수는 방향 적용 STL의 경계상자 X×Y×Z다. 실제 출력 성공·서포트·공정 검증을 뜻하지 않는다.

수정 팔4종은 최초 직접 STL의 비폐합을 같은 STEP의 OCP 재테셀레이션으로 보완했다. 왼앞 팔은 미세 누락 삼각형1개를 추가 수선했으며 네이티브·STEP 원본은 바꾸지 않았다. 아래 표는 최종 배포 메시 기준이다. [재생성·원표면 비교 근거](../source/P5_geometry_files/arm_tessellation.json), [최종 출력 전수검사](../source/P5_geometry_files/print_geometry_QA.json)와 [상세 이력](PRINT_ASSEMBLY.md#출력-메시-검사와-확인-범위)을 확인한다.

| 부품 | 수량 | 출력 경계상자 mm | 역할 | P5 파일 |
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
| L_CURVED_ARM_CORE_FRONT | 1 | 126.00×219.00×40.00 | P5 팔: Ø88 어깨 캡·브리지와 X축 손목 고정 코어 | [STEP](cad/L_CURVED_ARM_CORE_FRONT.step) · [출력 STL](print/oriented_stl/L_CURVED_ARM_CORE_FRONT.stl) · [3MF](print/single_part_3mf/L_CURVED_ARM_CORE_FRONT.3mf) |
| L_CURVED_ARM_CORE_REAR | 1 | 126.00×219.00×40.00 | P5 팔: Ø88 어깨 캡·브리지와 X축 손목 고정 코어 | [STEP](cad/L_CURVED_ARM_CORE_REAR.step) · [출력 STL](print/oriented_stl/L_CURVED_ARM_CORE_REAR.stl) · [3MF](print/single_part_3mf/L_CURVED_ARM_CORE_REAR.3mf) |
| R_ROUND_YAW_COLLAR_TRIAL | 1 | 82.00×82.00×35.00 | J1 베이스 칼라 | [STEP](cad/R_ROUND_YAW_COLLAR_TRIAL.step) · [출력 STL](print/oriented_stl/R_ROUND_YAW_COLLAR_TRIAL.stl) · [3MF](print/single_part_3mf/R_ROUND_YAW_COLLAR_TRIAL.3mf) |
| R_CURVED_ARM_CORE_FRONT | 1 | 126.00×219.00×40.00 | P5 팔: Ø88 어깨 캡·브리지와 X축 손목 고정 코어 | [STEP](cad/R_CURVED_ARM_CORE_FRONT.step) · [출력 STL](print/oriented_stl/R_CURVED_ARM_CORE_FRONT.stl) · [3MF](print/single_part_3mf/R_CURVED_ARM_CORE_FRONT.3mf) |
| R_CURVED_ARM_CORE_REAR | 1 | 126.00×219.00×40.00 | P5 팔: Ø88 어깨 캡·브리지와 X축 손목 고정 코어 | [STEP](cad/R_CURVED_ARM_CORE_REAR.step) · [출력 STL](print/oriented_stl/R_CURVED_ARM_CORE_REAR.stl) · [3MF](print/single_part_3mf/R_CURVED_ARM_CORE_REAR.3mf) |
| ROUNDED_PHONE_CRADLE_TRIAL | 1 | 82.00×60.54×53.51 | 휴대폰 받침 | [STEP](cad/ROUNDED_PHONE_CRADLE_TRIAL.step) · [출력 STL](print/oriented_stl/ROUNDED_PHONE_CRADLE_TRIAL.stl) · [3MF](print/single_part_3mf/ROUNDED_PHONE_CRADLE_TRIAL.3mf) |
| SEAM_SPLICE_1_FRONT | 1 | 48.00×44.00×10.00 | 베이스 전후 접합판·정렬키·M3 좌석 | [STEP](cad/SEAM_SPLICE_1_FRONT.step) · [출력 STL](print/oriented_stl/SEAM_SPLICE_1_FRONT.stl) · [3MF](print/single_part_3mf/SEAM_SPLICE_1_FRONT.3mf) |
| SEAM_SPLICE_1_REAR | 1 | 48.00×44.00×10.00 | 베이스 전후 접합판·정렬키·M3 좌석 | [STEP](cad/SEAM_SPLICE_1_REAR.step) · [출력 STL](print/oriented_stl/SEAM_SPLICE_1_REAR.stl) · [3MF](print/single_part_3mf/SEAM_SPLICE_1_REAR.3mf) |
| SEAM_SPLICE_2_FRONT | 1 | 48.00×44.00×10.00 | 베이스 전후 접합판·정렬키·M3 좌석 | [STEP](cad/SEAM_SPLICE_2_FRONT.step) · [출력 STL](print/oriented_stl/SEAM_SPLICE_2_FRONT.stl) · [3MF](print/single_part_3mf/SEAM_SPLICE_2_FRONT.3mf) |
| SEAM_SPLICE_2_REAR | 1 | 48.00×44.00×10.00 | 베이스 전후 접합판·정렬키·M3 좌석 | [STEP](cad/SEAM_SPLICE_2_REAR.step) · [출력 STL](print/oriented_stl/SEAM_SPLICE_2_REAR.stl) · [3MF](print/single_part_3mf/SEAM_SPLICE_2_REAR.3mf) |
| L_SHOULDER_YAW_TURRET | 1 | 79.99×72.00×91.00 | J1 회전판·J2 고정 어깨 하우징 | [STEP](cad/L_SHOULDER_YAW_TURRET.step) · [출력 STL](print/oriented_stl/L_SHOULDER_YAW_TURRET.stl) · [3MF](print/single_part_3mf/L_SHOULDER_YAW_TURRET.3mf) |
| R_SHOULDER_YAW_TURRET | 1 | 79.99×72.00×91.00 | J1 회전판·J2 고정 어깨 하우징 | [STEP](cad/R_SHOULDER_YAW_TURRET.step) · [출력 STL](print/oriented_stl/R_SHOULDER_YAW_TURRET.stl) · [3MF](print/single_part_3mf/R_SHOULDER_YAW_TURRET.3mf) |
| L_ROLL_YOKE_PALM_FRONT | 1 | 154.99×87.98×106.99 | 안쪽 Roll 캡·후방 요크·앞 손바닥 일체 | [STEP](cad/L_ROLL_YOKE_PALM_FRONT.step) · [출력 STL](print/oriented_stl/L_ROLL_YOKE_PALM_FRONT.stl) · [3MF](print/single_part_3mf/L_ROLL_YOKE_PALM_FRONT.3mf) |
| L_ROLL_PALM_REAR | 1 | 92.99×42.00×29.00 | 뒤 손바닥·목 서비스 분할 | [STEP](cad/L_ROLL_PALM_REAR.step) · [출력 STL](print/oriented_stl/L_ROLL_PALM_REAR.stl) · [3MF](print/single_part_3mf/L_ROLL_PALM_REAR.3mf) |
| L_ROLL_BEARING_CAP | 1 | 88.00×106.99×6.00 | 마지막에 닫는 X동축 베어링 캡·연결 귀 | [STEP](cad/L_ROLL_BEARING_CAP.step) · [출력 STL](print/oriented_stl/L_ROLL_BEARING_CAP.stl) · [3MF](print/single_part_3mf/L_ROLL_BEARING_CAP.3mf) |
| R_ROLL_YOKE_PALM_FRONT | 1 | 154.99×87.98×106.99 | 안쪽 Roll 캡·후방 요크·앞 손바닥 일체 | [STEP](cad/R_ROLL_YOKE_PALM_FRONT.step) · [출력 STL](print/oriented_stl/R_ROLL_YOKE_PALM_FRONT.stl) · [3MF](print/single_part_3mf/R_ROLL_YOKE_PALM_FRONT.3mf) |
| R_ROLL_PALM_REAR | 1 | 92.99×42.00×29.00 | 뒤 손바닥·목 서비스 분할 | [STEP](cad/R_ROLL_PALM_REAR.step) · [출력 STL](print/oriented_stl/R_ROLL_PALM_REAR.stl) · [3MF](print/single_part_3mf/R_ROLL_PALM_REAR.3mf) |
| R_ROLL_BEARING_CAP | 1 | 88.00×106.99×6.00 | 마지막에 닫는 X동축 베어링 캡·연결 귀 | [STEP](cad/R_ROLL_BEARING_CAP.step) · [출력 STL](print/oriented_stl/R_ROLL_BEARING_CAP.stl) · [3MF](print/single_part_3mf/R_ROLL_BEARING_CAP.3mf) |
| HAND_DOWEL_4x6 | 4 | 4.00×4.00×6.00 | 손 전후 정렬용 느슨한 핀, 양손 각2개 | [STEP](cad/HAND_DOWEL_4x6.step) · [출력 STL](print/oriented_stl/HAND_DOWEL_4x6.stl) · [3MF](print/single_part_3mf/HAND_DOWEL_4x6.3mf) |

정적 출력 배치의 최대 높이는 약 **106.99 mm**다. X1 Carbon 기본 프로파일 높이250mm, 앞 왼쪽18×28mm 제외 영역, 가장자리1mm와 브림5mm 예약을 검사했다. [배치 그림](print/bed_overview.svg)과 [P5 출력·조립 안내](PRINT_ASSEMBLY.md)를 함께 확인한다.

자동 방향 후보(`automatic_review_required`)의 코어 내부·케이스 레일·손 요크·서비스 개구·너트 홈은 서포트와 제거 경로를 슬라이서에서 재검토한다. `3MF`는 단일 모델·좌표만 포함하며 재료/공정 프리셋·실제 브림·서포트·G-code는 없다.

실제 슬라이싱·출력, 수축, 재료 강도, 현품 끼움·체결·하중 시험은 미검증이다. CAD 6축 RPY 구동과 실제 하드웨어 구동도 별개다.
