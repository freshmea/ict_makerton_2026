# Nano에서 Pico 2 펌웨어 빌드·업데이트

대상은 Nano에 사용자가 clone한 `/home/jetson/ict_makerton_2026`과 RP2350 Pico 2의 `pico2-device-bench` 통합 이미지다. Jetson의 BSP·커널·카메라 펌웨어를 갱신하는 도구가 아니다.

## 설치 위치와 소스

- 최초 확인한 Nano clone HEAD는 `6e84286ee4bb49a93ce38bd9c4e4ea9ea33827ab`, origin은 `https://github.com/freshmea/ict_makerton_2026.git`이며 당시 작업 트리는 깨끗했다. 최종 빌드 시 HEAD는 `ef8b7d6b4698ac45a0400d67b8dafb11c93c20d3`으로 갱신되어 있었다. 이 설정 작업에서는 commit·push·reset을 실행하지 않았다.
- 최초 전송 때 Windows 작업본의 미커밋 통합 host `src/main.rs`와 crate 내부 reset 모듈 등을 Nano clone에 반영했다. 변경 전 파일은 `/home/jetson/.cache/300seconds-linux-firmware-20261024/clone-baseline/`, 전송 목록·SHA-256은 같은 상위 폴더의 `sync-manifest.json`에 보존한다. 최종 빌드 당시의 HEAD·dirty 여부·실제 source SHA-256은 build-info.json으로 확인한다. Linux 설치 스크립트의 후속 수정도 포함하므로 HEAD만으로 이번 작업본 전체를 설명하지 않는다.
- Rust 1.90.0: 기존 격리 설치 `$HOME/.local/share/300seconds/rust/`. `thumbv8m.main-none-eabihf` 타깃을 추가한다. 별도 ARM GCC는 필요하지 않다.
- picotool 2.3.1: 저장소의 `.local-tools/linux/picotool/2.3.1/install/bin/picotool`. 소스 commit `2041936441b48a3cc53ae3da9e805229fe8f4e18`, Pico SDK 2.2.0 commit `a1438dff1d38bd9c65dbd693f0e5db4b9ae91779`를 고정한다. Nano aarch64에서 직접 빌드하고 install-info.json에 바이너리 SHA-256을 기록한다.
- SDK의 사전 빌드 보조 ELF를 사용하는 `USE_PRECOMPILED=ON`이다. SDK mbedTLS를 받지 않아 picotool의 이미지 암호화·서명 기능은 설치하지 않는다. USB 읽기/쓰기/검증과 UF2 변환을 사용한다. UF2 SHA-256은 Python으로 별도 계산한다.
- 이 Nano의 GNU 8.4.0 조합에서 picotool Release 빌드가 `info`의 clipp 출력 중 SIGSEGV를 일으켰다. 새 UF2와 SDK 기본 ELF 양쪽에서 재현했다. 같은 고정 소스를 **Debug**로 빌드하면 파일 정보 조회가 성공해, setup의 picotool만 Debug로 고정했다. 최적화·assert 등 어느 차이가 근본 원인인지는 확정하지 않았다. Pico 펌웨어와 Rust host는 Release다. setup은 SDK ELF의 실제 `info -a` 검사를 통과해야 install-info.json을 갱신하며, firmware 빌드도 새 UF2의 `info -a`를 확인한다.

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

대시보드 작업 전 연결된 Pico는 `c0de:caff` **NeoPixel Bench 변형**이다. VID/PID는 통합 `c0de:cafc`와 구분하는 식별자이며 이미지가 오래됐다는 뜻이 아니다. 재점검에서 interface 2의 class/subclass/protocol `ff/00/01`, 이름 `Reset`을 확인했고, **picotool `info -d -f`로 버튼 없이 ROM 진입·4 MiB flash 정보 조회·같은 앱 복귀에 성공했다.** 이전의 “구형이어서 최초 물리 BOOTSEL이 필요하다”는 판정은 잘못된 추론이었다.

