# Pico 통합 장치 시험·Nano USB 브리지

2026-10-24 확장: 현재 호스트는 **protocol v2**와 Arm/Pose/Light/Eyes를 지원한다. 운영 제어는 [Rust runtime](../../software/README.md)의 Unix/lease 경로로 수행하며 진단 대시보드는 비활성이다. [전체 기능·구동 보정](../../doc/software/전체기능_구현과_운영.md)을 먼저 읽는다. 아래 초기 실물 기록과 현재 v2 검증을 구분한다.

Rust Tokio와 tokio-serial로 Pico의 단일 USB 연결을 소유하고, Nano의 다른 프로세스에 loopback UDP JSON IPC를 제공하는 임시 시험 도구다. 왼손·오른손 NeoPixel 기본 구간은 각각 `[4,4,10]`, 손당18개·총36개다. 매트릭스·각 손 NeoPixel·서보의 유한 시험과6개 터치의 상태·누른 시간·500ms 간격 횟수·2초 창 누름 횟수를 전달한다. 최종 Nano 영상·음성 앱 전체를 구현한 것은 아니다.

**2026-10-24 Nano에서 native 빌드·통합 `c0de:cafc` USB 왕복·양손 LED와 서보 시험 완료 및 사용자 실물 점등/움직임 확인을 확보했다.** [대시보드 검증](../../doc/software/Jetson_Nano_장치_대시보드.md)을 따른다. 현재 스위치·매트릭스는 미연결이며 전원 부하·축 보정·체계적인 실물 장애 회귀는 남아 있다. Windows 빌드·가짜 직렬 스트림/UDP 검사와 aarch64 정적 검사의 결과는 실제 Pico/Nano 시험과 구분해 [후속 native 검사 원본](../../doc/software/board-info/2026-10-24/dashboard-rust-tests-build.log)에 기록한다.

2026-10-23 호스트 검사8개, Windows release 빌드, `aarch64-unknown-linux-gnu` 대상 `cargo check`를 통과했다. aarch64 검사는 최종 ELF 링크나 Nano glibc·실행 검증이 아니다. 이는 초기 검증 기록이다. 후속 Hello 신원 응답 유실 재시도 수정 뒤 Nano의 호스트 9개 검사가 통과했다. 구동 명령은 재전송하지 않는다.

## 통신과 하나의 USB 소유자

- 장치 CDC는 ASCII 로그 없이 `COBS(Postcard(Frame) + CRC32_LE) + 0x00` 프레임만 전송한다. 버전2·디코딩512바이트·전송520바이트 상한은 [공통 프로토콜](../../crates/pico-device-protocol/README.md)을 따른다.
- 연결마다 새 무작위64비트 session과 증가하는 seq를 사용한다. session은 인증 토큰이 아니다. HelloReply의 버전·session·seq를 확인하며 Ack는 프레임 seq와 `request_seq`를 모두 대조한다.
- **새 Hello는 이전 세션과 진행 중인 로컬 시험도 정지시킨다.** 단독 `status`도 새로 USB를 열고 Hello를 보내므로 단순 무영향 조회가 아니다. 브리지 실행 중에는 별도 USB CLI를 열지 않고 `ctl status`나 UDP IPC를 사용한다.
- 브리지는200ms마다 KeepAlive를 보내고 장치의 약100ms Status push와 Touch/TestEvent를 수신한다. USB 오류나 종료 시 Stop Ack를 시도하고 자동 재접속·과거 Test 재전송은 하지 않는다. 재시작은 수동이며 새 Hello·Configure 이후에도 Test를 자동 실행하지 않는다.
- `local_tests_enabled=true`가 기본이다. 현재 대시보드 배포는 스위치 미연결이므로 `false`, `test_switch=0`을 사용한다. 브리지가 연결된 유휴 상태에서도 SW6 로컬 모듈 선택·유한 시험을 허용한다. 동작 중 SW6는 정지 역할을 하며 로컬 시험 진행 중 원격 Test가 Busy를 반환하면 기존 시험을 임의 재시작하지 않는다.

브리지 stdout은 NDJSON이다. `event=status/touch/test_event/ack` 등에 session16진수 문자열·호스트 UTC Unix ms·호스트 단조 경과 ms를 포함한다. 터치 이벤트의 장치 uptime과 event_seq, Status의 dropped_events는 별도다. 반복 KeepAlive 성공 Ack는 출력에서 생략한다. 입력 이벤트 유실 가능성은 최신6개 TouchState 스냅샷과 dropped_events로 확인하며 모든 누름 이벤트가 전달됐다고 보장하지 않는다.

## Windows 호스트 빌드

저장소 루트 PowerShell에서 실행한다.

```powershell
. .\firmware\Use-LocalRust.ps1
cargo test --locked --offline --manifest-path tools/pico-device-bench/Cargo.toml
cargo build --release --locked --offline --manifest-path tools/pico-device-bench/Cargo.toml
& .\tools\pico-device-bench\target\release\pico-device-bench.exe --help
```

