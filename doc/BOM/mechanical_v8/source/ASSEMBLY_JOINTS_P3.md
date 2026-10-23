# v8 P3 — SolidCraft 관절과 구동 방법

이 문서는 **SolidCraft 안에서 움직이는 조립품**을 설명한다. 좌우 팔에 J1 Yaw와 J2 Pitch를 하나씩 둔 **회전 조인트 4개**가 대상이다. 머리에는 구동 모터가 정의돼 있지 않으므로 목 회전 조인트를 추가하지 않는다. 길이는 **mm**, 회전 값은 **deg**다.

## P2가 움직이지 않았던 이유

기존 [fold_wing_v8_P2.solidcraft](../cad/fold_wing_v8_P2.solidcraft)의 ZIP 안 `document.json`을 직접 확인했다. 검사한 파일의 SHA-256은 `50a8104c4476c6d4fcc6cc2a4c2c0894296edb3b2ae210b1af1da1d5398e881f`다.

| P2 저장 내용 | 실제 값 |
| --- | --- |
| Component / occurrence | 88 / 88 |
| 가져오기 계층의 rigid 조인트 | 87개 |
| 각도를 구동할 revolute 조인트 | **0개** |
| Motion Study | **0개** |
| `grounded: true` occurrence | **0개** |

P2의 실행 시 `joint.list`는 자동 고정 기준 `fixed:[0,2]`, 모든 occurrence의 DOF 0, `floating:[]`를 반환했다. 명시적 Ground 플래그가 0이라는 것과 고정 기준이 전혀 없다는 것은 다르다. 실제 원인은 **가져오기 전체가 rigid로 잠겨 있고 팔·손을 회전시키는 revolute 조인트가 없었다는 점**이다. 화면에서 보이는 축·서보·혼의 형상만으로 회전 자유도가 생기지는 않는다. P2에서 통과한 닫힌 솔리드·출력 크기·정지 자세 검사는 유효한 별도 결과이며, 관절이 구동된다는 검증은 아니었다.

P3는 가져오기 계층을 통째로 잠그던 rigid 관계를 풀고, 고정부·좌우 팔·좌우 손을 각각 묶은 뒤 그 사이에 회전 조인트를 정의한다. 단순한 STEP 재입력 대신 조인트·고정·Motion Study를 보존한 **[fold_wing_v8_P3_motion.solidcraft](../cad/fold_wing_v8_P3_motion.solidcraft)**를 열어야 한다.

## 어느 부품이 함께 움직이는가

다음은 운동 연결 관계다. Browser에 표시되는 가져오기 폴더의 부모·자식 구조와 운동 조인트의 부모·자식 관계를 구별한다.

```text
고정부: P1_closed_base:1 — Ground
├─ L_J1_YAW → 왼쪽 팔 고정 코어 묶음
│  └─ L_J2_PITCH → 왼쪽 손 회전 묶음
└─ R_J1_YAW → 오른쪽 팔 고정 코어 묶음
   └─ R_J2_PITCH → 오른쪽 손 회전 묶음
```

| 묶음 | 포함하는 부품과 역할 | 묶음 내부 관계 |
| --- | --- | --- |
| 몸체 고정부 | 베이스 트레이·뚜껑·연결판, 머리·얼굴·눈·카메라, 스피커와 전장 배치 영역, 휴대폰 받침, Yaw 칼라와 Yaw 서보 **케이스** | 기존 leaf 부품은 고정 기준 occurrence에 rigid로 연결한다. 새 연결판은 root의 고정 몸체로 유지한다. |
| 왼쪽·오른쪽 팔 | `L/R_CURVED_ARM_CORE_FRONT_part:1`을 기준으로 팔 전후 외장·고정 코어, Pitch 서보 **케이스**, 반대편 **고정 지지축**을 함께 묶는다. | 두 출력 절반을 볼트로 조립한 하나의 링크로 취급한다. |
| 왼쪽·오른쪽 손 | `P3_L_HAND:1` / `P3_R_HAND:1`에 새 손 전후 커버·정렬 핀, 짧은 서보 출력축 표시, 혼 표시, 베어링 표시를 함께 묶는다. | 앞 구동 커버와 뒤 베어링 커버가 함께 도는 하나의 링크다. |

