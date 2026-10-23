# Pico 통합 장치 시험·Nano USB 브리지

Rust Tokio와 tokio-serial로 Pico의 단일 USB 연결을 소유하고, Nano의 다른 프로세스에 loopback UDP JSON IPC를 제공하는 임시 시험 도구다. 왼손·오른손 NeoPixel 기본 구간은 각각 `[4,4,10]`, 손당18개·총36개다. 매트릭스·각 손 NeoPixel·서보의 유한 시험과6개 터치의 상태·누른 시간·500ms 간격 횟수·2초 창 누름 횟수를 전달한다. 최종 Nano 영상·음성 앱 전체를 구현한 것은 아니다.

**이 새 통합 호스트와 `c0de:cafc` 펌웨어의 실제 USB·배선·점등·서보·Nano 실행은 아직 검증하지 않았다.** 기존 개별 벤치의 실물 성공을 이 도구의 성공으로 확대하지 않는다. Windows 빌드·가짜 직렬 스트림/UDP 검사와 aarch64 정적 검사의 결과는 실제 Pico/Nano 시험과 구분해 [validation](validation/2026-10-23/README.md)에 기록한다.

2026-10-23 호스트 검사8개, Windows release 빌드, `aarch64-unknown-linux-gnu` 대상 `cargo check`를 통과했다. aarch64 검사는 최종 ELF 링크나 Nano glibc·실행 검증이 아니다. 통과 후 소스 변경이나 불필요한 반복 검사는 하지 않았다.

## 통신과 하나의 USB 소유자

- 장치 CDC는 ASCII 로그 없이 `COBS(Postcard(Frame) + CRC32_LE) + 0x00` 프레임만 전송한다. 버전1·디코딩512바이트·전송520바이트 상한은 [공통 프로토콜](../../crates/pico-device-protocol/README.md)을 따른다.
- 연결마다 새 무작위64비트 session과 증가하는 seq를 사용한다. session은 인증 토큰이 아니다. HelloReply의 버전·session·seq를 확인하며 Ack는 프레임 seq와 `request_seq`를 모두 대조한다.
- **새 Hello는 이전 세션과 진행 중인 로컬 시험도 정지시킨다.** 단독 `status`도 새로 USB를 열고 Hello를 보내므로 단순 무영향 조회가 아니다. 브리지 실행 중에는 별도 USB CLI를 열지 않고 `ctl status`나 UDP IPC를 사용한다.
- 브리지는200ms마다 KeepAlive를 보내고 장치의 약100ms Status push와 Touch/TestEvent를 수신한다. USB 오류나 종료 시 Stop Ack를 시도하고 자동 재접속·과거 Test 재전송은 하지 않는다. 재시작은 수동이며 새 Hello·Configure 이후에도 Test를 자동 실행하지 않는다.
- `local_tests_enabled=true`가 기본이다. 브리지가 연결된 유휴 상태에서도 SW6 로컬 모듈 선택·유한 시험을 허용한다. 동작 중 SW6는 정지 역할을 하며 로컬 시험 진행 중 원격 Test가 Busy를 반환하면 기존 시험을 임의 재시작하지 않는다.

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
& .\tools\pico-device-bench\target\release\pico-device-bench.exe --port COM11 configure --config .\tools\pico-device-bench\config.example.json
& .\tools\pico-device-bench\target\release\pico-device-bench.exe --port COM11 test matrix
& .\tools\pico-device-bench\target\release\pico-device-bench.exe --port COM11 test left
& .\tools\pico-device-bench\target\release\pico-device-bench.exe --port COM11 test right
& .\tools\pico-device-bench\target\release\pico-device-bench.exe --port COM11 stop
```

`test servos`와 `test all`도 지원하며 실제 서보를 움직이므로 해당 명령을 직접 선택했을 때만 요청한다. 기본 시험 폭은 중심90도 주변±10도의 명목 목표값이며 물리 각도를 보정한 결과가 아니다. 개별 테스트는 해당 Module의 `done=true/fault=false`, All은 마지막 **Module All**의 완료를 기다린다. 중간 단계 완료만으로 All 성공을 판정하지 않는다. `fault=true`는 중도 정지·취소도 포함하므로 반드시 부품 고장을 뜻하지 않는다. 최대180초 뒤에는 실패로 종료하고 Stop을 시도한다.

직접 `status`에는 업로더 호환용 `STATUS protocol=pico-device-v1 bootloader=picotool-v1 oe_high=...` 한 줄도 출력한다. `bootloader`는 Stop의 실제 장치 Ack·OE HIGH Status 뒤 Bootloader 요청 Ack를 받은 경우에만 `OK BOOTLOADER`를 추가 출력한다. **이 ASCII는 호스트 stdout에만 있으며 CDC로 보내지 않는다.** ROM 식별·쓰기 성공은 별도 업로드 절차에서 확인한다.

## Nano에서 브리지와 다른 프로세스 사용

Linux에서도 `--port`는 필수다. `/dev/ttyACM0`를 고정값으로 사용하지 않고 `/dev/serial/by-id/...` 또는 아래 udev 별칭을 선택한다. 열거된 이름과 별칭을 canonicalize해 비교하고 USB VID/PID `c0de:cafc`를 확인한다. libudev 없이 메타데이터가 Unknown이면 canonical tty의 `/sys/class/tty/<tty>/device` 부모에서 idVendor/idProduct를 읽어 검증한다. 값을 확인하지 못하거나 다른 USB 장치면 열지 않는다.

```bash
./pico-device-bench list
./pico-device-bench --port /dev/serial/by-id/YOUR_BOARD bridge \
  --config config.example.json --listen 127.0.0.1:37920
