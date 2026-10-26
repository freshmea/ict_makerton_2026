# Pico 2 통합 장치 진단 펌웨어

## 코드 이해와 HTML 문서

처음 읽는 경우 [설계·실행·데이터 흐름 해설](docs/architecture.md), [사용 사례와 변경 지점](docs/use-cases.md), [Cargo HTML 생성·탐색 방법](docs/cargo-doc.md) 순서로 읽는다. API의 한국어 주석과 장치 없이 실행하는 예제도 추가했다.

저장소 루트에서 `./firmware/pico2-device-bench/build-docs.ps1 -Open`을 실행하면 전체 해설을 포함한 라이브러리 HTML을 생성해 연다. 같은 명령이 RP2350 실행부의 태스크·드라이버·Application 내부 API HTML도 별도로 만든다. 장치 동작이나 업로드는 수행하지 않는다.

## 구현과 장치 현황

SW4 확장(2026-10-25): 짧게 누를 때마다 서보 1~4번(CH0~CH3)의 랜덤 팔 패턴 10종을 즉시 전환한다. 기준각 ±12°/최대 24°/초, 약 9초 후 복귀·출력 해제이며 SW3 조명과 함께 사용할 수 있다. [범위·패턴·검증](../../doc/software/SW4_서보팔_랜덤패턴.md).

2026-10-25 적용 완료: **SW3 짧은 누름으로 NeoPixel 랜덤 패턴 10종**을 즉시 전환한다. 각 출력의 바닥4개·팔4개·메인10개(3-4-3)를 구분하며, 유지 중 재선택과 직전 패턴 연속 중복을 막는다. Nano 검사 20개, Pico flash 백업·쓰기·읽기 검증, 대시보드 복구를 완료했고 사용자가 SW3 바닥 점등·패턴 변경을 확인했다. [배치·패턴·검증](../../doc/software/SW3_네오픽셀_랜덤패턴.md).

현재 확장은 **wire v2**의 보정 Arm·6축 목표 보간·고정/주기 조명·표정·Applied와 독립 safety/hardware watchdog을 포함한다. 기존 순차 진단도 유지한다. 기본 서보는 잠그며, 일반 표정 명령은 Arm의 `matrix_installed=true`일 때 수락한다. [전체 기능·운영](../../doc/software/전체기능_구현과_운영.md)과 [실제 계약](../../crates/pico-device-protocol/README.md)을 따른다.

Rust 1.90 / Embassy RP 0.10 / RP2350 Arm secure 대상의 통합 벤치 이미지다. 부팅 시 서보 OE를 HIGH로 두고 양손 NeoPixel을 검게 지우며 MAX7219를 blank/shutdown 한다. 부팅이나 USB 재연결만으로 검사를 시작하지 않는다. 기존 개별 벤치 이미지와 달리 USB CDC 데이터는 **바이너리 전용**이며, `tools/pico-device-bench` 호스트를 사용한다.

## 핀과 기본 배치

| 용도 | Pico GPIO | 물리 핀 / 설정 |
| --- | --- | --- |
| PCA9685 SDA / SCL | GP4 / GP5 | 6 / 7, I2C0 100kHz, 0x40/0x41 단일 응답 선택 |
| PCA9685 OE | GP12 | 16, HIGH=출력 차단 |
| 터치 SW1~SW6 | GP6~GP11 | 9,10,11,12,14,15, PullNone |
| 왼손 NeoPixel DIN | GP16 | 21, PIO0 SM0 / DMA0, GRB 800kHz |
| 오른손 NeoPixel DIN | GP17 | 22, PIO0 SM1 / DMA1, GRB 800kHz |
| MAX7219 CLK / DIN / CS | GP18 / GP19 / GP20 | 24 / 25 / 26, SPI0 mode0 1MHz |

PCA 서보 1~6은 CH0~CH5를 쓴다. 실물 관찰로 확인한 MAX7219 연결은 **기기 본체 기준 왼쪽 눈(가까운/첫 번째) → 오른쪽 눈(먼/두 번째)** 순서다. SPI는 먼 오른쪽 눈 데이터를 먼저 전송한다. intensity는 1, decode는 0, scan-limit는 7, display-test는 0이다.

### 기기 기준 눈 좌우와 90도 장착 보정

현재는 **기기 본체 기준 왼쪽 눈·오른쪽 눈**으로 통일한다. 정면에서 보는 사람의 오른편이 기기의 왼쪽 눈이다. 실물 윙크 관찰로 가까운 모듈이 기기 왼쪽 눈임을 확인했으며, 이 모듈의 LED 정면 기준 반시계 방향 90도 장착과 시계 방향 90도 출력 보정은 유지한다. 먼 모듈은 기기 오른쪽 눈이며 회전하지 않는다.

