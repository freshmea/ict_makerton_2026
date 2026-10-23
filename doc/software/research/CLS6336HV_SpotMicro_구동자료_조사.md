# CLS6336HV — SpotMicro 문서·커뮤니티 구동 자료

조사일: 2026-10-23, Asia/Seoul. 대상: 현재 벤치에서 사용 중인 JX CLS6336HV 6개.

**같은 서보를 약 500~2500µs로 제어한 SpotMicro 커뮤니티 사례가 있다.** 보존된 SpotMicroJetson 수정판은 60Hz·460~2440µs를 사용한다. 두 자료 모두 제조사가 보증한 끝점이나 모든 개체의 실제 180° 회전을 증명하지는 않는다. 현재 장치에서는 약 50Hz·500~2500µs로 6개를 순차 구동했고, 사용자가 회전폭 증가와 걸림·이상음 없음을 확인했다.

설정·출처·미확인 값을 기계가 읽을 수 있는 [조사 데이터 JSON](CLS6336HV_SpotMicro_근거데이터.json)에 함께 보존했다. 원본 전체를 전재하지 않고 수치·출처와 적용 범위를 추출했다. 이번 조사는 펌웨어 주파수 변경이나 추가 서보 구동을 수행하지 않았다.

## 1. 출처별 설정 비교

| 근거 | 주파수 | 제어 펄스·중립 | 확인 범위 |
| --- | --- | --- | --- |
| JX 제조사 제품 데이터 | 330Hz 표기 | 중립1520µs. 최소·최대 펄스 미기재 | 제품 사양. 최대 회전각도 미기재 |
| SpotMicroJetson 수정판 | 60Hz | 460~2440µs | 해당 커밋의 소스 설정 |
| SpotMicroJetson 15·18강 | 구간·설명 구분 필요 | CLS6336HV에 500~2500µs 설명 | 보존된 한국어 자동자막. 계측 결과표 없음 |
| SpotMicro 이슈 #8 사용자 | 명시 확인 못 함 | 약500~2500µs, 중립1500µs | 같은 모델을 Pololu Maestro로 제어했다는 실사용 보고 |
| 이번 Pico 벤치 | 약50Hz, prescale121 | RUN01: 1000~2000µs → RUN02: 500~2500µs | 6개 순차 동작 로그와 사용자 관찰. 실제 각도 미계측 |

제조사 표의330Hz를 근거로 다른 프로젝트의 PCA raw count를 그대로 쓰면 펄스폭이 달라진다. 현재50Hz 설정에서 움직였다는 관찰도330Hz의 동작 검증을 대신하지 않는다.

## 2. 제조사에서 확인한 것

