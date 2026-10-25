# SW3 짧은 누름 · NeoPixel 랜덤 패턴 10종

2026-10-25 후속 점검에서 **기존 작업은 로컬 UF2 빌드까지만 수행했고 Nano/Pico에는 미적용**이었음을 확인했다. Nano에는 `light_patterns.rs`와 `PATTERN_PRESS` 코드가 없었으며 SW3 입력 자체와 대시보드 NeoPixel 진단은 정상 동작했다. 새 코드를 Nano에 반영하고 네이티브 검사 20개 통과 후 실제 Pico에 업로드했다. 4MiB 기존 flash 백업, 새 이미지 쓰기·읽기 검증, 같은 USB serial의 앱 복귀, 대시보드 active·Pico connected·faults 0을 확인했다. **사용자가 실물 SW3로 바닥 점등과 패턴 변경을 확인했다.**

SW3(GP8, 물리 11번)를 누르면 기존 30ms 디바운스 후 Pico의 다음 20ms 출력 tick에서 패턴을 무작위로 선택한다. 번호 음성·길게 누르기·버튼 해제를 기다리지 않는다. 유지 중에는 다시 선택하지 않고, 손을 떼고 다시 누를 때 직전과 다른 패턴으로 교체한다. 선택된 패턴은 다음 누름이나 정지/다른 조명 명령 전까지 반복된다. “삼번” 음성과 유지 비프음은 기존 Jetson 경로에서 독립적으로 재생한다.

## 픽셀 배치

기존 두 출력 GP16/GP17 각각의 `[4,4,10]` 설정을 사용한다. 양쪽 출력은 같은 패턴으로 움직이며 색상에 차이를 준다. 번호는 **각 출력의 0부터 시작하는 DIN 순서**다.

| 그룹 | 픽셀 | 단위 |
|---|---|---|
| 바닥 | 0~3 | 4개 |
| 팔 | 4~7 | 4개 |
| 메인 전등 위 행 | 8~10 | 3개 |
| 메인 전등 가운데 행 | 11~14 | 4개 |
| 메인 전등 아래 행 | 15~17 | 3개 |

메인등은 위→가운데→아래 행, 각 행 왼쪽→오른쪽 순서로 가정했다. 실제 DIN 순서가 지그재그이거나 반대 방향이면 `light_patterns.rs`의 `MAIN_ROWS`/`MAIN_COLUMNS`를 실물 배선에 맞게 바꾼다.

## 패턴

Adafruit [strandtest](https://github.com/adafruit/Adafruit_NeoPixel/blob/master/examples/strandtest/strandtest.ino)의 color wipe, rainbow, theater chase와 [buttoncycler](https://github.com/adafruit/Adafruit_NeoPixel/blob/master/examples/buttoncycler/buttoncycler.ino)의 누름 전환 아이디어를 참고했다. Rust/Embassy/PIO에서 시간 기반 프레임으로 구현했다.

| 번호 | 패턴 | 효과 |
|---|---|---|
| 1 | 그룹 무지개 | 바닥·팔·메인이 서로 다른 색으로 순환 |
| 2 | 컬러 와이프 | 각 그룹을 한 점씩 채웠다가 지움 |
| 3 | 시어터 체이스 | 그룹별 고정색이 세 칸 간격으로 이동 |
| 4 | 무지개 체이스 | 이동하는 점들의 색도 순환 |
| 5 | 그룹 숨쉬기 | 세 그룹의 밝기가 시차를 두고 증감 |
| 6 | 그룹 릴레이 | 바닥→팔→메인을 차례로 점멸 |
| 7 | 혜성 | 각 그룹에서 밝은 머리와 짧은 꼬리가 순환 |
| 8 | 메인 행 물결 | 3→4→3개 행을 순서대로 강조, 바닥·팔 연동 |
| 9 | 메인 좌우 스캔 | 메인 열과 바닥·팔을 좌우로 왕복 점등 |
| 10 | 스파클 | 그룹 안의 여러 점이 무작위처럼 반짝임 |

## 정지와 기존 기능 공존

- Pico 단일 출력 task가 PIO를 계속 소유한다. 패턴별 `delay`나 긴 반복문은 없다.
- 칩 ID와 누른 시각을 섞은 의사난수로 10개 모두 선택 가능하며 직전 패턴의 연속 재선택은 제외한다.
- 정상 USB 세션과 keepalive가 필요하다. 브라우저 없이 동작하지만 기존 Jetson USB 브리지는 실행 중이어야 한다.
- Stop, USB 단절/lease 만료, watchdog, 새 세션은 선택을 취소하고 소등한다. 정지 중 누르고 있던 버튼은 실제 해제 후 다시 눌러야 한다.
- SW3는 서보 Arm이나 PWM 활성화를 수행하지 않으며 조명만 교체한다.
- 정상 `SetLight`(GPT Decisions 반응 등)는 버튼 패턴을 종료한다. 이후 SW3를 다시 누르면 랜덤 패턴으로 전환된다.
- 장치 진단 시험 중 SW3 입력은 무시하며 진단 시작 시 기존 버튼 조명은 소등한다.
- RGB 채널당 최대 32/255, 사용 길이 뒤의 버퍼는 검정이다. `outputs.light_active`는 소프트웨어 실행 상태이며 실제 발광 피드백은 아니다.

## 파일과 검증

- 패턴·랜덤 선택·누름 가드: [light_patterns.rs](../../firmware/pico2-device-bench/src/light_patterns.rs)
- SW3 입력·실행·정지: [main.rs](../../firmware/pico2-device-bench/src/main.rs)
- 업로드용 파일: `firmware/pico2-device-bench/dist/pico2-device-bench.uf2`
- 실제 Nano 배포 이미지(Nano 내부): `/home/jetson/ict_makerton_2026/firmware/pico2-device-bench/dist/linux/pico2-device-bench.uf2`, SHA256 `332c64e2c520c3676c84bd0816d024f69117501d56dc5f4756e3ebac26b11baf`
- [검사·빌드 기록](dashboard-check/2026-10-25/sw3-neopixel/)

PowerShell에서 재현:

```powershell
. ./firmware/Use-LocalRust.ps1
cargo test --locked --manifest-path firmware/pico2-device-bench/Cargo.toml --lib --target x86_64-pc-windows-msvc
./firmware/Build-PicoDevice.ps1
```

자동 검사: 10종의 시간 변화·밝기 상한·미사용 픽셀 소등·빈/최대 세그먼트 경계, 1,000회 선택의 전체 패턴 도달과 연속 중복 배제, 3-4-3 행과 4/4/10 릴레이, 실제 TouchEngine을 통한 짧은 누름·유지·접점 튐·부팅 시 눌림·정지 세대 변경 및 양쪽 입력 극성. 기존 서보·눈 매핑·정지 검사를 포함한다.

실물 확인: SW3 점등·패턴 변경은 사용자 확인 완료. `light_active=true`, faults 0, OE HIGH도 수신했다. 유지 중 재선택 방지와 행별 매핑은 자동 검사에서 확인했으며, 10개 전 패턴의 실물 방향·전원 부하·Stop 후 재누름은 별도 전수 관찰하지 않았다.
