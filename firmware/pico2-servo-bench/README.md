# Pico 2 / Pico 2 W 서보 임시 시험 펌웨어

RP2350A Arm Cortex-M33 + Rust + Embassy. 무선 기능은 사용하지 않는다. 이 프로그램은 Pico 측 서보 시험에 한정하며 Nano 서비스와 최종 바이너리 통신 규약은 아직 구현하지 않는다.

## 배선 계약

| Pico 물리 핀 | GPIO/기능 | PCA9685 |
|---:|---|---|
| 36 | 3V3 OUT | VCC (로직 3.3V) |
| 3 또는 다른 GND | GND | GND, 외부 전원 OUT−와 공통 |
| 6 | GP4 / I2C0 SDA | SDA |
| 7 | GP5 / I2C0 SCL | SCL |
| 16 | GP12 / active-low 출력 허가 | OE |
| 연결하지 않음 | 외부 컨버터 6V | V+ / 서보 전원 |

- 주소는 A0만 연결한 `0x41`을 기대한다. `scan`으로 실제 응답을 확인한다. `0x70`도 보일 수 있는데 PCA9685 기본 All Call 주소이다. 응답만으로 전압·서보 극성·실제 칩 모델까지 입증되지는 않는다.
- 서보 1~6은 보드에 인쇄된 **CH0~CH5**이다. 보드의 커넥터 위치만 보고 순서를 추측하지 않는다.
- 서보 GND/빨강 V+/신호를 보드 실크와 대조한다. VCC에 6V를 연결하지 않는다. 서보 전류는 Pico/브레드보드를 통해 공급하지 않는다.
- GP12의 초기값은 HIGH이다. **리셋·BOOTSEL·펌웨어 업로드 동안 GPIO가 high impedance이므로 소프트웨어만으로 그 시간의 OE HIGH를 보장하지 않는다.** 이때는 외부 서보 6V를 끄거나 OE를 3.3V에 고정한다. 나중에 GP12로 옮길 때 3.3V 직결선을 먼저 제거한다.
- 실제 PCA 보드의 OE 풀다운 저항을 확인하지 않고 임의의 10kΩ 풀업을 추가하지 않는다. 두 저항의 분압 때문에 유효한 HIGH가 되지 않을 수 있다.
- PWM OFF는 전원 차단이나 기계적 비상정지 장치가 아니다. STOP 후 서보의 유지력 상실/관성 동작은 서보와 하중에 따라 다르다.

## 빌드 환경

- Rust `1.90.0`, target `thumbv8m.main-none-eabihf`.
- `embassy-rp=0.10.0`, `embassy-executor=0.10.0`, `embassy-usb=0.6.0`, `embassy-sync=0.8.0`, `embassy-time=0.5.1`. Git main 의존성은 사용하지 않는다.
- `memory.x`는 Pico 2/Pico 2 W의 4MiB flash에 맞춘다. HAL이 RP2350 secure executable ImageDef를 제공하며 `.start_block`을 링크한다.
- 프로젝트의 `rust-toolchain.toml`은 이 디렉터리에서만 적용된다. 환경 설치는 저장소 공통 설정을 임의로 변경하지 않는다.

```powershell
cd D:\repository\ict_makerton_2026\firmware\pico2-servo-bench
. ..\Use-LocalRust.ps1
cargo build --release --locked
```

이 PC의 전역 Rust 1.75는 변경하지 않고 저장소 내부 `.local-tools/rustup`과 `.local-tools/cargo`에 Rust 1.90을 구성했다. 새 PC에서는 위 helper 환경을 적용한 뒤 다음을 설치한다.

```powershell
rustup toolchain install 1.90.0 --profile minimal --target thumbv8m.main-none-eabihf --no-self-update
cargo install --git https://github.com/JoNil/elf2uf2-rs --rev f14bf2d981772cd9fbe5bac33b685719caac1add --locked --force
```

crates.io의 elf2uf2-rs 2.2.0 릴리스는 RP2040 family만 기록하는 구형 코드이므로 이 빌드에는 사용하지 않는다. RP2350 family 선택을 지원하는 위 원본 커밋으로 고정했다. 저장소 루트에서 `powershell -File firmware/Build-PicoServo.ps1`을 실행하면 빌드·UF2 변환·블록/family 검증과 SHA-256 기록을 수행한다.

출력 ELF: `target/thumbv8m.main-none-eabihf/release/pico2-servo-bench`. 최종 UF2: `dist/pico2-servo-bench.uf2`, 메타데이터: `dist/build-info.json`. 현재 보드의 실제 USB/I2C 시험은 [작업 기록](../../doc/software/test-results/2026-10-23/RUN-20261023-01.md)을 참조한다.

UF2 변환 시 **RP2350 Arm Secure** family ID `0xe48bff59`를 지정한다. RP2040용 UF2 파일을 사용하지 않는다. 업로드는 외부 서보 전원 OFF 상태에서 BOOTSEL로 나타난 RP2350 드라이브를 확인한 뒤 진행한다. 빌드 성공, UF2 생성, USB 펌웨어 응답, 실제 서보 동작은 각각 별도의 검증이다.

## USB CDC 시험 명령

USB 제품명 `Pico2 Servo Bench`, serial `PICO2-SERVO-BENCH-01`, 벤치용 example VID/PID `c0de:cafe`. 최종 제품용으로 할당받은 VID/PID는 아니다. baud 115200 설정을 쓸 수 있지만 실제 USB CDC 전송 속도와는 별개이다. ASCII 한 줄/명령, LF 또는 CRLF로 구분한다. 패킷 분할/합침을 처리한다.

