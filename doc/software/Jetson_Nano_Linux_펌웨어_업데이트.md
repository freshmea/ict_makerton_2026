# Nano에서 Pico 2 펌웨어 빌드·업데이트

대상은 Nano에 사용자가 clone한 `/home/jetson/ict_makerton_2026`과 RP2350 Pico 2의 `pico2-device-bench` 통합 이미지다. Jetson의 BSP·커널·카메라 펌웨어를 갱신하는 도구가 아니다.

## 설치 위치와 소스

- Nano clone HEAD: `6e84286ee4bb49a93ce38bd9c4e4ea9ea33827ab`, origin `https://github.com/freshmea/ict_makerton_2026.git`. 적용 전 작업 트리는 깨끗했다.
- Windows 작업본에는 아직 commit되지 않은 통합 host `src/main.rs`와 crate 내부 reset 모듈 등이 있다. 빌드에 필요한 현재 소스와 Linux 스크립트만 Nano clone에 반영했다. 따라서 HEAD만으로 이번 빌드 소스 전체를 재현할 수 없다. 변경 전 파일은 `/home/jetson/.cache/300seconds-linux-firmware-20261024/clone-baseline/`, 전송 목록·SHA-256은 같은 상위 폴더의 `sync-manifest.json`에 보존한다. 기존 clone을 reset하거나 push하지 않았다.
- Rust 1.90.0: 기존 격리 설치 `$HOME/.local/share/300seconds/rust/`. `thumbv8m.main-none-eabihf` 타깃을 추가한다. 별도 ARM GCC는 필요하지 않다.
- picotool 2.3.1: 저장소의 `.local-tools/linux/picotool/2.3.1/install/bin/picotool`. 소스 commit `2041936441b48a3cc53ae3da9e805229fe8f4e18`, Pico SDK 2.2.0 commit `a1438dff1d38bd9c65dbd693f0e5db4b9ae91779`를 고정한다. Nano aarch64에서 직접 빌드하고 install-info.json에 바이너리 SHA-256을 기록한다.
- SDK의 사전 빌드 보조 ELF를 사용하는 `USE_PRECOMPILED=ON`이다. SDK mbedTLS를 받지 않아 picotool의 이미지 암호화·서명 기능은 설치하지 않는다. USB 읽기/쓰기/검증과 UF2 변환을 사용한다. UF2 SHA-256은 Python으로 별도 계산한다.