```

이 프로세스가 USB의 유일한 소유자다. 다른 Nano 프로세스는 다음 명령이나 같은 UDP JSON을 사용한다.

```bash
./pico-device-bench ctl --addr 127.0.0.1:37920 status
./pico-device-bench ctl --addr 127.0.0.1:37920 test left
./pico-device-bench ctl --addr 127.0.0.1:37920 configure --config config.example.json
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

## 설정과 터치 수치

[config.example.json](config.example.json)은 공통 DeviceConfig 전체 기본값과 일치한다. CLI 파일에서는 필요한 키만 덮어쓸 수도 있고 누락값은 기본값을 사용한다. 알 수 없는 키·잘못된 길이·범위는 거부한다. 손당 총1~36개, 극성 마스크 하위6비트, local test switch0~6, hold/window100~60000ms, 서보500~2500µs 내부 범위와 min<max, 시험 폭1~30도 등은 공유 validate를 따른다.

`hold_interval_ms=500`은 누르고 있는 동안의 구간 횟수이며, `press_window_ms=2000`의 누름 횟수와 다른 값이다. Touch의 Pressed/Interval/Released/WindowClosed와 최신6개 TouchState를 그대로 전달한다. 손당 구간을18개보다 크게 바꿨다고 전원 공급까지 검증된 것은 아니다. **30개 초과 NeoPixel 추가 전원 공급·주입 실부하 시험은 별도 TODO**다.

## Nano native 빌드와 수동 서비스 파일

Nano에서는 저장소의 공통 `crates/pico-device-protocol`도 함께 둔다. 독립된 tools 폴더만 복사하면 경로 의존성이 누락된다. Linux aarch64 환경에서 Rust1.90을 준비한 뒤 저장소 루트에서 빌드한다.

```bash
rustup toolchain install 1.90.0 --profile minimal
rustup run 1.90.0 cargo build --release --locked \
  --manifest-path tools/pico-device-bench/Cargo.toml
```

tokio-serial과 serialport의 기본 기능을 끄므로 libudev 설치를 빌드 전제로 두지 않는다. **구형 Jetson Nano Ubuntu18.04에서의 도구 설치·최종 native 링크·실행은 아직 검증하지 않았다.** Windows 테스트나 `cargo check --target aarch64-unknown-linux-gnu`의 성공은 그 실물 검증을 대신하지 않는다. 이 작업에서 apt·WSL·Nano 시스템 설정을 실제 변경하지 않는다.

[90-pico-device.rules](90-pico-device.rules)는 dialout/uaccess와 `/dev/pico-device` 별칭용 템플릿이다. 여러 보드를 연결하면 by-id나 serial을 추가한 규칙을 사용한다. [picod.service](picod.service)는 전용 `pico` 계정과 `/etc/default/picod`의 환경값을 쓰는 **수동 시작용** 템플릿이다. 실제 설치 시 운영자가 계정·dialout 권한·바이너리/설정 경로를 준비하고 [환경 예시](picod.env.example)를 맞춘다. 현재 장치에 이 파일을 설치하거나 서비스를 실행하지 않았다.

서비스에는 `[Install]`을 두지 않았고 `Restart=no`다. 운영자가 준비한 뒤 `systemctl start picod`/`stop picod`로만 사용하고 **enable이나 자동 부팅 시작을 설정하지 않는다.** SIGINT를 사용하므로 Stop Ack 정리를 시도한다. USB가 끊기면 명확히 종료하고 과거 Test를 자동으로 재생하지 않는다.
