# Pico 2 펌웨어 코드 해설

이 펌웨어는 Jetson의 명령과 여섯 개 터치 입력을 받아 NeoPixel, 눈 매트릭스, 서보를 제어한다. 핵심은 **계산과 실제 출력을 분리하고, 장치 출력의 소유자를 하나로 유지하는 것**이다. `device_task`가 장치를 소유하고 다른 태스크는 명령이나 최신 상태를 전달한다.

이 문서는 2026-10-26 작업본의 소스를 설명한다. 여기서 말하는 각도와 완료는 소프트웨어 명령·쓰기 결과다. 실제 각도, 발광, 전원 상태의 관측을 뜻하지 않는다.

## 1. 먼저 알아둘 Rust 개념

| 코드 표현 | 이 프로젝트에서의 의미 |
| --- | --- |
| crate | Cargo가 빌드하는 Rust 단위. 한 패키지에 라이브러리와 실행 바이너리가 있다. |
| `lib.rs` | 장치 없이도 실행 가능한 계산·검증 로직의 입구. `pico2_device_bench` 이름으로 사용한다. |
| `main.rs` | RP2350에서 실제 USB와 GPIO를 초기화하는 실행 프로그램. |
| `#![no_std]` | 운영체제의 표준 라이브러리를 사용하지 않는다. `core`와 고정 크기 자료형을 이용한다. |
| `#![no_main]` | 일반 PC의 `fn main()` 진입 대신 임베디드 런타임의 진입점을 사용한다. |
| `async fn` / `.await` | I/O나 타이머를 기다리는 동안 다른 태스크가 진행하도록 실행을 양보한다. |
| Embassy task | 실행기가 관리하는 비동기 작업. 태스크마다 OS 스레드를 하나 만드는 방식이 아니다. |
| `&mut Devices` | 장치 묶음을 독점적으로 빌려 동시에 다른 코드가 변경하지 못하게 하는 접근. |
| `Option<T>` | 현재 작업이 `Some`으로 있거나 `None`으로 없는 상태. |
| `enum` + `match` | 명령 종류와 처리 결과를 가능한 경우별로 분기한다. |
| `Channel` | 크기가 제한된 메시지 큐. 여러 요청을 순서대로 전달한다. |
| `Signal` | 최신 알림을 전달한다. 모든 버튼 요청을 길게 줄 세우는 용도가 아니다. |
| `#[cfg(target_os="none")]` | RP2350 같은 운영체제 없는 대상에서만 해당 코드를 포함한다. |

`no_std`가 모든 종류의 메모리 할당을 원천적으로 금지한다는 뜻은 아니다. 이 코드의 명령 큐와 프레임, 출력 배열은 고정 크기로 구성된다. 순수 로직을 PC에서 시험할 수 있는 이유는 하드웨어 초기화를 라이브러리 밖에 두었기 때문이다.

## 2. 파일을 역할로 나눠 보기

| 파일 | 소유하는 책임 | 처음 볼 기호 |
| --- | --- | --- |
| `Cargo.toml` | 공통 의존성과 임베디드 전용 의존성 구분 | `target_os = "none"` |
| `.cargo/config.toml` | 기본 빌드 대상과 Cortex-M33 설정 | `thumbv8m.main-none-eabihf` |
| `rust-toolchain.toml` | Rust 1.90과 타깃 구성 | `channel`, `targets` |
| `build.rs`, `memory.x` | 링크 스크립트 경로와 메모리 배치 | `OUT_DIR`, `link.x` |
| `src/lib.rs` | 세션·제스처·보간·진단 프레임의 순수 계산 | `SessionGate`, `ReleaseGuard`, `interpolate_pose` |
| `src/main.rs` | 주변장치 소유, 태스크, 명령 수락, 정지 | `main`, `rx_task`, `device_task`, `Devices` |
| `src/application.rs` | Arm 이후의 출력 목표와 주기 적용 | `Application`, `tick` |
| `src/light_patterns.rs` | SW3 선택과 시간 기반 RGB 프레임 | `PatternButton`, `ButtonPatterns`, `pattern_frame` |
| `src/arm_patterns.rs` | SW4 팔 동작의 기준각·단계·보간 | `ArmPatterns` |
| `src/picotool_reset.rs` | picotool 호환 USB reset 요청 | `chipid_serial`, `register` |