`list`는 USB 포트를 나열하며 열지 않는다. 결과는 NDJSON이다. 다른 직접 USB 명령은 항상 포트를 명시한다. COM11은 예시이며 설치·재연결 후 달라질 수 있다.

```powershell
& .\tools\pico-device-bench\target\release\pico-device-bench.exe list
& .\tools\pico-device-bench\target\release\pico-device-bench.exe --port COM11 status
& .\tools\pico-device-bench\target\release\pico-device-bench.exe --port COM11 configure --config .\apps\device-dashboard\pico-config.json
& .\tools\pico-device-bench\target\release\pico-device-bench.exe --port COM11 test matrix
& .\tools\pico-device-bench\target\release\pico-device-bench.exe --port COM11 test left
& .\tools\pico-device-bench\target\release\pico-device-bench.exe --port COM11 test right
& .\tools\pico-device-bench\target\release\pico-device-bench.exe --port COM11 stop
```

`test servos`와 `test all`도 지원하며 실제 서보를 움직이므로 해당 명령을 직접 선택했을 때만 요청한다. 기본 시험 폭은 중심90도 주변±10도의 명목 목표값이며 물리 각도를 보정한 결과가 아니다. 개별 테스트는 해당 Module의 `done=true/fault=false`, All은 마지막 **Module All**의 완료를 기다린다. 중간 단계 완료만으로 All 성공을 판정하지 않는다. `fault=true`는 중도 정지·취소도 포함하므로 반드시 부품 고장을 뜻하지 않는다. 최대180초 뒤에는 실패로 종료하고 Stop을 시도한다.

직접 `status`에는 업로더 호환용 `STATUS protocol=pico-device-v2 bootloader=picotool-v1 oe_high=...` 한 줄도 출력한다. `bootloader`는 Stop의 실제 장치 Ack·OE HIGH Status 뒤 Bootloader 요청 Ack를 받은 경우에만 `OK BOOTLOADER`를 추가 출력한다. **이 ASCII는 호스트 stdout에만 있으며 CDC로 보내지 않는다.** ROM 식별·쓰기 성공은 별도 업로드 절차에서 확인한다.

## Nano에서 브리지와 다른 프로세스 사용

Linux에서도 `--port`는 필수다. `/dev/ttyACM0`를 고정값으로 사용하지 않고 `/dev/serial/by-id/...` 또는 아래 udev 별칭을 선택한다. 열거된 이름과 별칭을 canonicalize해 비교하고 USB VID/PID `c0de:cafc`를 확인한다. libudev 없이 메타데이터가 Unknown이면 canonical tty의 `/sys/class/tty/<tty>/device` 부모에서 idVendor/idProduct를 읽어 검증한다. 값을 확인하지 못하거나 다른 USB 장치면 열지 않는다.

```bash
./pico-device-bench list
./pico-device-bench --port /dev/serial/by-id/YOUR_BOARD bridge \
  --config /home/jetson/ict_makerton_2026/apps/device-dashboard/pico-config.json --listen 127.0.0.1:37920
```

이 프로세스가 USB의 유일한 소유자다. 다른 Nano 프로세스는 다음 명령이나 같은 UDP JSON을 사용한다.

```bash
./pico-device-bench ctl --addr 127.0.0.1:37920 status
./pico-device-bench ctl --addr 127.0.0.1:37920 test left
./pico-device-bench ctl --addr 127.0.0.1:37920 configure --config /home/jetson/ict_makerton_2026/apps/device-dashboard/pico-config.json
./pico-device-bench ctl --addr 127.0.0.1:37920 stop
```

| UDP 요청 | 동작 |
| --- | --- |
| `{"cmd":"status"}` | 같은 USB 세션에서 GetStatus와 Ack를 확인해 최신 스냅샷 반환 |
| `{"cmd":"test","module":"matrix"}` | 유한 시험 요청의 Ack와 최신 Status 반환. module은 matrix/left/right/servos/all |
| `{"cmd":"stop"}` | 정지 완료 Ack와 최신 Status 반환 |
| `{"cmd":"configure","config":{...}}` | 완전한 typed DeviceConfig 검증·적용 Ack와 최신 Status 반환. 활성 중 Busy는 그대로 반환 |

서버는 `127.0.0.1`·`::1` 등 loopback에만 bind하며 원격 주소·임의 명령·파일 경로를 받지 않는다. UDP config는 파일 경로 대신 완성된 설정 객체다. 응답 `ok=true`는 요청 Ack/조회 성공이며 Test의 물리 완료를 뜻하지 않는다. 완료·진행·Touch 상태는 브리지 NDJSON으로 읽는다. 응답 Status에는 호스트 수신 시각·age_ms가 있어 캐시 상태를 구분한다. UDP 응답을 못 받으면 명령을 자동 재전송하지 않는다. UDP 클라이언트 종료 뒤에도 브리지가 lease를 유지하며 유한 시험이 끝나고 무한 서보 운동으로 전환하지 않는다.