당시 이미지에는 통합 바이너리 CDC 명령 대신 picotool의 USB Reset 경로를 사용한다. 다음 명령은 flash를 쓰지 않고 ROM 정보를 읽은 뒤 앱으로 복귀하며 실제 성공을 확인했다. 아래 serial은 이번 보드의 public chip ID다. 다른 보드는 그 보드의 serial로 바꾼다.

```bash
cd /home/jetson/ict_makerton_2026
PICOTOOL="$PWD/.local-tools/linux/picotool/2.3.1/install/bin/picotool"
PICO_SERIAL='E679675A69C4039B'
# 읽기 점검: 버튼 없는 ROM 진입 → 정보 조회 → 앱 복귀
"$PICOTOOL" info -d -f --vid 0xc0de --pid 0xcaff --ser "$PICO_SERIAL"
```

통합 이미지로 교체할 때에는 원격으로 ROM에 남도록 전환한 다음 기존 업로더를 사용할 수 있다. 이후 사용자 승인으로 아래 `reboot -u`→쓰기 조합도 실행해 성공했다. [대시보드 작업 기록](Jetson_Nano_장치_대시보드.md)을 따른다. 물리 BOOTSEL은 소프트웨어 Reset이 없는 이미지·손상된 앱의 복구 경로다.

```bash
cd /home/jetson/ict_makerton_2026
# 먼저 위와 같이 PICOTOOL 변수를 지정한다. 한 개의 대상 보드만 연결한다.
"$PICOTOOL" reboot -u -f --vid 0xc0de --pid 0xcaff --ser "$PICO_SERIAL"
# ROM 2e8a:000f 진입 후, 백업·쓰기·읽기 검증·통합 CDC 확인
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

2026-10-24 KST Nano에서 다음을 확인했다. 원본은 [최종 설치·빌드 로그](board-info/2026-10-24/linux-firmware-setup-and-build-final.log), [호스트 검사](board-info/2026-10-24/linux-firmware-host-tests.log), [업로더 방어 검사](board-info/2026-10-24/linux-firmware-safety-tests.log), [최종 상태 JSON](board-info/2026-10-24/linux-firmware-final.json)을 따른다.

- 고정 Rust 1.90.0 / RP2350 크로스 빌드와 Nano aarch64 Release host 빌드 성공.
- UF2는 271블록·138,752바이트·Arm Secure다. SHA-256은 `e4f2352f342465035603079809e4103ef51acfde3f9cd5986199ebc230f9d44f`다. picotool에서도 이름 `Pico2 Device Bench`, target `RP2350`, `ARM Secure`, release 정보를 확인했다.
- Rust host 테스트 8개와 업로더 방어 검사 11개 통과. shellcheck와 Bash 구문 검사 통과.
- `flash-pico.sh --check`에서 준비 상태·UF2/host/tool 해시·현재 USB 접근을 확인했다. `/dev/pico-neopixel`을 통합 CDC 업로드 대상으로 지정하면 쓰기 전에 거부했다. 이는 스크립트의 변형 제한이며 picotool Reset 불가 판정이 아니다.
- **재점검에서 버튼 없는 ROM 진입·정보 조회·동일 앱 복귀는 실제 성공했다.** 결과는 [현재 이미지·picotool 재점검](board-info/2026-10-24/picotool-current-image-recheck.json)에 기록했다. 이 재점검 당시에는 4 MiB 전체 백업·flash 쓰기/readback·새 통합 CDC 재연결을 실행하지 않았다. 이후 대시보드 작업 중 사용자 승인으로 모두 실행했고, 장치는 `c0de:cafc` 통합 이미지로 바뀌었다. [실제 flash 결과](board-info/2026-10-24/dashboard-pico-flash-result.json)를 따른다. 이전 [최종 상태 JSON](board-info/2026-10-24/linux-firmware-final.json)의 `initial_physical_bootsel_required: true`는 당시의 잘못된 추론이며 이 재점검으로 정정한다.