| 명령 | 동작 |
|---|---|
| `status` | `STATUS protocol=servo-bench-v1 state=… servo=… angle=… address=0x41 i2c=… min_us=… max_us=… reason=… oe_high=…` |
| `scan` | disarmed 상태에서 0x08~0x77의 register 0 응답 조사. `SCAN address=0x41 mode1=0x…` 및 `SCAN DONE count=…` |
| `arm` | 출력은 계속 OFF로 둔 채 0x41 초기화/확인. 성공 후 `OK ARM` |
| `ping` | 유효한 호스트 생존 신호 갱신. `OK PING` |
| `sweep` | 명시적으로 arm한 뒤에만 서보 1→6의 0→180 레이블 단회 이동. `OK SWEEP` |
| `stop` | 즉시 GP12 HIGH 및 정지 래치. `OK STOP`, `EVENT STOP reason=host_stop` |
| `config 1000 2000` | disarmed 상태에서 0/180 레이블의 펄스폭 µs 변경. 재부팅 시 기본값 복귀 |

정지 ACK는 OE 비활성화 명령이 적용됐다는 뜻이며 서보가 기계적으로 정지했다는 피드백은 아니다. 서보에 위치/전류 피드백은 없다.

호스트는 `arm` 직후부터 `ping`을 약 200ms 주기로 보낸다. **1000ms 동안 ping이 없거나 USB 연결이 끊기면 OE HIGH로 전환하고 다시 arm할 때까지 동작을 허용하지 않는다.** `status` 요청은 lease를 갱신하지 않는다. 오래된 큐 명령은 generation으로 폐기하므로 STOP 이전에 들어온 sweep이 뒤늦게 실행되지 않는다. STOP은 일반 명령 큐를 통과하지 않는다.

수신·송신·제어는 독립 task이다. USB 송신이 막혀도 제어/STOP 수신을 막지 않는다. 20ms 간격 제어, I²C transaction timeout 40ms, bounded queue를 사용한다. 인터럽트나 하드웨어 자체 정지까지 보장하는 인증된 안전 장치는 아니다.

## 시험 순서와 각도 의미

1. 외부 6V를 끄고 로직 3.3V와 I²C만 연결하여 `status`, `scan`을 확인한다.
2. BOOTSEL/업로드를 완료하고 USB identity, `oe_high=1`을 확인한다. 이 값은 GPIO 출력 레지스터 확인이며 배선 실측은 아니다.
3. 전원 OFF에서 OE를 GP12에 연결한다. 실제 보드의 OE HIGH를 실측하고 서보 극성/허용 전압을 확인한다.
4. 기구 하중 없는 서보 1개로 초기 시험한 뒤 CH0~CH5에 6개를 연결한다.
5. 호스트 도구의 `sweep`을 실행하고 실제 움직임·방향·이상음·전원 전압을 사람이 관찰한다. 처음 시작 위치로의 이동은 서보의 현재 위치를 알 수 없어 순간적으로 시작될 수 있다.
6. `EVENT servo=N angle=0 phase=start`, 180 레이블 도달 이벤트가 순서대로 나오고 마지막 `EVENT DONE`이 나오면 제어 루프의 단회 출력은 완료된다. 이벤트는 실제 각도 도달을 측정한 값이 아니다.

각 서보는 0 레이블에서 약 500ms 대기 → 20ms마다 1도 레이블 증가 → 180 레이블에서 약 500ms 대기 → PWM OFF로 진행한다. 한 번에 한 채널만 활성화한다. 다음 서보를 켜기 전에 이전 채널을 OFF한다. 6개를 약 28초에 걸쳐 한 차례 실행하며 자동 반복하지 않는다.

**기본 펄스폭은 1000~2000µs로 제한한다. 이것이 보유 서보의 실제 0~180°라는 뜻은 아니다.** 실제 180°를 사용하려면 서보의 사양과 기구 한계를 확인하고 채널별 실제 각도를 측정해야 한다. `config`는 500~2500µs 범위 내의 값을 받아들이지만 이 한계가 모든 서보에 안전하다는 의미는 아니다. 보정되지 않은 상태에서 기계적 끝까지 힘으로 밀어붙이지 않는다. PCA 내부 발진기 25MHz 가정, prescale 121로 약 50.0288Hz이며 개체 편차는 아직 실측하지 않았다.

## 검증 범위

순수 펄스 계산과 입력 파서는 아래와 같이 호스트에서 확인할 수 있다. 하드웨어 시험을 대체하지 않는다.

```powershell
cargo test --lib --target x86_64-pc-windows-msvc
```

현재 실제 빌드·업로드·배선·각도 시험 결과는 상위 작업 기록에 남긴다. 이 README의 절차 자체는 시험 완료 증거가 아니다.

## 참고한 공식 자료

- [Embassy RP235x 공식 예제](https://github.com/embassy-rs/embassy/tree/main/examples/rp235x)
- [embassy-rp 0.10.0](https://docs.rs/crate/embassy-rp/0.10.0)
- [NXP PCA9685 데이터시트](https://www.nxp.com/docs/en/data-sheet/PCA9685.pdf)
- [Raspberry Pi Pico 2 핀맵](https://datasheets.raspberrypi.com/pico/Pico-2-Pinout.pdf)
