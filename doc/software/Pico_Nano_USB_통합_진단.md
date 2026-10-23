# Pico 2 W–Jetson Nano USB 통합 진단

작성일: 2026-10-23, 한국 시간. 사용자가 앞 단계의 마지막 터치·매트릭스 기능 시험까지 완료했다고 확인했다. 이번 문서는 그 부품들을 한 이미지에 합쳐 USB 상태 수신과 로컬 기능 검사를 수행하는 새 구성이다. 새 통합 이미지의 빌드 결과와 실제 업로드·Nano 실행 결과는 구분해 기록한다.

## 1. 구성과 핀

```text
Nano USB host ── USB 데이터 케이블 ── Pico 2 W USB CDC device
  │                                  ├─ PCA9685 → 서보6개
  │                                  ├─ GP16 → 왼손 NeoPixel18개
  │                                  ├─ GP17 → 오른손 NeoPixel18개
  │                                  ├─ MAX7219 → 왼쪽·오른쪽 눈
  │                                  └─ 터치6개, SW6은 로컬 진단
  └─ Rust bridge가 USB를 단독 소유
       ├─ 상태·터치·검사 이벤트: NDJSON 출력
       └─ 다른 Nano 프로세스: 127.0.0.1:37920 UDP 명령
```

| 장치 | GPIO / 물리 핀 | 구성 |
| --- | --- | --- |
| PCA9685 SDA/SCL/OE | GP4/6번, GP5/7번, GP12/16번 | 주소0x41, 서보 CH0~CH5, 초기 OE HIGH |
| 왼손 NeoPixel DIN | GP16 /21번 | PIO0 SM0 / DMA0 |
| 오른손 NeoPixel DIN | GP17 /22번 | PIO0 SM1 / DMA1 |
| MAX7219 CLK/DIN/CS | GP18/24번, GP19/25번, GP20/26번 | 가까운 왼쪽→먼 오른쪽, 모듈2개 |
| 터치 SW1~SW6 | GP6~GP11 /9,10,11,12,14,15번 | IO/VCC/GND 모듈6개 |
| 진단 스위치 기본값 | **SW6 / GP11 /15번** | 눌렀다 놓은 시간으로 검사 선택 |

NeoPixel은 사용자 지정 **각 손4+4+10=18개, 합계36개**다. 세 구간은 같은 손 안에서 직렬 연결하고 양손 데이터는 분리한다. 구간 길이는 `DeviceConfig.left_segments`와 `right_segments`에 모으며 USB Configure 또는 Nano 설정 파일로 변경한다. 현 빌드의 한 손 최대 프레임 용량은36개다.

Configure는 RAM 설정이다. Pico 전원을 다시 켜면 기본값으로 돌아가며 Nano 브리지를 시작할 때 설정 파일을 다시 적용한다.18개를 넘겨 설정하는 것과 전원 실부하 검증은 별도다.

전원·레벨 변환은 [핀 배정·전원](Pico2_핀배정_및_전원.md), [터치·눈 배선](A_스위치6개_MAX7219_양쪽눈_배선.md)을 따른다. 새 진단 코드는 부하 전압·전류를 측정하는 장치가 아니다.30개 초과 추가 전원 실부하 시험 항목은 별도로 유지한다.

## 2. Bindbot에서 참고한 터치 처리

