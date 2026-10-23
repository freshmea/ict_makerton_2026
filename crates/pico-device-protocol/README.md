# Pico device diagnostic protocol v1

Pico 2와 Nano/PC가 공유하는 `no_std` 진단 프로토콜과 순수 터치 추적기다. GPIO·USB·모터를 직접 제어하지 않는다. 현재 시제품의 USB VID/PID는 `c0de:cafc`이며 wire version은 `1`이다. Nano 애플리케이션 전체의 최종 제어 명령까지 정의한 것은 아니다.

## API

```rust
use pico_device_protocol::{DeviceConfig, FrameDecoder, TouchEngine};

let config = DeviceConfig::default();
config.validate().unwrap();
let mut engine = TouchEngine::new(config).unwrap();
let events = engine.sample(0b000001, 100); // GPIO HIGH 비트, monotonic ms
let states = engine.states(100);
let mut decoder = FrameDecoder::new();
assert!(decoder.push(0).is_none());
```

모든 wire 타입은 `Copy`, `Serialize`, `Deserialize`를 지원한다. 호스트의 `serde_json`이 같은 타입을 출력하거나 설정 파일을 읽을 수 있다. 기본 빌드는 allocator·표준 라이브러리를 요구하지 않는다. 선택 기능 `std`는 Serde의 std 지원만 켜며 wire 형식은 바꾸지 않는다.

`encode_frame(&Frame, &mut [u8]) -> Result<usize, CodecError>`는 마지막 0까지 포함한 길이를 반환한다. `FrameDecoder::push(u8) -> Option<Result<Frame, CodecError>>`는 조각난 USB 패킷·연속 프레임을 처리한다. USB 연결 세션이 교체될 때 `clear()`로 이전 미완성 프레임을 폐기한다. version·session·seq의 수락 및 STOP 우선순위는 펌웨어/호스트가 적용한다.

## Wire 형식과 한도

```text
COBS( Postcard(Frame) || CRC-32/ISO-HDLC little-endian ) || 0x00

Frame { version: u8, session: u64, seq: u32, body: Message }
```

- `VERSION` 및 `PROTOCOL_VERSION`: 1
- `MAX_DECODED`: Postcard와 CRC 4바이트를 합쳐 최대 512바이트
- `MAX_WIRE`: delimiter까지 최대 520바이트
- CRC: reflected polynomial `0xedb88320`, init/xorout `0xffffffff`. 표준 검사 문자열 `123456789`의 결과 `0xcbf43926`.
- 빈 delimiter는 무시한다. 잘못된 COBS·CRC·payload는 오류로 반환한다. 프레임이 넘치면 다음 delimiter까지 버리고 이후 프레임부터 복구한다.
- 역직렬화 후 남는 payload 바이트는 거부한다. 코덱은 version 값을 보존하며 수락 정책을 대신 결정하지 않는다.

골든 `Hello` (`version=1, session=0, seq=0`)의 Postcard는 `01 00 00 00`, CRC LE는 `79 b8 f8 99`, 전체 wire는 `02 01 01 01 05 79 b8 f8 99 00`이다. CRC는 Python `zlib.crc32`로 독립 계산해 테스트에 고정했다.

Postcard enum 태그는 **선언 순서**를 사용한다. 아래 순서·필드 순서를 변경하려면 wire version과 호환 정책을 함께 검토한다.

| Message 태그 | Variant |
| --- | --- |
| 0 | `Hello` |
| 1 | `HelloReply { device_id: u64, uptime_ms: u64 }` |
| 2 | `KeepAlive` |
| 3 | `GetStatus` |
| 4 | `Status(DeviceStatus)` |
| 5 | `Configure(DeviceConfig)` |
| 6 | `RunTest(Module)` |
| 7 | `Stop` |
| 8 | `Ack { request_seq: u32, code: AckCode }` |
| 9 | `Touch(TouchEvent)` |
| 10 | `TestEvent { module: Module, phase: u16, done: bool, fault: bool }` |
| 11 | `Bootloader` |

`Module` 순서는 `Matrix, NeoLeft, NeoRight, Servos, All`이다. `AckCode` 순서는 `Ok, InvalidConfig, Busy, NoSession, Unsupported, Fault, BadVersion, BadSession, StaleSequence`다. `request_seq`는 응답 대상 요청의 `Frame.seq`이며 응답 자체의 sequence와 구분한다.

