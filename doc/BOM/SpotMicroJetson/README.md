# SpotMicroJetson 원본 프로젝트 자료 모음

수집일: 2026-10-22 (한국 시간).

## 찾은 프로젝트

**Road-Balance / SpotMicroJetson, G-Camp 한국어 강좌**가 가장 유력하다. 사용자 사진의 부품 조합과 원본 BOM의 배터리 제품명·판매처 품번까지 일치한다. 다만 사용자가 예전에 참고한 강좌가 이것이라는 최종 확인을 받은 것은 아니므로, 과거 작업 이력까지 확정하지는 않는다.

| 비교 항목 | 사용자 사진 / 이번 대화에서 확인한 내용 | 프로젝트 원본 자료 | 판단 |
| --- | --- | --- | --- |
| 배터리 | SKY HOLIC EXTREME 7.4V 2200mAh | 동일 제품명, 디바이스마트 품번 11866 | 강한 일치 |
| 서보 | JX CLS6336HV, 사진 최소 6개 | JX CLS6336HV 12개 | 모델 일치, 수량 차이 |
| PWM 보드 | SunFounder PCA9685 1개 확인 | SunFounder TS0185 2개 | 제조사·계열 일치, 수량 차이 |
| 강압 모듈 | LM2596 HW-411 1개 확인 | LM2596 SZH-PWSD-045 3개 | IC 계열 일치, 모듈 품번·수량 차이 |
| 컴퓨터 | Jetson Nano 계열, 리비전 미확정 | Jetson Nano Development Kit B01 | 계열 일치, 현품 리비전 확인 필요 |
| 카메라 | Camera V2.1 및 Module 3 | 핵심 BOM에는 카메라 없음 | 추가 보유품으로 구분 |
| Wi-Fi | 802.11n USB 동글 | TP-LINK Archer T2U Plus | 현품 동일 모델로 볼 수 없음 |

원본은 **12개 서보를 사용하는 12자유도 4족 로봇**이다. 사진에서 확인한 최소 수량만으로 전체 로봇 부품이 갖추어졌다고 판단하지 않는다. 아래 자료는 보관용이며 로봇에 설치하거나 실행하지 않았다.

## 바로 볼 자료

- [원본에서 확인한 전원·배선·서보 설정](세팅_확인.md)
- [YouTube 25개 강의 목록과 핵심 강좌](YouTube_강의목록.md)
- [공개 BOM의 XLSX 내보내기](Spot_Micro_BOM.xlsx)
- [Drive가 반환한 읽기용 BOM CSV](Spot_Micro_BOM_Drive_readable.csv): `Unnamed` 및 행 인덱스가 포함된 읽기용 추출본. XLSX 원본 내보내기와 구별한다.
- [저장소 README](repo/README.md), [Jetson 설치 안내](repo/JetsonNano/README.md), [시뮬레이션 안내](repo/Simulation/README.md), [기구학 설명](repo/Kinematics/README.md)
- [원본 부품 사진](repo/Images/Readme_Parts2.jpg), [전자부 구성 사진](repo/Images/SpotMicroAI_electronics.png), [Jetson 연결 사진](repo/Images/jetsonNano_connected_1.jpg)
- [수정판 서보 제어 코드](repo/JetsonNano/servo_controller_fix.py), [기존 제어 코드](repo/JetsonNano/servo_controller.py), [캘리브레이션 예제](repo/JetsonNano/examples/test_servos_cali.py)
- [저장소 참조 ZIP](Road-Balance_SpotMicroJetson_2235c77_reference.zip): 코드·문서·CAD/STL/STEP 포함. 대형 데모 GIF, TTF 글꼴, Python 캐시를 제외한 참조 스냅샷.

## 원문 링크