이 폴더 밖의 `crates/pico-device-protocol`은 `Message`, `Frame`, 설정 자료형, COBS·CRC·Postcard, 터치 디바운서를 공유한다. `tools/pico-device-bench`는 PC·Jetson 쪽 USB 소유자이며 대시보드와 펌웨어 사이를 연결한다. 펌웨어 자체가 AI API나 SQLite, HTTP 서버를 실행하지는 않는다.

## 3. 전체 데이터 흐름

```text
브라우저 대시보드 / Jetson 서비스
               |
               v
호스트 USB 브리지  <------------------------- 상태와 응답
               |                                  ^
       binary USB CDC                             |
               v                                  |
        rx_task + FrameDecoder                 tx_task
               |                                  ^
      일반 명령 |         Stop                     |
               v          |                  RESPONSES / EVENTS
     COMMANDS<Envelope>   v                        ^
               |     OE HIGH + generation 증가     |
               |          | STOP_WAKE              |
               v          v                        |
              device_task -------------------------+
               |   |   |
               |   |   +-- ButtonPatterns -> SW3 RGB 배열
               |   +------ Run -> 순차 진단의 현재 단계
               +---------- Application -> 목표각 / 조명 / 눈
                              |
                              v
                 Devices { Pca, Matrix, Left, Right, oe }
                       |         |         |
                      I2C       SPI      PIO + DMA
                       v         v         v
                      서보       눈      NeoPixel

터치 GPIO -> touch_task -> LOCALS / PATTERN_PRESS / ARM_PATTERN_PRESS
                         -> Touch 이벤트 / SNAPSHOT
safety_task -> lease·진행 확인 -> request_stop / watchdog
```

일반 USB 명령을 받았다는 사실만으로 곧바로 장치에 쓰지 않는다. 수락 단계에서 설정과 소유권을 검사한 뒤 상태를 갱신한다. 실제 쓰기는 진단 단계 또는 `Application::tick()`에서 수행한다. Stop은 이 일반 명령 큐를 거치지 않고 먼저 서보 OE를 차단한다.

## 4. 부팅부터 실행까지

`main`은 먼저 GP12 OE를 HIGH로 만든다. PCA9685, 두 NeoPixel의 PIO·DMA, MAX7219 SPI를 구성하고 `Devices::stop_all()`로 출력 정리를 시도한다. 정리에서 발견된 하드웨어 오류 비트는 이후 상태에 남는다. 부팅만으로 검사를 시작하지 않는다.

그다음 터치 입력을 만들고 USB VID/PID `c0de:cafc`, 칩 ID 기반 serial, CDC와 picotool reset interface를 설정한다. USB·수신·송신·안전 태스크를 실행한 뒤 `Devices`를 `device_task`로 넘긴다. 이 소유권 이동 이후 일반 장치 I/O는 그 태스크가 담당한다.

| 실행 주체 | 입력 | 출력과 책임 | 시간 설정 |
| --- | --- | --- | --- |
| `usb_task` | USB 인터럽트 | USB 스택 진행 | 이벤트에 따라 실행 |
| `rx_task` | 64바이트 이하 CDC packet | Frame 복원, version 검사, 일반 명령 큐 또는 우선 Stop | 수신에 따라 실행 |
| `tx_task` | 직접 응답과 push 이벤트 | 프레임 인코딩과 CDC 전송 | packet 쓰기 제한 500ms |
| `touch_task` | GP6~GP11 | 디바운스 이벤트와 SW3·SW4·SW6 요청 | 5ms 대기 |
| `device_task` | Stop·타이머·USB 명령·로컬 진단 | 상태 전환과 실제 출력 | tick 목표 간격 20ms |
| `safety_task` | `DEVICE_TICK`, lease | OE 차단 요청과 watchdog 급식 | 5ms 대기 |

5ms와 20ms는 타이머 설정이다. 장치 쓰기와 `.await`가 추가되므로 엄격한 실행 주기나 물리 정지 시간을 보장하는 수치로 해석하지 않는다.

## 5. 같은 의미처럼 보이는 세 상태

`device_task`에는 서로 다른 세 가지 출력 상태가 있다.

| 상태 | 하는 일 | 종료·교체 방식 |
| --- | --- | --- |
| `Option<Run>` | 눈·LED·서보의 유한 진단 | 단계가 끝나거나 Stop으로 제거 |
| `Option<Application>` | Arm 이후 포즈, 한 축 이동, 조명, 눈, SW4 팔 동작 | Arm으로 구성하고 Stop으로 제거 |
| `ButtonPatterns` | SW3 랜덤 조명 | 새 SW3로 교체, SetLight·진단·Stop 등에서 해제 |