논리 좌표는 위에서 아래로 8행, 각 행의 bit 7이 그림의 왼쪽이다. 논리 `left/right`는 기기 본체의 눈을 뜻한다. `matrix_mount_frame`은 **`near = CW90(logical.left)`, `far = logical.right`**로 물리 출력 버퍼를 만든다. `Matrix::frame`에서 SPI 전송 직전에 한 번만 적용하므로 L/R 식별 진단과 v2 `SetEyes`가 같은 매핑을 사용한다. 정면 미리보기의 화면 왼편에는 논리 right를, 화면 오른편에는 논리 left를 그린다. 호스트에서 실제 전송 데이터를 중복 교환하거나 회전하지 않는다. 부팅/Stop의 blank 프레임은 그대로 blank다.

비대칭 L 도형의 회전 방향·오른눈 유지, 행/열 스캔, blank 종료를 단위 검사로 확인한다. 실제 업로드·표시 결과는 [대시보드 후속 검증 기록](../../doc/software/Jetson_Nano_장치_대시보드.md)을 따른다.

NeoPixel은 손마다 최대 36픽셀 버퍼를 가지며 기본 세그먼트는 각각 `[4,4,10]`, 한 손 18개/양손 총 36개다. `Configure`로 각 손 3개 세그먼트를 변경한다. 실제 사용 길이 뒤의 36픽셀까지는 매번 검정으로 전송한다. 진단과 SW3 패턴의 RGB 각 채널은 최대 32/255이며 일반 `SetLight` 경로는 brightness 상한에 따라 최대 64/255다. RGBW는 지원하지 않는다. GPIO 3.3V 직결의 동작 여유는 LED 전원/배선/개체에 영향을 받으며 실제 발광은 실물에서 확인한다.

## 개별 서보 제어 확장

2026-10-24 wire v2 메시지 enum 끝에 `SetServo { channel, target_cdeg, move_ms }`, `Capabilities { single_servo }`, `CheckServoDriver`를 추가했다. 기존 메시지의 Postcard 태그는 유지한다. Hello/GetStatus 때 capability를 보내며 호스트는 이를 확인한 뒤 확장 명령을 전송한다.

