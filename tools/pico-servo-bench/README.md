# Pico 2 서보 임시 시험 도구

Pico 2의 `servo-bench-v1` USB CDC 펌웨어에만 명령을 보내는 PC용 도구다. Rust CLI가 기본이며, Windows 빌드 도구가 준비되지 않은 경우 Windows PowerShell의 내장 `System.IO.Ports` 드라이버를 사용할 수 있다. Pico 펌웨어 자체는 Rust다.

2026-10-23 Rust 호스트 빌드·인자 검사2개와 실제 USB/I2C 통신·6개 서보 순차 움직임을 확인했다. [RUN-20261023-01](../../doc/software/test-results/2026-10-23/RUN-20261023-01.md)에 설치·업로드·첫 구동, [RUN-20261023-02](../../doc/software/test-results/2026-10-23/RUN-20261023-02.md)에 펄스 범위 확대 시험을 기록했다. 실제 각도·부하·단절 시 정지 성능은 미계측이다. 이 도구는 Nano 서비스와 최종 Postcard/CRC/COBS 통신을 구현하지 않는다.

## 동작과 범위

- `list`는 포트를 나열하기만 한다. 모든 명령에 사용할 포트를 직접 지정한다. 임의 포트를 순회하며 쓰지 않는다.
- 연결 후 `status`의 `protocol=servo-bench-v1`을 확인한 뒤 다른 명령을 전송한다. 잘못된 장치 응답이면 중단한다.
- USB CDC 설정은 115200, 8N1, DTR 활성화다. 1200 baud 리셋을 사용하지 않는다.
- `sweep`를 명시적으로 실행할 때만 `arm`과 `sweep`를 보낸다. 서보 1~6은 PCA 채널 0~5다.
- 동작 중 200ms마다 `ping`을 보낸다. 통신이 끊기면 펌웨어의 1000ms lease timeout이 출력을 정지한다.
- 한 차례 1~6 순서 시험이 끝나면 `stop`을 보내 출력을 끈다. 초기 각도로 자동 복귀하거나 반복하지 않는다.
- 0도/180도는 펄스 범위에 대응하는 **명목 목표값**이다. 기본 1000~2000μs가 현품 서보의 물리적 0~180도를 보장하지 않는다. 서보 모델 사양과 실제 이동을 확인한 뒤 필요할 때만 보정한다.
- SW 정지는 PWM 출력을 막는다. 전원 차단이나 실제 축 위치 피드백을 대신하지 않는다.

## Rust CLI

저장소 루트 PowerShell에서 실행한다. 현재 PC는 전역 Rust1.75를 바꾸지 않고 `.local-tools`에 설치한 Rust1.90을 사용한다. **helper는 현재 셸에 dot-source**해야 한다. 아래 첫 줄의 `. `를 생략하거나 별도 `powershell -File` 프로세스에서 helper만 실행하면 호출한 셸에 환경이 남지 않는다.

```powershell
. .\firmware\Use-LocalRust.ps1
cargo run --release --locked --manifest-path tools/pico-servo-bench/Cargo.toml -- list
cargo run --release --locked --manifest-path tools/pico-servo-bench/Cargo.toml -- --port COM7 status
cargo run --release --locked --manifest-path tools/pico-servo-bench/Cargo.toml -- --port COM7 scan
cargo run --release --locked --manifest-path tools/pico-servo-bench/Cargo.toml -- --port COM7 sweep
cargo run --release --locked --manifest-path tools/pico-servo-bench/Cargo.toml -- --port COM7 stop
```

`COM7`은 이번 시험에서 응답한 포트다. 재연결 후 번호가 바뀔 수 있으므로 장치 관리자와 목록의 USB 식별 정보로 Pico 포트를 다시 고른다. 현재 벤치 펌웨어는 example VID/PID `c0de:cafe`, 제품명 `Pico2 Servo Bench`, 시리얼 `PICO2-SERVO-BENCH-01`을 사용한다. 최종 제품에 할당받은 VID/PID가 아니며, 실제 연결 보드와 protocol 응답을 함께 확인한다. 펌웨어 빌드·UF2 업로드는 [펌웨어 README](../../firmware/pico2-servo-bench/README.md)를 따른다.