원본은 [Bindbot 터치 드라이버](https://github.com/freshmea/micro_ros_pico_dev/blob/393f96b6e484b5c70245b821dddd3aca2d7cc1fc/src/drivers/touch_sensor.c#L41)의 누름 시간과500ms 간격 count다. 원본에는 시간창 안의 여러 눌림 횟수 집계가 없어 새 필드를 구분해 추가했다. 자세한 원본·이식 비교는 [조사 문서](research/Bindbot_터치_동작_및_USB_이식.md)에 있다.

| Nano에 보내는 데이터 | 의미 |
| --- | --- |
| `pressed` | 디바운스한 현재 IO 눌림 상태 |
| `held_ms` | 현재 누르고 있는 시간. 해제 시0 |
| `interval_count` | 현재 누른 시간÷기본500ms의 정수 부분. 해제 시0 |
| `last_duration_ms` | 마지막 해제 시 확정한 누름 시간 |
| `last_interval_count` | 마지막 해제 시 확정한 hold count |
| `press_count` | 첫 눌림부터 기본2초 고정 시간창 안의 눌림 시작 횟수 |
| `window_remaining_ms` | 위 집계 시간창의 남은 시간 |
| `raw_mask` / `pressed_mask` | GPIO HIGH 원본6비트 / 극성·디바운스 반영6비트 |

샘플링은5ms, 입력별 디바운스는30ms다. `Pressed`, `Interval`, `Released`, `WindowClosed` 이벤트를 즉시 큐에 넣고6개 전체 snapshot을100ms마다 보낸다. 현재값과 마지막 해제값을 함께 보존하며 u32 카운터를 포화 처리한다. `event_seq`와 `dropped_events`로 누락 가능성을 확인하고 상태 snapshot으로 현재 상태를 복원한다.

기본은 active-high·내부 풀 없음이다. `touch_active_low_mask`로 센서별 극성을 바꾼다. 토글 모듈이면 IO 상태와 손을 떼는 순간이 다를 수 있으므로 현재 모듈의 실제 동작 모드를 기준으로 사용한다.

## 3. SW6 하나로 기능 검사

검사 선택은 **해제 시의 hold count**다. Nano가 USB 상태를 수신하는 중에도 로컬 검사를 실행할 수 있다.

| hold count / 기본 누름 시간 | 기능 |
| --- | --- |
| 0~1 /1초 미만 | 양쪽 눈 L/R·8행·8열·체커·눈 패턴 |
| 2 /1.0~1.5초 미만 | 왼손 세 구간 RGB·픽셀 순차 점등 |
| 3 /1.5~2.0초 미만 | 오른손 세 구간 RGB·픽셀 순차 점등 |
| 4 /2.0~2.5초 미만 | 서보 CH0~CH5 순차 기능 검사 |
| 5 /2.5~3.0초 미만 | 눈 → 왼손 → 오른손 → 서보 순차 검사 |
| 6 이상 /3초 이상 유지 | 즉시 Stop, 해제 시 시작 동작 없음 |

검사 중에는 SW6을 다시 누르는 순간 정지하고 그 해제로 새 검사를 시작하지 않는다. 부팅·설정 변경 때 이미 눌린 버튼은 먼저 해제한 뒤 새로 눌러야 선택할 수 있다. Nano Stop·새 연결·lease 만료로 취소된 누름도 해제로 재실행하지 않는다.

서보 기본 검사는 한 채널씩 명령 각도90→80→100→90을 적용한 뒤 출력을 끈다. 각도는 PWM 명령값이며 실측 관절 각도가 아니다. `servo_min_us`, `servo_max_us`, `test_span_degrees`로 범위를 설정한다. LED 채널값은32/255, 매트릭스 밝기는1로 제한한다. 모든 검사는 유한 시퀀스이며 부팅·재연결만으로 자동 시작하지 않는다.

`local_tests_enabled=false` 또는 `test_switch=0`으로 로컬 진단 선택을 끌 수 있다. Nano가 연결되지 않아도 새 물리 입력으로 유한 로컬 검사는 가능하다. Nano session이 유효한 동안 시작한 검사에는 host lease도 적용되며 만료·연결 종료 시 정지한다.

## 4. USB 메시지 계약

USB는 개발용 `c0de:cafc`, 제품명 `Pico2 Device Bench`, 시리얼은 공개 RP2350 chip ID다. Nano에서는 `/dev/serial/by-id/` 또는 제공 udev 별칭으로 장치를 선택한다. tty 번호를 고정하지 않는다.

```text
Frame { version:1, session:u64, seq:u32, body:Message }
wire = COBS(Postcard(Frame) || CRC32_ISO_HDLC_LE) || 0x00
```

공통 [protocol crate](../../crates/pico-device-protocol/README.md)를 양쪽에서 사용한다. decoded 최대512바이트, wire 버퍼520바이트이며 초과 길이·CRC 오류 프레임은 버리고 다음 구분자로 복구한다. CDC에는 ASCII 진단 로그를 섞지 않는다.

| Nano→Pico | Pico→Nano |
| --- | --- |
| Hello | HelloReply·Ack |
| KeepAlive, GetStatus | Ack·Status |
| Configure | Ack 또는 설정 거부 |
| RunTest | Ack·TestEvent·Status |
| Stop | 출력 정리 후 Ack·Status |
| Bootloader | 출력 정리 후 Ack, ROM 진입 요청 |
| 물리 터치 | Touch 이벤트·Status |

새 session은 이전 검사를 취소한다. session·sequence로 중복 명령의 재실행과 오래된 요청을 막는다. KeepAlive 기본200ms, 만료1초이며 Nano 연결이 끊긴 뒤 과거 검사를 재전송하지 않는다. CRC와 유효한 스키마로 수신한 Stop은 일반 동작 대기열보다 먼저 처리한다.

`Ack`는 요청 수락·거부를 뜻한다. `TestEvent`의 `done=true,fault=false`만 자연 종료이며, 중단된 시퀀스는 `done=true,fault=true`로 완료 성공과 구분한다. 드라이버 오류 비트는 `Status.faults`에 따로 둔다. 어느 경우에도 PWM/SPI/PIO 명령 완료를 물리 위치·광학 점등 계측으로 해석하지 않는다.

## 5. 빌드와 PC 업로드

저장소 루트 PowerShell에서 로컬 Rust1.90을 사용한다.

```powershell
. .\firmware\Use-LocalRust.ps1
.\firmware\Build-PicoDevice.ps1
cargo build --release --locked --manifest-path tools/pico-device-bench/Cargo.toml
```

UF2는 `firmware/pico2-device-bench/dist/`에 생성한다. 실제 보드에 설치할 때만 현재 COM 포트를 확인해 아래 명령을 실행한다. COM11은 예시다.

```powershell
.\firmware\Flash-Pico.ps1 -Firmware Device -Port COM11
```

이 작업은 기존 벤치 이미지를 통합 진단 이미지로 교체한다. 새 PID로 인해 COM 번호가 바뀔 수 있으므로 `list`로 다시 확인한다. 현재 이미지가 멈춰 소프트웨어 부트로더 요청을 처리할 수 없을 때는 기존 BOOTSEL 복구 경로를 사용한다.

이미지·현재 포트·ROM 확인 순서와 호환 범위는 [USB 자동 업로드](Pico_USB_자동업로드.md)를 따른다. 이번 작업에서는 실제 USB 포트를 열거나 flash를 쓰지 않았다.

## 6. Nano 실행과 프로세스 간 통신

Nano의 Rust1.90 및 네이티브 링커 환경에서 빌드한다. Windows에서 만든 실행 파일을 Nano에 복사해 실행하지 않는다.

```bash
cargo +1.90.0 build --release --locked --manifest-path tools/pico-device-bench/Cargo.toml
```

`bridge`가 장치를 한 번만 열고 상태와 이벤트를 NDJSON으로 출력한다. 같은 포트를 별도 CLI로 동시에 열지 않는다. 다른 Nano 프로세스는 loopback UDP 제어 경로로 status·test·stop·configure를 요청한다. 수신 주소는 loopback으로 제한하며 외부 네트워크 서버를 시작하지 않는다.

기본 설정 파일의 `left_segments`·`right_segments`는 `[4,4,10]`이다. 구간 길이·터치 간격·진단 버튼·서보 범위를 같은 설정에 모으고, 동작 중 설정은 거부한다. 실제 CLI 문법·설정 파일·udev 규칙·수동 systemd 실행 방법은 [Nano/PC 도구 안내](../../tools/pico-device-bench/README.md)를 따른다. 서비스 파일을 제공해도 자동 enable이나 시스템 설정 변경을 수행한 것은 아니다.

이 USB 진단 계약은 모듈 시험·터치 상태 반환 범위다. 카메라·음성·일반 서보 목표 자세와 전체 애플리케이션 controller는 기존 아키텍처의 후속 단계다.