`DeviceStatus`는 uptime, GPIO HIGH 원시 마스크, 디바운스된 눌림 마스크, 6개 `TouchState`, 실행 모듈, 로컬 시험 허용 상태, 서보 OE 상태, fault 비트값·이벤트 누락 수 및 현재 설정을 포함한다. 이 상태는 호스트/펌웨어가 채운 보고이며 실제 발광·회전각을 센서로 확인한 결과를 자동으로 뜻하지 않는다.

## 기본 설정과 검증

| 설정 | 기본값 | 허용 범위 |
| --- | --- | --- |
| `left_segments` | `[4,4,10]` | 3개 세그먼트 합 1~36 |
| `right_segments` | `[4,4,10]` | 3개 세그먼트 합 1~36 |
| `touch_active_low_mask` | 0 | 하위 6비트만 사용 |
| `local_tests_enabled` | true | bool |
| `test_switch` | 6 | **1 기반 1~6**, 0이면 로컬 선택 비활성 |
| `hold_interval_ms` | 500 | 100~60,000ms |
| `press_window_ms` | 2,000 | 100~60,000ms |
| `servo_min_us / servo_max_us` | 1000 / 2000 | 500≤min<max≤2500 |
| `test_span_degrees` | 10 | 1~30, 명령상 시험 폭 |

각 손 기본 18개, 양손 합계 36개다. 손마다 최대 36개까지 설정할 수 있어 통합 출력 버퍼는 양손 합계 최대 72개에 맞춰 준비해야 한다. 개별 세그먼트 0개는 허용하지만 한 손 전체가 0개인 설정은 거부한다. USB `Configure`로 후속 배치 변경을 전달할 수 있으며 전원 재시작 후 영구 저장 여부는 이 crate가 결정하지 않는다. 서보의 명령상 각도·펄스 범위 검증은 실제 개체의 기계적 보정과 별개다.

## TouchEngine의 시간 의미

`sample(raw_high_mask, now_ms)`에 실제 GPIO HIGH 비트를 넣는다. 엔진 안에서 active-low mask를 적용하고 각 입력을 30ms 디바운스한다. 펌웨어는 5ms 간격으로 호출한다. 엔진은 GPIO pull 모드나 모듈 전원을 변경하지 않는다.

`TouchKind` 순서는 `Pressed, Interval, Released, WindowClosed`다. 이벤트는 센서 `index` **1~6**, 엔진 공통 `event_seq`, uptime, 현재 pressed, duration, hold interval count, 별도 press count를 포함한다. 이벤트 sequence는 u32 모듈러 증가이며 설정 초기화 뒤에도 이어진다.

- **Pressed:** 안정된 눌림 전환 시 시작 시간을 기록한다. duration과 interval count는 0이다.
- **Interval:** 누르는 동안 `floor(held_ms / hold_interval_ms)`가 증가하면 최신 누적 count를 한 번 알린다. 루프가 지연되면 중간 tick을 반복 재생하지 않는다.
- **Released:** 안정된 해제 시 최종 duration·interval count를 이벤트에 보존한다. 현재 pressed/held/interval은 false/0/0이 되며 `last_duration_ms`와 `last_interval_count`에는 방금 결과가 남는다.
- **WindowClosed:** 첫 안정된 press부터 시작하는 고정 시간창의 눌림 **상승 전환 횟수**를 알리고 count를 초기화한다. 눌러 둔 시간의 interval count와 별개다. 시간창 경계와 새 press가 같으면 이전 창을 먼저 닫고 새 창을 시작한다. 길게 누르기만 계속하면 새 press 창이 저절로 반복 생성되지 않는다.

`WindowClosed`의 duration/interval은 이벤트 시점에 계속 누르고 있으면 현재 값, 이미 놓았으면 0이다. 최종 release 결과는 별도 필드에 남는다. u32 duration/count는 포화 처리해 긴 누름에서 작은 정수로 돌아가지 않는다. `sample`의 이벤트 용량은 24개이며 한 호출에서 6개 입력의 동시 창 종료·edge·interval을 처리한다.

`states(now_ms)`는 `[TouchState;6]`을 반환한다. 각 상태는 `pressed, held_ms, interval_count, last_duration_ms, last_interval_count, press_count, window_remaining_ms`다. `configure(config, now_ms)`는 검증 성공 후 held·창 상태를 초기화한다. 검증 실패하면 기존 설정·상태를 바꾸지 않는다. `clear(now_ms)`는 동일한 설정으로 상태를 초기화한다. 로컬 SW6의 모듈 선택·STOP 정책은 이 엔진에 포함하지 않는다.