[JX CLS6336HV 제품 페이지](https://hkjx-servo.com/product-detail.html?category=HOT%20SERVO&product=CLS6336HV)와 해당 페이지의 [제품 데이터](https://hkjx-servo.com/product/HOT%20SERVO/CLS6336HV/text-data.js)를 확인했다. 데이터의 중국어 항목을 기준으로 전압별 값을 구분했다.

| 항목 | 기재 값 |
| --- | --- |
| 중립·주파수 | 1520µs / 330Hz |
| Deadband | 텍스트 데이터2µs |
| 속도 | 6.0V: 0.14s/60°, 7.4V: 0.11s/60° |
| 스톨 토크 | 6.0V: 27.8kg·cm, 7.4V: 35.6kg·cm |
| 크기·질량 | 40.5×20.5×40mm, 63g |
| 최소·최대 펄스 / 정격 전체 회전각 | 확보한 제품 데이터에 없음 |

제품 사진·기존 판매처 자료에는 deadband1µs 표기도 있어 텍스트와 차이가 있다. 이 차이를 임의로 하나의 확정 사양으로 합치지 않았다. 스톨 토크는 정상 연속 운전의 허용 토크가 아니다.

확보한 제품 데이터 파일의 SHA-256은 `883EFCB3B08CEF4C4ED13EF4E75DB15B756ED3A3AB499A86EEDAFE7664D829B7`이다. 추출값과 해시는 JSON에 남겼다. **500~2500µs와 물리180°는 이번에 확보한 제조사 문서로 확정할 수 없다.**

## 3. 이전 SpotMicroJetson 자료를 다시 확인한 결과

저장소: [Road-Balance/SpotMicroJetson](https://github.com/Road-Balance/SpotMicroJetson). 보존 커밋: `2235c77a93e86d04dec2e03c6306ba2c06d454ce`. 이번에는 [기존 로컬 스냅샷](../../BOM/SpotMicroJetson/repository_snapshot.json)과 [설정 확인 문서](../../BOM/SpotMicroJetson/세팅_확인.md)를 직접 대조했다. 해당 커밋 raw URL의 웹 조회는 실패했으므로, 아래 수치는 로컬에 보존된 원본 파일을 읽은 결과다.

### 코드에서 직접 읽은 값

- [servo_controller_fix.py 30~40행](https://github.com/Road-Balance/SpotMicroJetson/blob/2235c77a93e86d04dec2e03c6306ba2c06d454ce/JetsonNano/servo_controller_fix.py#L30-L40): 두 PCA 모두60Hz, 각 서보460~2440µs. [로컬 파일](../../BOM/SpotMicroJetson/repo/JetsonNano/servo_controller_fix.py)의 SHA-256은 `B16BED88DAF9089EE9954D1C64B56A506D0D87ECCBD9E1D48D5316BCDB8E725C`이며 스냅샷 manifest와 일치한다.
- 같은 파일의 전역 서보0~5는 `0x40 CH0~5`, 6~11은 **`0x41 CH6~11`**이다. 반면 [offset 예제](https://github.com/Road-Balance/SpotMicroJetson/blob/2235c77a93e86d04dec2e03c6306ba2c06d454ce/JetsonNano/examples/test_servos_offset.py#L15-L32)는 `%6`으로 각 보드CH0~5를 선택한다. 지금의 한 보드 `0x41 CH0~5` 배선에 원본 매핑을 그대로 복사하지 않는다.
- 수정판의 중립 오프셋은 `[180,90,90,1,90,90,180,90,90,1,90,90]`이다. 해당12축의 장착 방향에 맞춘 값이다. 현재6개 서보의 보정값으로 사용할 근거는 없다.
- 460~2440µs를 선형 매핑하면 명목90의 펄스는1450µs이다. 제조사1520µs 또는 다른 사례의1500µs와 같은 값이 아니다.
- [legacy 실험](https://github.com/Road-Balance/SpotMicroJetson/blob/2235c77a93e86d04dec2e03c6306ba2c06d454ce/JetsonNano/legacy/servos.py#L19-L49)에는50Hz·771~2740µs가 남아 있다. 모델별 정격이 확인된 값으로 취급하지 않는다. 이 파일은 예외가 나도 `finally`의 성공 문구를 출력하므로, 문구 자체를 실물 성공 증거로 쓰지 않는다.

### 강좌에서 설명한 범위와 보정 문제

| 구간 | 보존 자료에서 확인한 내용 | 근거 |
| --- | --- | --- |
| 15강16:39~17:54 | CLS6336HV 모델과500~2500µs·0~180 설명 | [영상](https://www.youtube.com/watch?v=StFKgFmMEK0&t=999s), [자동자막216~232행](../../BOM/SpotMicroJetson/transcripts/15_servo_specs.txt) |
| 16강23:06~25:33 | 실물 제어 시 명령0/180과 실제 회전 범위가 맞지 않는 현상 설명 | [영상](https://www.youtube.com/watch?v=Az8Ae3zJoPo&t=1386s), [자동자막336~368행](../../BOM/SpotMicroJetson/transcripts/16_servo_control.txt) |
| 18강05:26~06:21 | CLS의500~2500µs 설명 | [영상](https://www.youtube.com/watch?v=pvS29mRDxEc&t=326s), [자동자막76~90행](../../BOM/SpotMicroJetson/transcripts/18_calibration.txt) |
| 18강10:27~11:47 | 라이브러리 기본 범위750~2250µs가 서보와 맞지 않아 이동 폭이 줄어드는 예 설명 | [영상](https://www.youtube.com/watch?v=pvS29mRDxEc&t=627s), 같은 자동자막148~167행 |
| 18강15:05~18:37 | 펄스 범위를 바꾼 코드와 두 모터 시연, 이동 폭 개선 설명 | [영상](https://www.youtube.com/watch?v=pvS29mRDxEc&t=905s), 같은 자동자막212~258행 |

[자막 출처 manifest](../../BOM/SpotMicroJetson/transcripts/sources.json)는 모두 한국어 자동 생성으로 표시한다. 이번 조사에서는 영상 화면의 숫자·각도기를 검토하지 않았다. 강좌의500~2500 설명과 후속 코드의460~2440 설정을 하나의 계측 결과로 합치지 않는다. 18강의 MG996R 비교값은 자동자막과 legacy 코드의 숫자도 다르므로 CLS6336HV의 설정 근거로 사용하지 않는다.

## 4. 같은 모델의 커뮤니티 실사용 사례

[mike4192/spotMicro 이슈 #8](https://github.com/mike4192/spotMicro/issues/8), 작성자 `ohmbrew`, 게시일2020-09-09. 사용자는 CLS6336HV, Raspberry Pi3B, ROS Melodic, Pololu Maestro18채널로 조립했으며 개별 제어와 기립 동작을 보고했다.

[설정 댓글](https://github.com/mike4192/spotMicro/issues/8#issuecomment-689292127)에는 PCA의 raw PWM 값 대신 **약500~2500µs**를 사용하는 코드로 바꿨다고 적었다. 중립은1500µs, `servo_max_angle_deg`는82.5, 축별 `range`는1650~1943.3이다. 이 `range`는 끝점 간 폭을 위한 설정 필드이며 최소·최대 펄스 두 개를 뜻하지 않는다. 원본 보정 문서에서82.5는 중립 기준 한 방향 명령 제한이다. 전체 회전각82.5°나 제조사 보증165°로 해석하지 않는다.

[운영자 답변](https://github.com/mike4192/spotMicro/issues/8#issuecomment-691795038)은 혼을 끼운 위치에 따라 중립에서의 링크 각도가 바뀌며, 실제 사용할 관절 범위가 서보의 유효 범위에 들어오도록 재장착·재보정해야 한다고 설명한다. 후속 댓글에도 일부 각도 clipping 문제가 남아 있어 완전히 해결된 보행·정밀 보정 성공 사례로 단정하지 않는다.

이 자료는 **같은 모델의 실제 사용자 보고**로 유용하다. 다만 제어기는 PCA9685가 아니며 주파수·실측 펄스·실제 전체 회전각은 확인되지 않았다.

## 5. 다른 SpotMicro 자료를 가져올 때의 주의점

- [SpotMicroAI Credits](https://spotmicroai.readthedocs.io/en/latest/credits/)는 KDY0523가 CLS6336HV에 맞춘 프레임을 제공했지만 해당 커뮤니티 개발팀은 당시MG996R를 계속 사용한다고 명시한다. CLS용 프레임이라는 이유만으로 모든 전기 설정을 CLS6336HV 사양으로 인용하지 않는다.
- [mike4192 원본 README](https://github.com/mike4192/spotMicro/blob/master/README.md#hardware)는 실제 사용 서보를 **PDI-HV5523MG**로 명시한다. 이슈#8의CLS 사용자와 원본 제작자의 하드웨어를 구분한다. [보정 가이드](https://github.com/mike4192/spotMicro/blob/master/docs/servo_calibration.md)의 중립·방향·장착각·명령 제한 개념은 참고하되 예제 수치는 복사하지 않는다.
- [gonglini의 ROS 프로젝트](https://github.com/gonglini/Spotmicro-Quadruped-Project-with-ROS)는 CLS6336HV12개 채택을 명시한다. 커밋 `d3c42cb10902605c81d2010ebb7c63796cd0d4db`의 [컨트롤러 기본값](https://github.com/gonglini/Spotmicro-Quadruped-Project-with-ROS/blob/d3c42cb10902605c81d2010ebb7c63796cd0d4db/ros-i2cpwmboard-master/src/i2cpwm_controller.cpp#L283)은330Hz인데 [YAML](https://github.com/gonglini/Spotmicro-Quadruped-Project-with-ROS/blob/d3c42cb10902605c81d2010ebb7c63796cd0d4db/spot_micro_motion_cmd/config/spot_micro_motion_cmd.yaml#L20-L34)은중립306counts를 담고 있다. 실제 런타임 주파수·설정 변경 경로와 실물 검증은 확인하지 않았다. 이 조합을 바로 이식할 근거로 삼지 않는다.

PCA9685의 일반 PWM 환산은 `pulse_us = counts × 1,000,000 / (4096 × frequency_hz)`이다. 계산상306counts는50Hz에서약1494µs,330Hz에서약226µs다. 따라서 주파수를 바꿀 때는 count도 다시 계산해야 한다. 실제 주파수에는 발진기·prescale 오차가 있으므로 이 계산이 오실로스코프 실측을 대신하지 않는다.

## 6. 현재 프로젝트에 남길 결정과 다음 데이터

1. 이번 조사로 현재 펌웨어의 주파수나 끝점을 자동 변경하지 않는다. 이번 벤치의 **약50Hz·500~2500µs** 결과는 [RUN-20261023-02](../test-results/2026-10-23/RUN-20261023-02.md)에 남긴다. 재부팅 시 기본1000~2000µs로 복귀한다. 현재 명령의 하한은500µs이므로 원본의460~2440µs를 그대로 보내면 거부된다.
2. 명목0/90/180과 실제 회전각을 구분한다. 현재500~2500µs 매핑의 명목90은1500µs이며, 제조사 중립1520µs와 차이가 있다. 보정 전에는 실제 각도를 단정하지 않는다.
3. 다음 축별 보정은 서보 번호·PCA 채널·방향·중립펄스·두 기준각의 측정 펄스·기구 조립 후 허용 범위를 한 묶음으로 남긴다. 다른 로봇의12축 오프셋은 가져오지 않는다.
4. 이번 사용자의 “회전폭 증가, 걸림·이상음 없음”은 무부하 관찰이다. 부하 중6V 유지·전류·온도·정지 지연·장시간 반복은 별도 시험 대상으로 남긴다.

현재6개 축의 실제 각도와 보정 끝점은 JSON에서 `null`로 남겼다. 이 파일은 참고 데이터이며 펌웨어가 읽는 자동 적용 설정 파일이 아니다.