`Status.running`은 `Run` 진단만 표시한다. 값이 비어 있어도 눈이나 조명이 켜져 있을 수 있다. `Outputs`를 함께 읽어야 한다. `Outputs.armed=true`는 `Application`이 있다는 뜻이며, `servo_enabled=false`인 설정도 가능하다. 이는 OE LOW나 실제 서보 이동과 같은 값이 아니다.

`Application::tick()`은 포즈, SW4 팔 패턴, 조명, 눈 순서로 처리한다. 포즈는 매 tick 보간하고 완료 뒤 PWM을 유지할 수 있다. 주기 조명은 계속 새 프레임을 쓴다. 눈은 대기 중인 프레임을 `take()`로 한 번 적용하고 MAX7219에 래치된다.

## 6. 명령 프레임과 결과를 구분하기

```text
Frame { version: u8, session: u64, seq: u32, body: Message }
                 |
                 +-- Message::SetServo { channel, target_cdeg, move_ms }
```

wire 바이트는 Postcard 직렬화, CRC 무결성 정보, COBS 프레이밍과 구분자를 사용한다. `FrameDecoder`가 쪼개지거나 이어진 USB packet을 프레임으로 복원한다. CDC 포트에 JSON 문자열을 직접 쓰는 방식은 지원하지 않는다.

일반 명령은 `Envelope { frame, generation, busy }`로 큐에 들어간다. `generation`은 수신 당시 작업 세대이고 `busy`는 수신 당시의 활동 상태다. `device_task`가 이 정보와 현재 상태를 함께 확인한다.

| 결과 | 뜻 | 뜻하지 않는 것 |
| --- | --- | --- |
| `Ack { request_seq, code }` | 요청 수락 또는 거절 | 실제 움직임 완료 |
| `Applied { request_seq, kind }` | 예정된 보간 또는 출력 쓰기의 적용 단계 완료 | 센서로 확인한 각도·점등 |
| `TestEvent` | 진단 단계, 자연 완료 또는 중단 | 모든 `fault=true`가 물리 고장이라는 판정 |
| `Status` | 진단·터치·오류·OE의 최신 스냅샷 | 모든 일반 출력 상태의 완전한 설명 |
| `Outputs` | Arm과 명령각, 출력 활동 상태 | 엔코더로 읽은 실제 각도 |
| `ServoDriver` | PCA probe·레지스터·디지털 핀 상태 | 전압계 측정 |

Applied의 kind는 포즈 1, 조명 첫 프레임 2, 눈 쓰기 3, 단일 서보 4다. push Frame의 `seq`, `Applied.request_seq`, `TouchEvent.event_seq`는 각각 이벤트 순서, 원래 명령의 순서, 터치 이벤트 순서이므로 혼동하지 않는다.

## 7. 왜 session, seq, generation을 모두 쓰는가

| 경계 | 막으려는 문제 | 소유하는 코드 |
| --- | --- | --- |
| session | 이전 호스트 연결의 명령이 새 연결에서 실행됨 | `device_task`, `SESSION` |
| seq | 재전송된 명령이 다시 실행되거나 과거 명령이 뒤늦게 실행됨 | `SessionGate` |
| generation | Stop 이전에 큐에 있거나 await 중이던 작업이 다시 출력을 켬 | `request_stop`, `Envelope`, `run_valid` |
| lease | 호스트가 사라졌는데 출력이 계속됨 | `LAST_PING`, `lease_valid` |
| watchdog | 제어 태스크가 더 이상 진행되지 않음 | `safety_task`, `DEVICE_TICK` |

`SessionGate`는 최근 8개 ACK 결과를 보관한다. 중복 요청에는 같은 ACK를 돌려주고 작업은 재실행하지 않는다. session 일치 자체는 `SessionGate::check()`가 아니라 호출자가 검사한다. 중복 KeepAlive도 ACK만 재전송하며 lease를 연장하지 않는다. KeepAlive에는 새 seq가 필요하다.

`request_stop()`은 `STOPPED=true`, generation 증가, GP12 OE HIGH, `STOP_WAKE` 알림을 순서대로 수행한다. 이후 `device_task`가 Application과 패턴을 없애고 NeoPixel 검정, MAX7219 blank/shutdown, PCA all-off를 시도한다. Stop ACK는 이 정리 시도 뒤 전송한다. 정리 오류는 `Status.faults`로 확인해야 한다.