| 자료 | 원문 | 보관 상태 |
| --- | --- | --- |
| 중심 저장소 | [Road-Balance/SpotMicroJetson](https://github.com/Road-Balance/SpotMicroJetson) | 커밋 고정 참조 ZIP, 선택 문서·코드 추출, GitHub HTML |
| 강좌 | [006_Robots_001_Spot_Micro](https://www.youtube.com/playlist?list=PLK2UKp8KOXe1ZRbSmcO3VvE_TNs66K6lA) | 브라우저에서 25개 제목·URL 확인, 핵심 4강 자동자막 저장. 영상 파일은 저장하지 않음 |
| 공개 BOM | [Spot Micro](https://docs.google.com/spreadsheets/d/1UIJ1a0tUQx4ky75Ovr97hnKy3tkcdXQCYJl6zFl0juA/edit) | Drive 메타데이터 확인 후 XLSX 내보내기와 읽기용 CSV 저장 |
| 강좌 Notion | [SpotMicro for G-Camp](https://www.notion.so/SpotMicro-for-G-Camp-c541934a4bad4ad48d1e37ab94c10de8) | 웹 도구 404, 직접 요청에서도 본문 미확보. 원문 링크만 보존 |
| 상위 프로젝트 | [FlorianWilk/SpotMicroAI](https://github.com/FlorianWilk/SpotMicroAI) | 중심 README가 상위 저장소로 참조. 별도 전체 소스는 중복 저장하지 않음 |
| 커뮤니티 문서 | [SpotMicroAI](https://spotmicroai.readthedocs.io/en/latest/) | [홈 HTML](web/SpotMicroAI_home.html), [조립 안내 HTML](web/SpotMicroAI_assembly.html), [크레딧 HTML](web/SpotMicroAI_credits.html) 저장 |
| 원형 기구 부품 | [KDY0523 / Thingiverse 3445283](https://www.thingiverse.com/thing:3445283), [관련 3761340](https://www.thingiverse.com/thing:3761340) | 원 사이트 직접 다운로드 403. 중심 저장소의 CAD/STL/STEP는 참조 ZIP에 포함 |
| 다른 한국어 제작 사례 | [ductility, 2021-01-12](https://ductility.github.io/2021/01/12/Spot_Micro.html) | [HTML](web/Ductility_20210112_build.html). DGS-1199를 사용한 별도 제작 사례로 구분 |
| NVIDIA 소개 | [Jetson 개발자 밋업 소개](https://blogs.nvidia.co.kr/blog/nvidia-jetson-developer-meetup/) | [HTML](web/NVIDIA_meetup.html). 로드밸런스 SpotMicro의 후속 ROS2/CUDA 발표 맥락용 |

ROS Melodic 기반 `0x49b/spotMicro-ROS-Melodic-Jetson-Nano`도 검색되었지만, 이번에 부품이 직접 일치한 중심 자료는 **w/o ROS** 강좌다. ROS 파생 프로젝트의 설치 명령·채널 설정·전원 설정을 혼합하지 않았다.

## 보관 기준과 검증 범위

- 고정 커밋: `2235c77a93e86d04dec2e03c6306ba2c06d454ce`. [원본 트리](github_tree.json), [ZIP 파일별 해시와 제외 범위](repository_snapshot.json), [웹 수집 성공/실패](web_sources.json), [자동자막 출처](transcripts/sources.json), [전체 로컬 검증 기록](verification.json)을 보관한다.
- 원본 ZIP을 내려받아 CRC 검사 후 참조 ZIP을 만들었다. 참조 ZIP에 들어간 파일은 원본과 바이트가 같고, 제외 항목은 기록했다. 내려받은 전체 ZIP은 중간 파일로만 사용하고 약 33MB의 참조 ZIP을 남겼다.
- `repo/`는 선택해서 꺼낸 읽기용 자료다. 전체 작업용 Git checkout이 아니며 `.git` 폴더가 없다. 원본 README의 일부 GIF·외부 자산 링크는 그대로여서 이 선택 폴더에서는 표시되지 않을 수 있다. 원본 내용을 수정해 재작성하지 않았다.
- 원본 [GPL-3.0 LICENSE](repo/LICENSE)를 보존했다. 외부 웹페이지와 YouTube 자막의 권리는 각 권리자에게 있으며 프로젝트 전체에 GPL을 일괄 적용한 것이 아니다.
- BOM 가격은 과거 문서의 값이다. 현재 가격·재고·품질 보증이 아니다. 예를 들어 LM2596 행의 수량 3·단가 3,000원·소계 6,000원은 서로 맞지 않지만 원본 그대로 보존했다.
- 인터넷 자료·파일 무결성·소스 설정을 확인했다. 실제 부품의 출력전압, 통신 인식, 라이브러리 설치, 서보 동작과 보행은 시험하지 않았다.
