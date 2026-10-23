# v7 P1 출력 형상 목록

현재 STL은 22개다. 단위 mm, 배율 100%. 모든 끼움·축방향 체결을 확정한 최종 조립품은 아니다. [검토 범위](README.md)를 먼저 확인한다.

| 부품 / STL | 용도 | 경계상자 X×Y×Z (mm) |
| --- | --- | --- |
| [PILL_BASE_TRAY_1](stl/PILL_BASE_TRAY_1.stl) | 둥근 베이스 트레이 | 213.33×200.00×96.00 |
| [PILL_BASE_LID_1](stl/PILL_BASE_LID_1.stl) | 둥근 베이스 뚜껑 | 213.33×200.00×4.00 |
| [PILL_BASE_TRAY_2](stl/PILL_BASE_TRAY_2.stl) | 둥근 베이스 트레이 | 213.33×200.00×96.00 |
| [PILL_BASE_LID_2](stl/PILL_BASE_LID_2.stl) | 둥근 베이스 뚜껑 | 213.33×200.00×4.00 |
| [PILL_BASE_TRAY_3](stl/PILL_BASE_TRAY_3.stl) | 둥근 베이스 트레이 | 213.33×200.00×96.00 |
| [PILL_BASE_LID_3](stl/PILL_BASE_LID_3.stl) | 둥근 베이스 뚜껑 | 213.33×200.00×4.00 |
| [SEAM_PLATE_1](stl/SEAM_PLATE_1.stl) | 베이스 연결판 | 44.00×42.00×4.00 |
| [SEAM_PLATE_2](stl/SEAM_PLATE_2.stl) | 베이스 연결판 | 44.00×42.00×4.00 |
| [PEBBLE_HEAD_FRONT_TRIAL](stl/PEBBLE_HEAD_FRONT_TRIAL.stl) | 페블 머리 전면 | 160.56×25.52×140.49 |
| [PEBBLE_HEAD_REAR_TRIAL](stl/PEBBLE_HEAD_REAR_TRIAL.stl) | 페블 머리 후면 | 192.00×96.00×155.00 |
| [CAPSULE_VISOR_TRIAL](stl/CAPSULE_VISOR_TRIAL.stl) | 캡슐형 얼굴 베젤 | 144.00×27.78×67.00 |
| [L_ROUND_YAW_COLLAR_TRIAL](stl/L_ROUND_YAW_COLLAR_TRIAL.stl) | 원형 Yaw 수납 칼라 | 82.00×82.00×35.00 |
| [L_CURVED_ARM_CORE_FRONT](stl/L_CURVED_ARM_CORE_FRONT.stl) | 곡선 팔·고정 코어 전면 | 131.00×36.00×226.00 |
| [L_CURVED_ARM_CORE_REAR](stl/L_CURVED_ARM_CORE_REAR.stl) | 곡선 팔·고정 코어 후면 | 131.00×36.00×226.00 |
| [L_WRAP_HAND_FRONT](stl/L_WRAP_HAND_FRONT.stl) | 감싸는 손·혼 홈 앞 커버 | 172.00×34.00×90.00 |
| [L_WRAP_HAND_REAR](stl/L_WRAP_HAND_REAR.stl) | 감싸는 손·베어링 뒤 커버 | 172.00×34.00×90.00 |
| [R_ROUND_YAW_COLLAR_TRIAL](stl/R_ROUND_YAW_COLLAR_TRIAL.stl) | 원형 Yaw 수납 칼라 | 82.00×82.00×35.00 |
| [R_CURVED_ARM_CORE_FRONT](stl/R_CURVED_ARM_CORE_FRONT.stl) | 곡선 팔·고정 코어 전면 | 131.00×36.00×226.00 |
| [R_CURVED_ARM_CORE_REAR](stl/R_CURVED_ARM_CORE_REAR.stl) | 곡선 팔·고정 코어 후면 | 131.00×36.00×226.00 |
| [R_WRAP_HAND_FRONT](stl/R_WRAP_HAND_FRONT.stl) | 감싸는 손·혼 홈 앞 커버 | 172.00×34.00×90.00 |
| [R_WRAP_HAND_REAR](stl/R_WRAP_HAND_REAR.stl) | 감싸는 손·베어링 뒤 커버 | 172.00×34.00×90.00 |
| [ROUNDED_PHONE_CRADLE_TRIAL](stl/ROUNDED_PHONE_CRADLE_TRIAL.stl) | 둥근 휴대폰 받침 | 82.00×60.54×53.51 |

CAD 좌표의 각 개별 STEP와 출력용 STL은 위치가 다르다. STL은 각 부품을 양의 좌표로 옮긴 파일이며 조립 위치의 기준은 전체 STEP다.

폐기한 별도 Yaw 혼판 2개는 팔과 일체화했으므로 목록에서 제외했다. `history/retired_separate_rotors`에 보존된 파일은 현재 출력 대상이 아니다.

SolidCraft는 WRAP_HAND 앞뒤 4개에 열린 바디 가져오기 경고를 반환했다. STL 폐합 검사와 별개다. [기록](reference/solidcraft/README.md).