I2C 요청은 40ms 제한을 사용한다. `.await` 뒤에도 작업 유효성을 재확인하고 서보 OE를 LOW로 연다. Stop이 먼저 들어왔다면 늦게 끝난 쓰기가 출력을 다시 켜면 안 되기 때문이다.

호스트 lease는 1000ms다. `DEVICE_TICK`이 250ms 이상 갱신되지 않으면 safety 태스크는 정지를 요청하고 watchdog을 급식하지 않는다. watchdog은 1000ms로 설정된다. CPU 전체 정체나 전원 이상에서의 실제 시간 한계는 별도 실측 사항이다.

## 8. 데이터 단위와 고정 크기

| 데이터 | 단위·범위 | 예 |
| --- | --- | --- |
| `target_cdeg`, 포즈 배열 | 1/100도, 6축 | `9000 = 90도` |
| `servo_angle` 진단 반환값 | 정수 도 | `90`, `80`, `100` |
| `move_ms`, 패턴 시각 | ms | `1000 = 1초` |
| `max_speed_cdeg_s` | 1/100도 매초 | `2400 = 24도/초` |
| NeoPixel 프레임 | 한 손 `[[u8;3];36]`, RGB | 기본 사용 길이는 4+4+10=18 |
| 진단·SW3 NeoPixel 채널 | 최대 32/255 | 미사용 tail은 검정 |
| 일반 SetLight 채널 | RGB와 밝기를 곱해 최대 64/255 | brightness 상한 64 |
| 눈 프레임 | 좌우 각 `[u8;8]` | 위부터 8행, bit7이 왼쪽 |
| 터치 mask | 하위 6bit | SW1은 bit0, SW6은 bit5 |

`DeviceConfig`는 LED 배치·터치·진단 공통 펄스 설정이다. `ActuatorConfig`는 일반 Arm에 사용하는 축별 각도·펄스 보정과 속도 설정이다. 진단용 `servo_ticks()`와 일반 구동의 `ActuatorConfig::ticks()`는 입력 단위와 설정 소유자가 다르다.

큐 크기는 일반 명령 8, 로컬 진단 2, 직접 응답 8, 이벤트 16이다. 이벤트 큐가 차면 기다리지 않고 `DROPPED`를 증가시킨다. 약 100ms 간격의 상태 스냅샷으로 누락된 터치 이벤트 뒤에도 현재 상태를 다시 알 수 있게 한다. 큐가 모든 이벤트의 영구 보존을 보장하지는 않는다.

## 9. 눈과 서보에서 주의할 좌표

눈의 left/right는 로봇 본체 기준이다. 정면 관찰자의 좌우와 반대다. 가까운 첫 모듈이 왼쪽 눈이며 CW90 보정을 적용한다. 먼 모듈은 오른쪽 눈이고 회전하지 않는다. `matrix_mount_frame()`에서 한 번 보정하고 `matrix_packet()`은 먼 모듈의 바이트부터 전송한다.

서보의 `current`, `last_commanded`, `known_positions`는 소프트웨어가 알고 있는 명령 기준값이다. `SeedServoPositions`로 복원해도 실제 서보가 그 각도에 있다는 측정은 아니다. 따라서 위치 복원과 실제 이동을 구분해서 읽는다.

## 10. 권장 코드 읽는 순서

1. 공통 프로토콜의 `Message`, `Frame`, `DeviceConfig`, `ActuatorConfig`를 읽는다.
2. `main.rs`의 `main`에서 어떤 주변장치를 누가 소유하는지 본다.
3. `rx_task`에서 바이트가 `Envelope`로 바뀌는 지점을 찾는다.
4. `device_task`의 `Message::SetServo` 분기부터 따라간다.
5. `Application::servo()`와 `tick()`에서 목표와 실제 쓰기가 분리되는 모습을 본다.
6. `interpolate_pose`, `servo_target`과 패턴 모듈의 테스트를 읽는다.
7. `touch_task`의 SW3·SW4·SW6 분기와 release guard를 읽는다.
8. `request_stop`, `run_valid`, `safety_task`를 따라 취소 경계를 확인한다.

라이브러리 HTML에서는 [세션 문지기](crate::SessionGate), [포즈 보간](crate::interpolate_pose),
[SW3 패턴](crate::light_patterns), [SW4 패턴](crate::arm_patterns)을 눌러 API와 예제로 이동할 수 있다.
