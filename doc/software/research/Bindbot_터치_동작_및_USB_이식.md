# Bindbot 터치 동작과 Pico–Nano USB 이식 기준

확인일: 2026-10-23, 한국 시간. 사용자 요청의 Bindbot은 [freshmea/micro_ros_pico_dev](https://github.com/freshmea/micro_ros_pico_dev/tree/393f96b6e484b5c70245b821dddd3aca2d7cc1fc)로 확인했다. 확인한 main HEAD는 `393f96b6e484b5c70245b821dddd3aca2d7cc1fc`다. `CMakeLists.txt`의 실행 프로젝트 이름이 `bindbot`이며 기존 메모의 이름만으로 결정하지 않고 실제 코드를 다시 읽었다.

## 1. 원본에서 확인한 동작

| 항목 | Bindbot 실제 코드 |
| --- | --- |
| GPIO 읽기 | 원본은 HIGH를 눌림으로 처리하고 초기화에서 풀다운을 설정 |
| 눌림 시작 | 상승 변화에서 단조 시각을 시작 시각으로 저장 |
| 누르는 동안 | 현재 시각에서 시작 시각을 빼 `duration` 계산 |
| 간격 count | `floor(duration / 500ms)`가 증가하면 count와 비프 이벤트를 갱신 |
| 해제 | 현재 `duration`·`beepCount`·시작 시각을0으로 초기화 |
| 샘플링 | 주변장치 태스크에서 약20ms 주기로 갱신 |
| ROS 전송 | 센서3개의 눌림 상태 Bool·count UInt8를100ms마다 전송 |

근거는 [touch_sensor.c의 갱신·해제 처리](https://github.com/freshmea/micro_ros_pico_dev/blob/393f96b6e484b5c70245b821dddd3aca2d7cc1fc/src/drivers/touch_sensor.c#L41), [주변장치 태스크](https://github.com/freshmea/micro_ros_pico_dev/blob/393f96b6e484b5c70245b821dddd3aca2d7cc1fc/src/tasks/periph_task.c#L103), [ROS publisher와100ms 타이머](https://github.com/freshmea/micro_ros_pico_dev/blob/393f96b6e484b5c70245b821dddd3aca2d7cc1fc/src/tasks/uros.c#L253)다.

원본의500ms count는 **한 번 계속 누르는 동안의 경과 간격 수**다. 여러 번 눌렀는지를 시간창 안에서 집계하는 click count와 다르다. 읽은 원본 드라이버에는 소프트웨어 디바운스·다중 클릭 집계가 없고, ROS에는 `duration`과 눌림/해제 이벤트를 따로 보내지 않는다. 원본 count의 UInt8 범위도 새 구현의 장시간 카운터에 그대로 사용하지 않는다.

## 2. 이번 Rust 구현에서 유지·추가할 내용

| 구분 | Pico–Nano 통합 진단 펌웨어 |
| --- | --- |
| 유지 | HIGH 기본 극성, 누른 시간 계산,500ms 간격 hold count, 해제 시 현재 시간·count 초기화 |
| 현 배선 유지 | 터치 GP6~GP11. 원본의 GPIO18~20은 이 프로젝트 매트릭스와 겹치므로 복사하지 않음 |
| 입력 보완 | 기존 터치 시험과 같은 내부 풀 없음, active-low mask 설정,5ms 샘플링·30ms 디바운스 |
| 새 이벤트 | Pressed·Interval·Released·WindowClosed와 이벤트 순번·단조 시각 |
| 해제 이력 | 해제 이벤트에 마지막 누른 시간과 hold count를 포함하고 snapshot에도 마지막 값을 보존 |
| 새 누름 횟수 | 첫 눌림에서 시작하는 기본2초 고정 시간창의 `press_count`. hold count와 별도 필드 |
| 전송 확장 | ROS 대신 USB CDC,6개 센서 전체의 상태를100ms 주기로 Nano에 전송 |
| 카운터 | 포화 처리하는 u32. 해제 이후에도 과거 값과 현재0을 구분 |

터치 모듈의 정확한 IC·토글 설정은 모델 확인과 별개다. 여기서 눌림은 디바운스한 IO 상태를 뜻하며 토글 출력이면 손을 뗀 순간과 IO 해제가 같지 않을 수 있다.

## 3. 진단용 SW6 배정

SW6은 **GP11 / 물리15번**이며 기본 로컬 진단 입력으로 사용한다. 누름이 끝났을 때의 hold count로 아래 검사를 고른다. Nano가 USB로 상태를 받는 동안에도 로컬 검사를 사용할 수 있다.

| 해제 시 hold count | 검사 |
| --- | --- |
| 0 또는1 | MAX7219 양쪽 눈 |
| 2 | 왼손 NeoPixel |
| 3 | 오른손 NeoPixel |
| 4 | 서보6개, 중립 부근 순차 이동 |
| 5 | 눈 → 왼손 → 오른손 → 서보 순차 검사 |
| 6 이상, 기본3초 이상 유지 | 즉시 Stop. 해제 시 추가 검사를 시작하지 않음 |

검사 중 SW6을 다시 누르면 먼저 정지하고 그 해제는 새 시작으로 소비하지 않는다. Nano의 Stop·연결 변경·lease 만료도 누르고 있던 선택을 취소한다. 재부팅·재연결이 이전 검사를 자동으로 다시 실행하지 않도록 한다. 로컬 진단은 설정으로 끌 수 있다.

LED는 **왼손4+4+10=18개, 오른손4+4+10=18개, 합계36개**를 기본값으로 한다. 손별3개 구간 길이는 설정과 USB Configure로 바꾸며 하드코딩된18개 분할을 프로그램 곳곳에 복제하지 않는다.30개 초과 추가 전원 실부하 시험은 별도 확인 항목으로 유지한다.