**J1:** Yaw 서보 케이스·칼라는 몸체에 남고, 출력 혼을 받는 회전판과 일체인 곡선 팔이 Z축 주위로 돈다. **J2:** Pitch 서보 케이스·고정 코어·반대편 지지축은 팔에 남는다. 서보 출력축과 혼이 손의 앞 커버를 돌리고, 브리지로 연결된 뒤 커버와 손이 함께 돈다.

혼은 서보 케이스와 같은 rigid 묶음에 넣지 않는다. 그렇게 하면 구동측과 고정측이 다시 잠긴다. 반대편 지지축을 손 묶음에 넣는 것도 고정·회전 관계를 뒤집는다. 현재 베어링은 내·외륜이 분리되지 않은 단일 형상 표시이므로 손 쪽 회전 부품에 표시를 붙인다. 베어링 내부의 전동체·내외륜 상대 운동까지 해석하는 모델은 아니다.

## 회전 조인트 4개의 설정

초기 좌표계는 X=좌우, Y=앞뒤, Z=위쪽이다. 아래 위치와 방향은 **네 조인트가 모두 0°인 저장 자세**의 world 좌표다. `joint.as_built`로 현재 배치를 보존하여 정의한다.

| 조인트 이름 | 부모 → 자식 | 원점 XYZ | 초기 축 방향 | 저장값 | CAD 임시 제한 |
| --- | --- | --- | --- | --- | --- |
| `L_J1_YAW` | 몸체 → 왼쪽 팔 | `[-275, 40, 130]` | `[0, 0, 1]` (+Z) | 0° | -15°~+15° |
| `R_J1_YAW` | 몸체 → 오른쪽 팔 | `[275, 40, 130]` | `[0, 0, 1]` (+Z) | 0° | -15°~+15° |
| `L_J2_PITCH` | 왼쪽 팔 → 왼쪽 손 | `[-220, 40, 315]` | `[0, 1, 0]` (+Y) | 0° | -15°~+15° |
| `R_J2_PITCH` | 오른쪽 팔 → 오른쪽 손 | `[220, 40, 315]` | `[0, 1, 0]` (+Y) | 0° | -15°~+15° |

각 조인트는 `revolute`라서 각도 값 하나를 가진다. 0°는 **CAD의 현재 조립 자세**이며 서보의 전기적 중립 1500 μs, 90° 명령이나 혼 스플라인의 설치 위치를 뜻하지 않는다. 실물 서보와 연결할 때는 별도의 중립·방향·오프셋 보정이 필요하다.

양의 각도는 지정 축의 **오른손 법칙**을 따른다. 좌우가 대칭으로 생겼어도 같은 +각도가 같은 시각적 방향을 뜻하지 않는다. J1을 0°로 둔 상태에서 J2 +10°를 주면 왼쪽 손의 안쪽 부분은 내려가고 오른쪽의 안쪽 부분은 올라간다. 대칭으로 같은 제스처를 만들려면 원하는 동작에 맞춰 좌우 부호를 선택한다. P3의 네 축은 독립 구동이며 자동 미러 Motion Link를 추가하지 않는다.

J2는 부모인 팔에 붙어 있으므로 J1을 돌리면 **J2 원점·축도 팔과 함께 이동**한다. 초기 +Y축을 매번 고정된 world +Y축으로 다시 강제하면 두 단계 관절의 관계가 깨진다. 예를 들어 J1=θ일 때 초기 +Y축은 world 좌표에서 `[-sinθ, cosθ, 0]` 방향으로 돌아간다.

**±15°는 CAD 동작 확인을 위한 임시 제한**, 데모의 ±10°도 보여 주기 위한 값이다. 실제 CLS6336HV 허용 범위·혼 간섭·배선 여유·토크·베어링 하중이 검증된 범위가 아니다. 조인트 각도를 입력할 수 있다는 사실을 충돌 없는 가동 범위로 해석하지 않는다.

## SolidCraft 화면에서 직접 움직이기