## Bindbot에서 확인한 근거와 이번 확장

2026-10-23 연결된 GitHub 도구로 원본 `freshmea/micro_ros_pico_dev`의 main HEAD를 다시 확인했다. 고정 커밋은 **`393f96b6e484b5c70245b821dddd3aca2d7cc1fc`**다. `freshmea/bindbot` 경로는 조회에서 확인되지 않았다. 아래 CMake의 `project(bindbot)`과 소스 연결을 실제 프로젝트 식별 근거로 사용했다.

| 원본 코드 | 확인한 동작 |
| --- | --- |
| [CMakeLists.txt 8·43~60행](https://github.com/freshmea/micro_ros_pico_dev/blob/393f96b6e484b5c70245b821dddd3aca2d7cc1fc/CMakeLists.txt#L8) | Bindbot 타깃이 touch/periph/uros 코드를 포함 |
| [project_config.h 52~58행](https://github.com/freshmea/micro_ros_pico_dev/blob/393f96b6e484b5c70245b821dddd3aca2d7cc1fc/src/config/project_config.h#L52-L58) | held beep interval 500ms, 센서 3개. 기존 GPIO는 이번 배선에 복사하지 않음 |
| [touch_sensor.c 34~84행](https://github.com/freshmea/micro_ros_pico_dev/blob/393f96b6e484b5c70245b821dddd3aca2d7cc1fc/src/drivers/touch_sensor.c#L34-L84) | HIGH 입력, held duration/500 count, release 때 내부 값 0 초기화 |
| [touch_sensor.c 89~131행](https://github.com/freshmea/micro_ros_pico_dev/blob/393f96b6e484b5c70245b821dddd3aca2d7cc1fc/src/drivers/touch_sensor.c#L89-L131) | press/release edge·held·duration·beep count API |
| [periph_task.c 103~120·142행](https://github.com/freshmea/micro_ros_pico_dev/blob/393f96b6e484b5c70245b821dddd3aca2d7cc1fc/src/tasks/periph_task.c#L103-L142) | 눌림 이벤트·beep 큐, 20ms 루프 |
| [uros.c 71~110·253~269행](https://github.com/freshmea/micro_ros_pico_dev/blob/393f96b6e484b5c70245b821dddd3aca2d7cc1fc/src/tasks/uros.c#L253-L269) | 센서 3개의 Bool state와 UInt8 beep_count를 100ms마다 ROS publish |

원본의 hold count는 시간창 내 클릭 횟수가 아니다. 원본 드라이버에는 소프트웨어 디바운스와 고정 클릭 집계 창이 없으며, duration을 ROS로 보내는 publisher도 없다. 터치 문서의 “state 하나만 발행”이나 long-press 1000ms 예시는 위 커밋의 실행 코드와 구분했다.

이번 6입력 디바운스·release duration 보존·고정 press 창·명시 이벤트·u32 포화 count·USB 전송은 **이번 프로젝트의 확장**이다. 원본의 uint8 hold count는 128초 누름에서 256을 담을 수 없어 이 새 엔진에서는 긴 누름 검사를 별도로 둔다. 원본 소스의 네트워크 설정값은 이 문서에 전재하지 않았다.

## 검증

저장소 루트 PowerShell에서:

```powershell
. .\firmware\Use-LocalRust.ps1
cargo test --manifest-path crates/pico-device-protocol/Cargo.toml --locked --offline -- --nocapture
cargo check --manifest-path crates/pico-device-protocol/Cargo.toml --target thumbv8m.main-none-eabihf --locked --offline
cargo check --manifest-path crates/pico-device-protocol/Cargo.toml --features std --locked --offline
```

검사 범위는 골든 wire·표준 CRC·조각/연속 프레임·CRC/COBS 손상·초과 프레임 뒤 복구·설정 경계·최대 정수 Status 크기·디바운스·release 보존·고정 창 경계·6입력·긴 누름 포화다. 최악 정수 Status도 Postcard 255바이트, CRC 포함 259바이트, wire 262바이트로 한도 안이다. 순수 테스트와 no_std 대상 빌드 확인은 실물 장치의 통신·입력·구동 시험을 대신하지 않는다.