공식 [picotool 빌드 안내](https://github.com/raspberrypi/picotool/blob/2.3.1/BUILDING.md), [UF2·load·verify 명령](https://github.com/raspberrypi/picotool/blob/2.3.1/README.md)을 기준으로 했다.

## 재설치·빌드

이 보드에는 개발 패키지가 이미 준비되어 있다. 다른 Ubuntu 보드에서 필요한 패키지는 `build-essential cmake pkg-config libusb-1.0-0-dev libudev-dev libssl-dev git python3 psmisc`다. 기존 Rust 1.90 환경도 필요하다. setup은 일반 개발 사용자로 실행한다.

```bash
cd /home/jetson/ict_makerton_2026
bash firmware/setup-linux.sh
bash firmware/build-pico-device.sh
bash firmware/flash-pico.sh --check
```

setup은 root 설치·자동 시작·전역 PATH 변경을 하지 않는다. 빌드는 firmware crate 디렉터리에서 실행해 `.cargo/config.toml`의 Cortex-M33 설정을 적용한다. 기본 병렬 작업은 2개이며 `PICO_BUILD_JOBS=1`로 줄일 수 있다.

산출물은 다음 위치다. Windows 산출물과 별도 디렉터리를 사용한다.

| 파일 | 용도 |
| --- | --- |
| `firmware/pico2-device-bench/dist/linux/pico2-device-bench.uf2` | RP2350 Arm Secure 이미지 |
| 같은 디렉터리의 `build-info.json` | family `0xe48bff59`, 타깃, 크기·블록 수·SHA-256·변환 도구·Git 상태 |
| `tools/pico-device-bench/target/release/pico-device-bench` | Nano 네이티브 USB host |
| `.local-tools/linux/picotool/2.3.1/install-info.json` | 고정 picotool·SDK commit, aarch64 바이너리 SHA-256 |

`--check`는 UF2·manifest·picotool 해시/버전과 USB sysfs 목록만 확인한다. CDC 명령·리셋·flash 쓰기를 수행하지 않으므로 환경 준비 확인과 실제 업로드 성공을 구분한다.

## USB 권한

`tools/jetson/device_access.py`가 생성하는 기존 `99-z-300seconds-devices.rules`에 RP2350 ROM만 추가했다.

```udev
SUBSYSTEM=="usb", ENV{DEVTYPE}=="usb_device", ATTR{idVendor}=="2e8a", ATTR{idProduct}=="000f", GROUP="robot-device", MODE="0660", TAG+="uaccess"
```

`jetson`과 `pico`는 `robot-device` 그룹이다. 앱 `c0de:cafc`의 `/dev/pico-device`·raw USB와 기존 `c0de:caff`의 `/dev/pico-neopixel` 규칙도 유지한다. `MODE=0666`이나 모든 Raspberry Pi USB를 허용하는 규칙은 추가하지 않는다. 물리 재연결 시 ROM에도 규칙이 적용된다. 그룹을 새로 받은 VS Code Remote SSH 세션은 재접속해야 한다.

이번 보드의 실제 설치본은 `/opt/300seconds/jetson/device_access.py`다. 해당 장치 구성을 확인한 보드에서만 `sudo /opt/300seconds/jetson/configure-device-access.sh`로 재적용한다. 일반 사용자 clone을 root 서비스 실행 경로로 등록하지 않는다.

## 최초 업로드와 이후 업데이트

현재 연결된 Pico는 `c0de:caff` **구형 NeoPixel Bench**다. 그 이미지의 Linux용 CLI와 소스가 현재 저장소에 없으므로 통합 바이너리 명령을 보내거나 미확인 reset을 강제로 수행하지 않는다. 처음 통합 이미지를 설치할 때에는 Pico의 **BOOTSEL을 누른 채 USB를 Nano에 다시 연결**해 `2e8a:000f`로 열거한 뒤 실행한다.

```bash
cd /home/jetson/ict_makerton_2026
# 한 개의 RP2350 BOOTSEL 보드만 연결된 상태
bash firmware/flash-pico.sh --bootsel
```

통합 이미지가 올라간 다음 업데이트는 BOOTSEL 버튼 없이 실행할 수 있도록 구성했다. USB 브리지·터미널을 먼저 종료하고 실제 alias를 지정한다.

```bash
bash firmware/build-pico-device.sh
bash firmware/flash-pico.sh --port /dev/pico-device
```

업로더는 다음을 요구한다.

1. UF2 블록의 magic·family·번호·겹치지 않는 4 MiB flash 주소와 manifest SHA-256 일치.
2. CDC 모드에서는 선택한 USB 부모가 `c0de:cafc`, 포트 미점유, `pico-device-v1` Status·OE HIGH·`picotool-v1` 확인. 그 뒤 host의 출력 정리/Bootloader Ack를 확인한다. Ack만으로 ROM 진입 성공을 판정하지 않는다.
3. RP2350 ROM 한 개와 앱→ROM serial 일치, picotool의 RP2350 정보 확인. 여러 보드·RP2040·다른 serial·권한 오류면 중단한다.
4. 기존 **4 MiB 전체 flash를 백업**한 뒤 `picotool load -v`, 별도 `verify`, `reboot` 실행. 쓰기 실패 뒤 다른 방식의 자동 재시도는 하지 않는다.
5. 같은 serial의 `c0de:cafc` 재열거와 새 앱의 Status·OE HIGH·reset 기능 확인. 서보·LED·매트릭스 구동 시험은 시작하지 않는다.

각 실행의 `tmp/pico-flash/<UTC>-linux/`에 동결한 UF2, 명령 출력, 이전 flash `previous-flash.bin`, `flash-result.json`을 보존한다. 로그 폴더는 사용자 전용이다. `flash_verified`, `application_status_verified`, `completed`를 각각 확인한다. 이 Linux 도구는 UF2 드라이브 복사 fallback을 제공하지 않아 읽기 검증 없는 복사를 성공으로 보고하지 않는다.

전체 flash 백업에는 기기별 데이터가 포함될 수 있으므로 Git에 추가하지 않는다. OTP·보안 fuse의 백업/복구가 아니며, 복구 파일을 다른 보드에 쓰지 않는다. 자동 rollback은 하지 않는다. 실패 시 보드를 BOOTSEL로 다시 열고 로그·대상 serial·백업을 확인한 뒤 복구한다.

## 검증 기록

2026-10-24 Nano 실측 로그는 [board-info/2026-10-24](board-info/2026-10-24/)의 `linux-firmware-*`에 보존한다. 최종 빌드·검사 결과와 실제 업로드 여부는 후속 검증 기록을 따른다.