1. [P3 `.solidcraft` 파일](../cad/fold_wing_v8_P3_motion.solidcraft)을 연다. P2 파일이나 `.step`를 열면 P3의 구동 설정을 사용할 수 없다. Browser에서 네 회전 조인트 이름을 확인한다.
2. 상단 **조립 → 관절 구동**을 연다(영문 UI: SOLID → ASSEMBLE → Drive Joints). 또는 **S**로 명령 검색을 열고 `joint.drive`를 찾는다. 조인트 목록에서 `L_J1_YAW`를 선택해 0°에서 +10°로 바꾼다. 왼쪽 팔과 그 자식인 손이 함께 도는지 확인한다.
3. 해당 값을 0°로 되돌리고 `L_J2_PITCH`를 +10°로 바꾼다. 팔 고정 코어는 그대로 있고 손·혼 표시가 도는지 확인한다. 오른쪽도 `R_J1_YAW`, `R_J2_PITCH`로 각각 확인한다.
4. 상단 **조립 → 운동 연구**를 연다(영문 UI: Motion Study). 저장된 Study에서 **`P3_FOUR_JOINT_DEMO`**를 선택한다. 타임라인 위치를 바꿔 팔·손의 순차 회전을 확인한다. 마지막 단계나 0단계로 되돌린 다음 저장한다.