이미 빌드한 CLI는 `& .\tools\pico-servo-bench\target\release\pico-servo-bench.exe --port COM7 status`처럼 Cargo 없이 직접 실행할 수 있다.

Rust CLI에서 Ctrl+C를 누르면 STOP을 전송하고 종료한다. USB 자체를 분리한 경우에는 전송이 불가능하므로 펌웨어 timeout으로 정지한다. 포트를 다른 터미널이나 도구에서 동시에 열지 않는다.

기본 펄스 범위는1000~2000µs다. 이번 무부하 시험에서는 회전폭이 작다는 사용자 관찰 뒤 아래 설정을 적용하고 `sweep`를 재실행했다. 사용자는 회전폭 증가와 걸림·이상음 없음을 확인했다. **500~2500µs는 이번 벤치에서 관찰한 범위이며 제조사 보증 최대 범위나 물리0~180도 계측 결과가 아니다.**

```powershell
cargo run --release --locked --manifest-path tools/pico-servo-bench/Cargo.toml -- --port COM7 config --min-us 500 --max-us 2500
cargo run --release --locked --manifest-path tools/pico-servo-bench/Cargo.toml -- --port COM7 status
cargo run --release --locked --manifest-path tools/pico-servo-bench/Cargo.toml -- --port COM7 sweep
```

설정은 RAM에만 저장한다. **Pico 재부팅·전원 재투입 후에는1000~2000µs로 초기화**되므로 Status를 확인하고 필요한 설정을 다시 보낸다. 기본값 복귀 명령은 같은 `config --min-us 1000 --max-us 2000`이다. 도구의 입력 허용 범위500~2500µs를 현품·기구의 사용 허용 범위로 간주하지 않는다. 축별 물리 각도와 부하 상태를 별도로 보정한다.

## Windows PowerShell 대체 실행

아래 경로는 저장소 루트 기준이다. Windows PowerShell 5.1에서 실행하면 별도의 MSVC나 Rust host linker가 필요 없다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/pico-servo-bench/servo-bench.ps1 List
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/pico-servo-bench/servo-bench.ps1 Status -Port COM7
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/pico-servo-bench/servo-bench.ps1 Scan -Port COM7
powershell.exe -NoProfile -ExecutionPolicy Bypass -File tools/pico-servo-bench/servo-bench.ps1 Sweep -Port COM7
```

`Stop` 명령도 같은 형식으로 사용할 수 있다. 단, 포트는 시험 중인 프로그램이 소유하므로 다른 창에서 동시에 열 수 없다. PowerShell 중단 시 `finally`에서 STOP을 시도하며, 중단 방식에 따라 전송이 불가능하면 펌웨어 timeout이 적용된다. 명시적 정지와 정상 종료 확인에는 Rust CLI를 우선한다.

## 진단 결과 해석

1. `Status`: `protocol`, `state`, `address=0x41`, `i2c`, 펄스 범위를 확인한다.
2. `Scan`: `SCAN address=0x41 ...`과 마지막 `SCAN DONE count=...`를 확인한다. 스캔은 서보를 움직이지 않는다.
3. 서보 혼 간섭과 전원 상태를 확인한 뒤 `Sweep`를 실행한다.
4. `EVENT servo=1 ...`부터 `servo=6`, `EVENT DONE`, `OK STOP` 순서의 실제 로그를 저장한다.

명령 접수나 `EVENT DONE` 로그는 PWM 명령을 실행했다는 뜻이다. 실제 각도 도달, 전압 유지, 기계 간섭 여부는 눈으로 확인하고 시험 기록에 별도로 남긴다.