장치 Ack·Status를 기다리는 중에도 UDP Stop을 수신해 현재 요청보다 먼저 전송한다. Stop Ack와 새 Status를 확인하면 정지 클라이언트에 응답하고 취소한 원래 요청에는 오류를 반환한다. 대기 중의 다른 명령은 Busy로 거부하며 나중에 자동 실행하도록 쌓지 않는다. Hello와 Stop 앞에는 빈0구분자를 보내 이전 부분 프레임의 경계를 회복한다. Stop 우선 처리도 USB 포트를 여는 태스크는 하나다.

## 개별 서보 IPC

새 펌웨어의 `ServoDriver` 메시지를 NDJSON `event=servo_driver`와 상태 스냅샷의 `servo_driver`로 전달한다. 구형 펌웨어에서는 null이며 새 명령을 자동으로 시도하지 않는다. 진단의 `probes[0/1]`은 0x40/0x41에 대응하고 0=미검사, 1=유효 레지스터 응답, 2=ACK 없음, 3=40ms 시간 초과, 4=기타 버스 오류, 5=MODE2 예약 비트 불일치다. `selected_address=0`이면 주소가 선택되지 않았다. 상태 수신은 Arm이나 서보 이동을 수행하지 않는다.

2026-10-24 대시보드의 개별 제어를 위해 `{"cmd":"servo","channel":0,"target_cdeg":9000,"move_ms":500}`와 `{"cmd":"servo_probe"}`를 추가했다. channel은 0~5이고 명령 범위 밖 값과 알 수 없는 필드는 거부한다. 새 펌웨어가 `Capabilities.single_servo=true`를 알린 경우에만 전송하므로 구형 펌웨어에 확장 명령을 보내지 않는다. Servo는 유효한 Arm과 lease가 필요하며 ACK 수락과 `Applied.kind=4` 완료는 구분한다. probe는 출력 정지 상태의 PCA 초기화만 요청한다. 브리지가 browser lease를 관리하지는 않으며 대시보드가 이를 만료·정지 처리한다. [사용법·현재 하드웨어 제한](../../apps/device-dashboard/README.md#서보별-각도-슬라이더)을 따른다.

## 설정과 터치 수치

현재 배포 설정은 [pico-config.json](../../apps/device-dashboard/pico-config.json)이다. 스위치 미연결에 맞춰 SW6 기능을 끄며 공통 기본값과 구분한다. CLI 파일에서는 필요한 키만 덮어쓸 수도 있고 누락값은 기본값을 사용한다. 알 수 없는 키·잘못된 길이·범위는 거부한다. 손당 총1~36개, 극성 마스크 하위6비트, local test switch0~6, hold/window100~60000ms, 서보500~2500µs 내부 범위와 min<max, 시험 폭1~30도 등은 공유 validate를 따른다.

`hold_interval_ms=500`은 누르고 있는 동안의 구간 횟수이며, `press_window_ms=2000`의 누름 횟수와 다른 값이다. Touch의 Pressed/Interval/Released/WindowClosed와 최신6개 TouchState를 그대로 전달한다. 손당 구간을18개보다 크게 바꿨다고 전원 공급까지 검증된 것은 아니다. **30개 초과 NeoPixel 추가 전원 공급·주입 실부하 시험은 별도 TODO**다.

## Nano native 빌드와 수동 서비스 파일

Nano에서는 저장소의 공통 `crates/pico-device-protocol`도 함께 둔다. 독립된 tools 폴더만 복사하면 경로 의존성이 누락된다. Linux aarch64 환경에서 Rust1.90을 준비한 뒤 저장소 루트에서 빌드한다.

```bash
rustup toolchain install 1.90.0 --profile minimal
rustup run 1.90.0 cargo build --release --locked \
  --manifest-path tools/pico-device-bench/Cargo.toml
```

tokio-serial과 serialport의 기본 기능을 끄므로 libudev 설치를 빌드 전제로 두지 않는다. **실제 보드는 Ubuntu20.04.6 / L4T R32.6.1이며 Rust1.90 native 링크·실행을 검증했다.** [환경 설치](../../doc/software/Jetson_Nano_개발환경_설치와_모드전환.md)와 [Linux 빌드·업데이트](../../doc/software/Jetson_Nano_Linux_펌웨어_업데이트.md)를 따른다. Windows/정적 검사만으로 판단한 결과가 아니다.

현재 udev·계정 설정은 [장치 접근 설정 도구](../jetson/configure-device-access.sh)를 따른다. `/dev/pico-device`와 robot-device 그룹 0660 권한을 사용하며 여러 보드는 serial/by-id로 구분한다.

자동 시작은 [대시보드 서비스](../../apps/device-dashboard/300seconds-dashboard.service)가 이 Rust 브리지를 자식 프로세스로 실행하는 방식이다. 예전 문서에서 언급한 별도 `picod.service` 템플릿은 현재 저장소에 없으므로 설치 대상으로 안내하지 않는다. 직접 CLI를 실행하기 전 대시보드를 중지해야 USB 소유자가 충돌하지 않는다. 수동 시험 후에는 대시보드를 다시 시작한다. SIGINT 종료 시 Stop Ack 정리를 시도하며 USB가 끊겨도 과거 Test를 자동으로 재생하지 않는다.