`SetServo`는 보정 Arm·lease·PCA 정상 상태를 요구하고 CH0~CH5 중 선택한 채널만 보간한다. 활성 이동 중 새 요청은 Busy이며 완료는 `Applied.kind=4`로 보고한다. 처음에는 PCA 전체 출력을 끈 뒤 선택 채널만 켠다. 이후 다른 채널은 이전 PWM을 유지한다. Stop은 모든 채널을 끄고 OE를 HIGH로 둔다. `CheckServoDriver`는 idle·미Arm·OE HIGH 상태에서만 초기화하며 성공할 때만 PCA fault를 지운다. [대시보드 사용법·실기 제한](../../apps/device-dashboard/README.md#서보별-각도-슬라이더)을 참고한다.

재부팅 후 PCA 오류 진단 확장은 `ServoDriver` 상태 메시지를 enum 끝에 추가한다. 출력 차단 상태에서 0x40/0x41의 MODE1·MODE2를 각각 읽고 MODE2 예약 비트를 검사한다. 정확히 한 주소만 유효하면 그 주소를 선택하며 두 주소가 모두 응답하면 선택하지 않는다. ALLCALL 0x70을 구동 주소로 사용하지 않는다. 주소별 응답·ACK 없음·40ms 시간 초과·기타 버스 오류·레지스터 불일치, SDA/SCL의 디지털 입력, 초기화 여부와 마지막 쓰기 오류를 보고한다. HIGH/LOW는 전압계 측정이 아니다. 부팅 시에도 주소 확인 후 FULL_OFF만 쓰며 PWM을 시작하지 않는다. 자세한 상태는 Hello/GetStatus 및 명시적 driver probe에서 제공한다. 이 소스 확장의 실기 업로드·관측 여부는 해당 실행의 검증 기록과 구분한다.

## SW6 로컬 검사

기본 SW6는 GP11이며 다른 5개 입력과 같이 시간·count 상태를 보고한다. 입력은 5ms 샘플링/30ms 디바운스를 거친다. 기본 HIGH=눌림이며 active-low 센서는 `touch_active_low_mask`로 뒤집는다. 정확한 터치 모듈 품번은 미확정이다. 연결하지 않은 부동 입력의 이벤트를 정상 센서 판정에 사용하지 않는다.

대기 상태에서 SW6를 눌렀다 놓으면 **안정된 눌림부터 센 500ms 구간 수**로 검사 모듈을 고른다.

| hold interval count | 검사 |
| --- | --- |
| 0 또는 1 | 양쪽 눈 매트릭스 |
| 2 | 왼손 NeoPixel |
| 3 | 오른손 NeoPixel |
| 4 | 서보 6개 |
| 5 | 눈 → 왼손 → 오른손 → 서보 순차 |
| 6 이상 | 즉시 전체 정지, release 소비 |

검사 중 SW6를 누르면 전체 정지하며 놓을 때 새 검사를 실행하지 않는다. 부팅 중 눌림, 새 Hello, Stop, 설정 변경, lease 만료로 취소된 hold는 **실제 raw 입력을 안정적으로 30ms 해제한 뒤의 새 누름**부터 다시 수락한다. 설정이 디바운서의 눌림 상태를 초기화해도 held-release로 재실행하지 않는다.

USB가 없어도 로컬 검사는 유한하게 끝난다. Nano가 상태를 구독 중일 때도 idle의 SW6 검사를 허용한다. 활성 USB 세션이 있으면 로컬 검사에도 같은 1초 lease를 적용하며, 연결 해제/lease 만료 시 정지한다. `local_tests_enabled=false` 또는 `test_switch=0`으로 로컬 선택을 끌 수 있다.

## 검사 내용과 종료

- 눈: 왼쪽 L / 오른쪽 R 구분, 8행, 8열, checker, 눈 패턴을 약 9.8초 동안 표시한 뒤 blank/shutdown 한다.
- NeoPixel: 세그먼트마다 R/G/B를 표시하고 전체 사용 픽셀을 한 점씩 이동한 뒤 소등한다. 기본 한 손 약 4.7초다.
- 서보: 1~6을 한 개씩 명령상 `90 → 80 → 100 → 90`으로 각 500ms 구동하고 채널을 끈다. 기본 펄스 설정은 1000~2000µs, 시험 span은 10이다. 이 각도는 명령 라벨이며 실제 회전각/관절 위치 피드백이 아니다. 끝나면 PCA all-off와 OE HIGH를 적용한다.
- All: 위 네 검사를 순차 실행하며 기본 약 31초다. 동시에 여러 서보를 활성화하지 않는다.

STOP 요청은 RX가 version/CRC를 확인한 뒤 session/sequence와 무관하게 OE를 즉시 HIGH로 하고 generation을 바꾼다. 제어 루프는 두 NeoPixel의 black frame, MAX7219 blank/shutdown, PCA all-off를 완료한다. I2C는 요청당 40ms timeout을 두며 await 뒤에도 취소/lease를 재확인하고 서보 OE를 연다.

`TestEvent { done:true, fault:false }`만 자연 완료다. 정지·연결 해제·lease 만료 등 중단은 `done:true, fault:true`다. `All` 내부 모듈의 완료 이벤트와 최종 `module:All` 완료를 구별한다. `Status.faults`는 별도 하드웨어 오류 latch로 bit0=PCA I2C, bit1=MAX7219 SPI 전송 오류이며 USB Stop만으로 오류 비트를 지우지 않는다. LED 발광·매트릭스 표시·실제 각도는 이 통신 보고만으로 확인되지 않는다.

CPU panic은 OE HIGH를 유지하지만 이미 래치된 LED/매트릭스는 남을 수 있다. 이 벤치의 소프트웨어 정지는 전원 차단 장치나 독립 안전회로를 대신하지 않는다.

## USB / Nano 계약

USB VID:PID는 `c0de:cafc`, product는 `Pico2 Device Bench`, serial은 RP2350 public chip ID의 대문자 16진 16자리다. OTP는 읽기만 한다. crate 내부 `src/picotool_reset.rs`가 picotool reset 인터페이스와 Windows WinUSB 자동 바인딩용 MS OS 2.0 descriptor를 등록한다. 바이너리 `Bootloader`도 같은 출력 정리 경로를 사용한다. **이번 정리 전송이 성공했을 때만** Ok Ack 후 150ms 전송 시간을 두고 ROM BOOTSEL로 이동한다. 이번 정리가 실패하면 Fault Ack 후 앱에서 정지 상태를 유지하며 과거의 fault latch만으로 정상 정리 후 ROM 진입을 막지는 않는다.

reset 인터페이스는 class/subclass/protocol `ff/00/01`이며 [Pico SDK 2.2.0 상수](https://github.com/raspberrypi/pico-sdk/blob/2.2.0/src/common/pico_usb_reset_interface_headers/include/pico/usb_reset_interface.h)와 [picotool 2.3.1의 CLASS/INTERFACE 요청](https://github.com/raspberrypi/picotool/blob/2.3.1/main.cpp#L9465-L9488)에 맞춘다. BOOTSEL request 1, bmRequestType 0x21, 지정 interface, 길이 0인 요청만 수락한다. [SDK MS OS 구현](https://github.com/raspberrypi/pico-sdk/blob/2.2.0/src/rp2_common/pico_stdio_usb/reset_interface.c)의 WINUSB ID와 reset interface GUID를 사용한다. Flash reboot request 2는 지원하지 않으며 activity GPIO/ROM interface disable 옵션은 적용하지 않고 `reset_to_usb_boot(0,0)`을 호출한다. USB handler에서는 요청 신호만 전달하고 직접 리셋하지 않는다. 이 새 이미지의 vendor/MSOS 실제 인식은 아직 하드웨어에서 확인하지 않았다.

공유 [프로토콜](../../crates/pico-device-protocol/README.md)은 `COBS(Postcard(Frame) + CRC32) + 0`이다. `Hello`, `KeepAlive`, `GetStatus`, `Configure`, `RunTest`, `Stop`, `Bootloader`를 사용한다. 세션 0은 원격 실행에 사용하지 않는다. 요청 응답 Frame.seq와 Ack.request_seq는 요청 seq를 그대로 반환하며 push 이벤트는 독립 이벤트 sequence를 사용한다. GetStatus는 Status와 Ack 둘 다 보낸다.

호스트는 200ms마다 KeepAlive를 보내며 장치는 마지막 새 Hello/KeepAlive부터 1초를 lease로 본다. 같은 session/seq 요청은 최근 8개 결과를 중복 응답하고 재실행하지 않는다. 캐시 밖 오래된 sequence는 거부한다. 같은 Hello 중복은 lease를 연장하거나 검사를 다시 시작하지 않는다. 새 세션 Hello는 이전 동작을 정지한다. CRC가 잘못되거나 알 수 없는 version의 프레임은 동작을 시작/정지하지 않는다.

입력 전용 task, USB RX/TX task, 장치 제어 루프를 분리한다. telemetry 송신 큐가 차면 제어를 기다리게 하지 않고 dropped_events를 증가시킨다. 약 100ms마다 6개 TouchState와 raw/pressed mask가 들어 있는 Status를 보내 누락 이벤트 이후 현재 상태를 복구한다. USB가 없는 로컬 실행의 telemetry는 보관/재생하지 않는다. `Configure`는 idle에서만 수락하며 RAM 설정이라 전원 재시작 시 기본값으로 돌아온다. Ack는 설정 요청 수락이며 터치 설정 적용은 다음 5ms 입력 루프에서 이루어진다.

## 빌드와 검증

Nano/Linux에서는 저장소 루트에서 `bash firmware/setup-linux.sh`, `bash firmware/build-pico-device.sh`, `bash firmware/flash-pico.sh --check`를 실행한다. 최초 BOOTSEL 설치와 이후 CDC 업데이트, 실제 검증 범위는 [Nano Linux 업데이트 문서](../../doc/software/Jetson_Nano_Linux_펌웨어_업데이트.md)를 따른다.

```powershell
. .\firmware\Use-LocalRust.ps1
cargo test --manifest-path firmware/pico2-device-bench/Cargo.toml --lib --target x86_64-pc-windows-msvc --locked --offline
cargo build --manifest-path firmware/pico2-device-bench/Cargo.toml --target thumbv8m.main-none-eabihf --release --locked --offline
```

초기 `logs/unit-test.txt`는 heapless 참조 오류가 난 과거 실패 기록이다. 이전 문서의 `unit-test-reset.txt`·`release-build-reset.txt`는 현재 저장소에 없으므로 성공 증거로 링크하지 않는다. 현재 소스 단위 검사 결과는 [2026-10-24 재검증](../../doc/software/board-info/2026-10-24/git-sync-firmware-tests.log), 실제 Linux release 빌드는 [최종 빌드 로그](../../doc/software/board-info/2026-10-24/linux-firmware-setup-and-build-final.log)를 따른다. 2026-10-24에는 [실제 flash](../../doc/software/board-info/2026-10-24/dashboard-pico-flash-result.json)와 [Nano USB·LED/서보 사용자 실물 확인](../../doc/software/Jetson_Nano_장치_대시보드.md)을 확보했다. 후속 연결 점검에서 스위치 6개 눌림·해제와 매트릭스 양쪽 표시·소등을 확인했다. 이번 왼눈 90도 장착 보정의 새 UF2 재업로드·readback·USB 재연결은 [후속 기록](../../doc/software/Jetson_Nano_장치_대시보드.md#왼눈-반시계-방향-90도-장착-보정-펌웨어)을 따른다. 부하·장애 검사는 별도다.
