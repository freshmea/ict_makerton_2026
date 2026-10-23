# Pico 2 USB 재업로드

통합 진단 이미지는 `picotool-v1` reset 인터페이스와 binary `Bootloader` 요청을 제공한다. 정상 실행 중인 새 이미지에서는 BOOTSEL 버튼 없이 호스트 도구로 출력을 정리한 뒤 ROM에 진입할 수 있다. 실제 새 이미지의 USB 재업로드는 이번 작업에서 실행하지 않았다.

## Windows

저장소 루트에서 로컬 Rust를 적용하고 빌드한다.

```powershell
. .\firmware\Use-LocalRust.ps1
.\firmware\Build-PicoDevice.ps1
cargo build --release --locked --manifest-path tools/pico-device-bench/Cargo.toml
& .\tools\pico-device-bench\target\release\pico-device-bench.exe list
```

USB 포트를 점유한 브리지·터미널은 먼저 종료한다. 실제 현재 포트를 지정한다. COM11은 예시다.

```powershell
.\firmware\Flash-Pico.ps1 -Firmware Device -Port COM11
```

스크립트는 소스 UF2의 SHA-256·family·flash 주소·블록을 확인한다. 현재 이미지에 맞는 CLI의 Status에서 protocol·OE HIGH·reset 기능을 확인한 뒤 Bootloader를 요청한다. **이전 이미지의 CLI가 없으면 자동 선택해 명령을 보내지 않고 종료한다.** 새 도구의 NDJSON `list`와 기존 벤치의 ASCII `list`를 모두 읽는다. 실제 ROM 장치가 하나인 경우만 picotool2.3.1로 선택·쓰기·검증·실행하며, 마지막에 새 `c0de:cafc` Status를 확인한다.

CLI `STATUS ...`와 `OK BOOTLOADER`는 업로더 호환용 호스트 stdout이다. 새 이미지의 실제 USB CDC에는 ASCII 명령을 쓰지 않는다. `OK BOOTLOADER`는 장치 요청 Ack 확인이며 ROM 열거·flash 검증 결과와 구분한다.

이미 ROM 드라이브가 나타나거나 이전 이미지가 reset 기능을 제공하지 않는 최초 설치에는 다음 명시적 경로를 쓴다.

```powershell
.\firmware\Flash-Pico.ps1 -Firmware Device -Bootsel
```

이 모드는 정확히 한 개 RP2350 ROM 장치를 요구한다. picotool 접근이 안 되고 RP2350 `INFO_UF2.TXT`가 하나만 마운트된 경우 검증한 UF2 복사를 허용하지만 flash readback 검증으로 보고하지 않는다. 실행 로그는 매번 새 `tmp/pico-flash/` 폴더에 남긴다. 손상·정지한 펌웨어에는 물리 BOOTSEL 복구가 필요할 수 있다.

## Nano

Nano clone `/home/jetson/ict_makerton_2026`에 Linux용 설치·빌드·업로드 스크립트를 추가했다. 준비와 쓰기를 구분해 실행한다.

```bash
cd /home/jetson/ict_makerton_2026
bash firmware/setup-linux.sh
bash firmware/build-pico-device.sh
bash firmware/flash-pico.sh --check
# 이미 ROM BOOTSEL에 진입한 상태에서 (원격 Reset 또는 버튼)
bash firmware/flash-pico.sh --bootsel
# 통합 이미지 설치 후의 업데이트
bash firmware/flash-pico.sh --port /dev/pico-device
```

현재 연결된 `c0de:caff`는 NeoPixel 변형이며, 통합 CDC 명령을 보내지 않는다. 이 이미지는 picotool USB Reset을 지원하며 실제 버튼 없는 ROM 정보 조회·앱 복귀를 확인했다. `--bootsel`은 이미 ROM에 들어간 상태를 뜻하며 물리 버튼을 요구하는 옵션이 아니다. 원격 진입 명령·권한·도구 버전·flash 백업·readback 검증 범위는 [Nano Linux 펌웨어 업데이트](Jetson_Nano_Linux_펌웨어_업데이트.md)를 따른다.

실행·설정은 [통합 도구 README](../../tools/pico-device-bench/README.md), 결과는 [초기·후속 검증 범위](Jetson_Nano_작업_종합기록_2026-10-24.md)을 따른다.
