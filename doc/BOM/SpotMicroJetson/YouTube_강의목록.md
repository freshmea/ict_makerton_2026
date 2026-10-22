# 원본 YouTube 강좌 목록

- 재생목록: [006_Robots_001_Spot_Micro](https://www.youtube.com/playlist?list=PLK2UKp8KOXe1ZRbSmcO3VvE_TNs66K6lA)
- 게시 채널: **Korean Engineers**. Road-Balance 저장소 README가 직접 연결하는 강좌다.
- 확인: 2026-10-22, 브라우저 화면에서 동영상 **25개**의 제목과 URL을 확인했다. 재생목록에서는 **02강이 마지막에 놓여 있다**. 아래 표는 학습하기 쉽게 강의 번호순으로 정렬했다.
- 제목 공통 접두어: `Spot Micro! w/Jetson nano, w/o ROS`.

| 강 | 제목 | 영상 |
| --- | --- | --- |
| 01 | SpotMicro 프로젝트 소개와 목차 소개 | [보기](https://www.youtube.com/watch?v=RocfxXIWZd4) |
| 02 | 구매 링크를 포함한 준비물 설명 | [보기](https://www.youtube.com/watch?v=WV4XagCFLmA) |
| 03 | 3D 프린팅 파츠 소개 | [보기](https://www.youtube.com/watch?v=RFxHaI4Lt6A) |
| 04 | 시뮬레이션 소개 및 환경 구성 (Jetson Nano에서는 구동 불가, 데스크탑에서 구성) | [보기](https://www.youtube.com/watch?v=A0KBixvFAxA) |
| 05 | 시뮬레이션 구동 실습 및 설명 - 1 | [보기](https://www.youtube.com/watch?v=gOpPMToIf8o) |
| 06 | 시뮬레이션 구동 실습 및 설명 - 2 | [보기](https://www.youtube.com/watch?v=iqLxMBpgGS0) |
| 07 | 4족 보행 Kinematics 설명 - 1 | [보기](https://www.youtube.com/watch?v=9BUBcX6Y8RE) |
| 08 | 4족 보행 Kinematics 설명 - 2 | [보기](https://www.youtube.com/watch?v=TvkJ5PffmuE) |
| 09 | Matplotlib를 사용한 Inverse Kinematics 실습 | [보기](https://www.youtube.com/watch?v=gO34PRgbh2E) |
| 10 | 외관 조립 설명 - 다리 조립 | [보기](https://www.youtube.com/watch?v=v6WOk3I8juo) |
| 11 | 외관 조립 설명 (몸체 조립 후 다리와의 결합) | [보기](https://www.youtube.com/watch?v=XcKpf5IAYIc) |
| **12** | **전자, 전원부 조립 설명** | [보기](https://www.youtube.com/watch?v=AUtIKKJltyg) |
| 13 | Jetson Nano 세팅 | [보기](https://www.youtube.com/watch?v=orxFLitnro0) |
| 14 | Jetson Nano 개발환경과 Python 가상환경 구성 | [보기](https://www.youtube.com/watch?v=SIXsb4cWBSM) |
| **15** | **서보모터란? 프로젝트에 사용된 모터의 스펙 설명** | [보기](https://www.youtube.com/watch?v=StFKgFmMEK0) |
| **16** | **Jetson Nano를 이용한 모터 제어 실습** | [보기](https://www.youtube.com/watch?v=Az8Ae3zJoPo) |
| 17 | 가조립된 로봇을 이용한 Pose 제어 | [보기](https://www.youtube.com/watch?v=9gwIaQl9vzI) |
| **18** | **모터 Calibration과 코드 설명** | [보기](https://www.youtube.com/watch?v=pvS29mRDxEc) |
| 19 | 제자리 걷기 실습 | [보기](https://www.youtube.com/watch?v=dX37iuWznEE) |
| 20 | 보행 메커니즘 설명 1 | [보기](https://www.youtube.com/watch?v=2cYUtxOxUP0) |
| 21 | 보행 메커니즘 설명 2 | [보기](https://www.youtube.com/watch?v=OzEfRp2S6Co) |
| 22 | 제작 시 주의해야 할 디버깅 포인트들 | [보기](https://www.youtube.com/watch?v=waEfR0EjBx4) |
| 23 | 시뮬레이션에서 실습한 작업들을 실제 로봇에 적용해보기 (Pybullet to JetsonNano) | [보기](https://www.youtube.com/watch?v=aMmzNu1zNtM) |
| 24 | 키보드를 통한 원격 전후양옆 제어 실습 | [보기](https://www.youtube.com/watch?v=XefhWWCUX94) |
| 25 | 최종 시연, SpotMicro 커뮤니티 소개 | [보기](https://www.youtube.com/watch?v=MT8CpmtM-QM) |

## 확보한 자동자막

| 강 | 보관 파일 | 우선 확인할 내용 |
| --- | --- | --- |
| 12 | [전자·전원부](transcripts/12_power.txt) | 08:18 VCC/V+ 구별, 11:49 배터리, 12:21~13:48 강압·6V 설정, 18:25 전원 경로, 19:16 핀맵, 20:18 주소 설정 |
| 15 | [서보 사양](transcripts/15_servo_specs.txt) | PWM 개념, 주파수와 펄스 폭, 실제 사용 모터 사양 설명 |
| 16 | [모터 제어](transcripts/16_servo_control.txt) | Jetson I2C, 보드 2개, 모터 인덱스별 제어 실습 |
| 18 | [캘리브레이션](transcripts/18_calibration.txt) | 모터 종류에 따른 펄스 범위와 각도 대응, 라이브러리 기본값과 보정 |

자막은 YouTube에서 제공하는 **한국어 자동생성본**이며, 시간표시를 포함해 저장했다. 숫자·제품명·핀 이름이 잘못 인식된 부분이 있다. 자막을 교정한 공식 강의록으로 취급하지 않는다. 설정값은 영상 화면·저장소 코드·제조사 자료와 대조한다. 영상 파일이나 전체 25강 자막을 내려받은 것은 아니다.

HTTP 요청으로 받은 YouTube HTML만으로는 영상 목록을 얻지 못했지만, 브라우저 렌더링 화면에서 목록을 확인했다. [기계 판독용 목록](youtube_videos.json)과 [자막별 출처·해시](transcripts/sources.json)를 함께 보관한다.
