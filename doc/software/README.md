# Pico 2 · Jetson Nano 소프트웨어 개발 문서

양쪽 보드 모두 Rust를 우선한다. Pico 2는 Embassy, 구형 Nano는 Tokio 기반 프로세스로 구현한다.

| 문서 | 용도 |
| --- | --- |
| [2026-10-24 작업 종합 기록](Jetson_Nano_작업_종합기록_2026-10-24.md) | 보드 설정·ROS 비활성화·권한·실제 flash·장치 대시보드·HDMI와 남은 검증 범위 |
| [개발 단계 및 점검표](개발_단계_및_점검표.md) | 실제 작업 순서·A/B 병렬 진행·진입/완료 조건·진행 현황 관리 |
| [시험 기록 양식](시험_기록_양식.md) | 개별 시험의 실제 구성·절차·측정·실패·증거 기록 |
| [A 단계 Pico–PCA9685 배선과 초기 점검](A_Pico2_PCA9685_배선과_초기점검.md) | 실제 Pico 2·주소 점퍼·3.3V/6V 전원 분리·서보 1개 시작 절차 |
| [소프트웨어 아키텍처 계획](소프트웨어_아키텍처_계획.md) | 프로세스·IPC·USB protocol·펌웨어·영상·음성의 기술 기준 |
| [Jetson Nano 보드 정보](Jetson_Nano_보드_정보.md) | 2026-10-24 SSH 실측: Nano 4GB·B01 DT·64GB SD·Ubuntu/L4T·CUDA·개발 도구·연결 장치·원본 manifest |
| [Nano 개발 환경 설치·모드 전환](Jetson_Nano_개발환경_설치와_모드전환.md) | Rust1.90·native 개발 패키지 설치, GUI/서비스/모듈 정책 전환·복원 실증, ROS 저장소·만료 키·매분 cron 비활성화 |
| [Nano 디바이스 권한·실물 점검](Jetson_Nano_디바이스_권한과_실물점검.md) | 실제 USB 오디오·Pico 접근, 서비스 계정·udev, IMX708 실패와 V2 교체 이력 |
| [Camera V2 두 개 실물 검증](Jetson_Nano_Camera_V2_실물검증.md) | IMX219 두 센서, 비root 개별·동시 720p 약30fps, 실제 촬영 PNG·PTS·원본 로그 |
| [FastAPI 장치 대시보드](Jetson_Nano_장치_대시보드.md) | 실제 Pico·두 CSI·마이크·스피커, systemd 자동 시작, RTSP/RTP·프레임 속도·검증 기록 |
| [HDMI 텍스트 로그인 점검](Jetson_Nano_HDMI_콘솔_점검.md) | multi-user·tty1 로그인·프레임버퍼 실측과 모니터 연결 시 사용 방법 |
| [Nano Linux 펌웨어 업데이트](Jetson_Nano_Linux_펌웨어_업데이트.md) | clone 소스 반영·Rust 크로스 빌드·picotool2.3.1·BOOTSEL 권한·flash 백업/검증·최초 설치와 재업로드 |
| [Pico–Nano USB 통합 진단](Pico_Nano_USB_통합_진단.md) | 양손18개씩 NeoPixel·서보6개·눈2개·터치6개 통합, SW6 진단 선택, Nano USB 브리지 |
| [핀 배정·전원](Pico2_핀배정_및_전원.md) / [터치·양쪽 눈 배선](A_스위치6개_MAX7219_양쪽눈_배선.md) | 현재 GPIO·물리 핀·전원 구분과 직렬 연결 |
| [통합 펌웨어](../../firmware/pico2-device-bench/README.md) / [Nano·PC 도구](../../tools/pico-device-bench/README.md) / [공통 protocol](../../crates/pico-device-protocol/README.md) | 실제 Rust 소스·설정·빌드·실행 방법 |
| [Bindbot 터치 이식 근거](research/Bindbot_터치_동작_및_USB_이식.md) | 원본500ms hold count와 새2초 눌림 횟수의 구분 |
| [초기·후속 검증 범위](Jetson_Nano_작업_종합기록_2026-10-24.md) / [USB 재업로드](Pico_USB_자동업로드.md) | 통합 이미지28개 자동 검사·UF2/host 빌드 증거와 실제 업로드 절차 |
| [Pico 서보 펌웨어](../../firmware/pico2-servo-bench/README.md) / [PC 벤치 도구](../../tools/pico-servo-bench/README.md) | 현재 구현한 Rust 임시 구동 프로그램의 빌드·업로드·USB 명령 |
| [RUN-20261023-01](test-results/2026-10-23/RUN-20261023-01.md) | Rust 환경·UF2 업로드·USB/I2C·6개 서보 순차 구동의 실제 결과 |
| [RUN-20261023-02](test-results/2026-10-23/RUN-20261023-02.md) | 펄스500~2500µs 확대 후 움직임과 사용자 관찰, 남은 보정 범위 |
| [CLS6336HV SpotMicro 조사](research/CLS6336HV_SpotMicro_구동자료_조사.md) / [근거 데이터 JSON](research/CLS6336HV_SpotMicro_근거데이터.json) | 제조사·기존 코드·강좌·같은 모델 사용자 사례와 현재 시험값의 구분 |