메뉴 위치는 [공식 기능 목록](https://docs.solidcraft.io/dev/features.html)의 조립 명령과 같다. Study 선택과 타임라인·차트 조작은 [공식 조립 가이드](https://docs.solidcraft.io/guide/assemblies.html)를 따른다. 이 설명은 실행 파일에 없는 별도 플러그인을 요구하지 않는다.

명령 검색에서 JSON을 실행하는 방법도 있다. **S**를 누르고 아래 한 줄을 입력하면 지정한 조인트를 직접 구동한다. 이는 자동으로 회전 도구 대화상자를 여는 문법과 구별된다. [공식 UI 명령 검색 규약](https://github.com/tangency-labs/solidcraft/blob/main/docs/control-protocol.md)

```text
joint.drive {"joint":"L_J2_PITCH","value":10}
```

```text
motion.play {"study":"P3_FOUR_JOINT_DEMO","step":10}
```

원점 자세로 돌아가려면 다음을 실행한다.

```text
motion.play {"study":"P3_FOUR_JOINT_DEMO","step":0}
```

정확한 명령 이름과 인자는 [공식 명령 참조](https://docs.solidcraft.io/reference/commands.html)를 기준으로 한다. `joint.drive`와 `motion.play`는 현재 조립 자세를 바꾼다. 움직임을 확인한 뒤 네 값이 모두 0°인지 확인하고 저장한다.

## Motion Study와 재현 정보

Study 이름은 `P3_FOUR_JOINT_DEMO`, 타임라인 길이는 **80 steps**다. 네 축을 차례로 0° → +10° → -10° → 0°로 구동하며, 다른 축은 각 순서에서 0°를 유지한다.

| 구간 | 움직이는 조인트 | +10° / -10° / 복귀 step |
| --- | --- | --- |
| 0~20 | `L_J1_YAW` | 5 / 10 / 15 |
| 20~40 | `L_J2_PITCH` | 25 / 30 / 35 |
| 40~60 | `R_J1_YAW` | 45 / 50 / 55 |
| 60~80 | `R_J2_PITCH` | 65 / 70 / 75 |

각 축만 골라 보기 위한 20-step Study도 `L_J1_YAW_DEMO`, `L_J2_PITCH_DEMO`, `R_J1_YAW_DEMO`, `R_J2_PITCH_DEMO`라는 이름으로 저장한다. step은 시퀀스의 위치이며 실제 서보 시간이나 제어 주기를 의미하지 않는다. 속도·가속도·구동 전류·부하를 계산한 동역학 결과도 아니다.

재생 원본은 [build_motion_P3.py](build_motion_P3.py)이며, 고정 묶음·운동 묶음·네 회전 조인트·키프레임을 같은 소스에서 만든다. 실행 명령 묶음은 [motion_P3.json](motion_P3.json), 부품 배정은 [group_mapping.json](P3_files/group_mapping.json), 정확한 축·부모·자식 인자는 [joint_specs.json](P3_files/joint_specs.json)에 있다. P2 형상과 원본 파일은 별도로 보존한다.

현재 저장된 P3 ZIP에는 **rigid 39개 + revolute 4개 = 조인트 43개**, Motion Study **5개**, `P1_closed_base:1`의 Ground 설정이 들어 있다. [final_joints.json](P3_files/final_joints.json)에서 `conflicts`, `errors`, `floating`이 모두 비어 있음을 확인했다. [drive_checks_raw.json](P3_files/drive_checks_raw.json)의 네 축 각각 +10°, -10°, 0° 구동 12건은 모두 `moved: true`다. 이 기록은 CAD 엔진의 구동 결과이며 하드웨어 동작 결과는 아니다. 수치 변위와 화면 재생 검증은 각각의 최종 QA·화면 근거와 함께 확인한다.

## 움직이지 않을 때 확인할 항목

| 화면·명령 상태 | 확인할 항목 |
| --- | --- |
| 네 이름이 목록에 없다 | 열려 있는 파일이 P3 `.solidcraft`인지 확인한다. P2 rigid 그룹이나 STEP 가져오기 파일을 다시 연 경우인지 본다. |
| `moved: false`, `unconnected`, `floating` | 몸체 기준 occurrence가 Ground인지, 각 팔이 J1으로 몸체에 연결됐는지, 각 손이 J2로 팔에 연결됐는지 확인한다. |
| 조인트가 rigid이거나 값 칸이 없다 | P2 가져오기 rigid와 P3 revolute를 혼동했는지 확인한다. 네 구동 조인트의 타입은 revolute다. |
| 값은 바뀌지만 특정 부품이 남는다 | 그 부품이 대응하는 팔 또는 손의 rigid 묶음에 포함됐는지 확인한다. Browser의 폴더 안에 있는 것만으로 같은 운동 링크가 되지는 않는다. |
| 몸체까지 움직인다 | Ground 대상과 고정부 rigid 연결을 확인한다. 팔·손 자체를 Ground하지 않는다. |
| 15°보다 큰 값을 주어도 더 안 간다 | 임시 CAD 제한에서 값이 잘린다. 즉시 실제 모터 한계라고 판단하지 않는다. |
| 기존 자세에서 부품이 뒤집힌다 | 원점·축과 조인트 origin 설정을 확인한다. 기존 위치를 보존하는 as-built 관계를 기준으로 복구한다. |

MCP·CLI 확인에는 `joint.list`, `joint.inspect`, `occurrence.properties`, `motion.list`를 사용한다. 구동 성공 메시지만 읽지 말고 `moved`와 실제 occurrence 위치 변화를 함께 확인한다. 이 점검 방법은 작업에 적용한 공식 **solidcraft-mechanisms** 스킬과 [조립 명령 규약](https://docs.solidcraft.io/reference/commands.html)을 따른다.

최종 독립 검사는 [native_motion_P3_qa.json](../evidence/native_motion_P3_qa.json)에 있다. 새 프로세스 2회의 재열기에서 네 회전 조인트·Ground·Study를 확인했고, 각 축 ±10°의 실제 이동, 부모 Yaw 뒤 자식 Pitch의 연속 회전, 9개 Study 키프레임과 중립 복귀를 검사했다. 해석식과 질량중심 최대 차이는 약 0.000094 mm이며, P2와 중립 형상 53바디의 체적·경계상자·중심이 같다.

지정한 SolidCraft 0.20.0 데스크톱 창에서도 P3 파일을 열었다. 네 회전축 표시와 `L_J1_YAW (Revolute)` 선택, 각도 슬라이더가 표시되는 것을 확인했다. [실제 창 기록](../evidence/P3_desktop_joint_drive.json)과 [CAD 엔진으로 만든 동작 GIF](../renders/P3_joint_demo.gif)를 구분해 보존했다. 저장된 원본의 중립값은 0°이며, 사용자가 현재 창에서 조작하는 미리보기 각도와는 별개다.

P3에서 실제로 확인한 항목과 아직 확인하지 않은 항목은 구분한다. 회전 조인트 저장, 값 구동, occurrence 변위, Study 재입력·재생이 운동 모델의 확인 대상이다. 전 범위 충돌·배선·토크·서보 하드웨어 동작·출력품의 체결은 별도 검증 대상이다.