작업은 **공통 준비 → Pico 임시 구동 / Nano SD 준비 병렬 → USB 실제 연결 → 기본 소프트웨어 → 통합 구동 점검 → 필수 고급 기능 → 선택 확장** 순서로 진행한다.

먼저 개발 점검표의 P-01~P-05를 확인한다. 담당자가 나뉘면 A와 B를 동시에 진행하고, Nano 없이도 Pico를 PC에서 시험할 수 있게 한다. 결과를 얻을 때마다 시험 양식을 복사해 RUN을 작성하고 점검표를 갱신한다.

2026-10-23 현재 A 트랙에서는 **Rust 펌웨어 빌드·UF2 업로드·실제 USB 응답·PCA9685 주소0x41 확인·6개 서보의 순차 움직임**까지 확인했다. 기본1000~2000µs의 회전폭이 작다는 관찰 뒤 같은 펌웨어의 런타임 설정을500~2500µs로 넓혀 재시험했고, 사용자는 회전폭 증가와 걸림·이상음 없음을 확인했다. 실제0~180도 계측이나 제조사 보증 최대 범위 확인은 아니다. 재부팅하면 기본1000~2000µs로 돌아간다.

개발 PC의 전역 Rust1.75는 유지하고 저장소 내부 `.local-tools`에 Rust1.90을 구성했다. 저장소 루트의 PowerShell에서 `. .\firmware\Use-LocalRust.ps1`로 현재 셸에 환경을 적용한 뒤 빌드한다. 자세한 재현 명령과 해시는 각 RUN 및 펌웨어·도구 README를 따른다.

추가 사용자 확인: 교체한 NeoPixel4개는 정상 점등했으며 마지막 터치·매트릭스 개별 시험도 완료했다. 원래36개 스트립은 고장으로 판단해 조사를 종료했다. 이는 사용자 관찰이며 이번 통합 이미지의 실물 결과와 구분한다. **30개 초과 NeoPixel의 추가 전원·전원 주입 실부하 시험은 남아 있다.**

새 `pico-device-v1` 통합 진단은 Postcard/CRC/COBS 공유 codec, USB 브리지와 SW6 로컬 검사를 구현한다. 양손은 각각 `[4,4,10]`, 총36개이며 설정 파일로 변경한다. 초기 빌드·모의 시험은 [초기·후속 검증 범위](Jetson_Nano_작업_종합기록_2026-10-24.md), 후속 **실제 flash·Nano USB·LED/서보 사용자 확인·영상/오디오·자동 시작**은 [대시보드 검증](Jetson_Nano_장치_대시보드.md)을 따른다. 현재 스위치·매트릭스는 미연결이며 서보 보정·부하·체계적인 실물 장애 시험과 최종 AI 서비스 통합은 남아 있다.

2026-10-24 01:25에는 기존 SD로 부팅된 **Nano 4GB에 SSH로 접속해 설치 전 manifest를 수집**했다. Ubuntu20.04.6·L4T R32.6.1·CUDA10.2와 GPU 인식은 확인했으며 상세 버전·오류·원본 로그는 [보드 정보](Jetson_Nano_보드_정보.md)를 따른다. 당시 Rust 도구는 계정 PATH/기본 경로에서 찾지 못했고, Pico·카메라·USB 오디오는 조회 목록에 나타나지 않았다. SD 원본 이미지·반복 부팅·복구와 주변장치 실제 실행 검증은 남아 있다.

후속 작업에서 **격리 Rust1.90·개발 패키지를 실제 설치**하고 Nano에서 host 테스트8개·Tokio AF_UNIX 왕복·C native 링크·합성 DSP를 확인했다. GUI/서비스29개를 관리하는 프로젝트 모드와 원래 상태 복원을 시험했으며 최종 상태는 프로젝트 모드다. 이번 프로젝트는 ROS를 사용하지 않아 저장소·만료 공개키·매분 실행 cron·service를 별도 비활성화했다. [적용 명령·복원 데이터·실제 증거](Jetson_Nano_개발환경_설치와_모드전환.md)를 따른다.

이어 실제 연결된 C-Media USB 오디오에서 **48kHz 녹음·재생·duplex와 사용자 청취**를 확인했다. 초기 Pico는 `c0de:caff` NeoPixel Bench였으며, 후속 승인된 flash 이후 **`c0de:cafc` / `/dev/pico-device` 통합 protocol 왕복**을 확인했다. IMX708 두 개는 현재 BSP에서 취득에 실패했으나, 사용자가 **Camera V2로 교체한 뒤 IMX219 두 센서의 개별·동시 720p 약30fps 촬영과 실제 PNG 확인에 성공**했다. 최신 운영 상태와 남은 범위는 [종합 기록](Jetson_Nano_작업_종합기록_2026-10-24.md)을 따른다.
