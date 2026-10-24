# 300 Seconds Rust runtime

최신 기능과 계정/하드웨어 검증 범위는 [전체 기능 구현·운영](../doc/software/전체기능_구현과_운영.md)을 따른다. `tools/study.py`가 도움·정정·음성·OCR·기억·일반 구동 CLI다. 기본 Gemini는 `gemini-3.5-flash-lite` 단일 요청, OpenAI 추론은 무료 크레딧 확인 전 차단한다. 기본 TTS는 Typecast ssfm-v30/서연이며 합성 전 계정 잔여 크레딧과 별도 문자 상한을 검사한다.

Linux/aarch64 Nano에서 실행하는 Rust/Tokio workspace다. `host-core`는 길이 프레이밍·typed IPC·monotonic deadline·controller lease·PCM header·3슬롯 프레임·판단 정책을 소유한다. `nano-runtime`은 같은 실행 파일의 **독립 프로세스 7개**로 실행하며 C ABI에 GStreamer·SQLite·CUDA 호출만 한정한다.

| 역할 | 현재 동작 |
| --- | --- |
| controllerd | quiet → 명시적 Help → lease 갱신, Stop/Finish·epoch 폐기. 자동 발화/동작 없음 |
| picod | 기존 검증된 Rust USB 브리지 자식 한 개, Unix 제어/별도 Stop 소켓, controller lease 만료 시 Stop |
| camerad | 두 CSI 독점, NVMM 720p30 취득 →320×240 NV12/10fps →3슬롯 tmpfs |
| visiond | CPU/CUDA 품질 + YOLOX-Nano TensorRT FP16/YuNet, 재석 후보/unknown, 요청한 ROI의 한국어 OCR |
| audiod | USB codec 입출력·동일 GStreamer pipeline의 echo reference/DSP,48k mono PCM 별도 소켓·epoch·lease·장치 flush |
| memoryd | SQLite 목표·확인한 메모·opt-in·검색·삭제·페이지 export, 파라미터 바인딩 |
| dialogued | Gemini 판단/힌트와 동의한 발화 단일 호출, Jev/Decisions/Responses 어댑터, Typecast TTS·계정 확인·호출/문자 상한·취소·provenance |

## 빌드·설치

실제 Nano의 개발 패키지/GStreamer app headers·SQLite·CUDA10.2를 사용한다. Windows native 실행 대상은 아니다. `software/Cargo.lock`을 유지한다.

```bash
cd ~/ict_makerton_2026
sudo bash tools/jetson/project-mode.sh  # native ALSA 독점, PulseAudio 충돌 방지
source ~/.local/share/300seconds/rust/env.sh
cargo test --locked --offline --manifest-path software/Cargo.toml -j2
cargo build --release --locked --offline --manifest-path software/Cargo.toml -j2
sudo bash software/install.sh
# 명시적으로 시작/정지. 부팅 자동 시작은 등록하지 않는다.
sudo systemctl start 300seconds-runtime.target
sudo systemctl stop 300seconds-runtime.target '300seconds-runtime@*.service'
```

설치는 기존 `boarddash` 계정과 장치 그룹을 사용한다. 바이너리는 root 소유 `/opt/300seconds/runtime`에 두고, socket/슬롯은 `/run/300seconds`, DB는 `/var/lib/300seconds-runtime/runtime.sqlite3`다. systemd target과 템플릿에는 부팅 enable 항목이 없다. 모니터 서비스는 disabled/inactive이며 동시 실행 충돌도 막는다. 설치만으로 새 서비스나 펌웨어 구동 시험을 시작하지 않는다.

## 수동 요청

Unix 소켓은0660 및 동일 uid를 검사한다. systemd 실행판의 CLI는 `boarddash`로 실행한다. Stop은 별도 stop-only 소켓으로 보내고 일반 명령 대기와 분리한다.

설치판 picod와 USB 자식은 `PrivateNetwork=yes`인 별도 network namespace를 사용한다. 내부 UDP37920을 호스트의 다른 프로세스가 호출해 controller lease를 우회하지 못하게 한다. 직접 실행하는 hardware harness의 UDP 경로는 격리 없는 제한된 개발 시험이며 종료 후 모든 프로세스를 정리한다. 일반 운영은 설치된 systemd target을 사용한다.

```bash
sudo -u boarddash /opt/300seconds/runtime/nano-runtime ctl controllerd '{"cmd":"status"}'
sudo -u boarddash /opt/300seconds/runtime/nano-runtime ctl controllerd '{"cmd":"help"}'
sudo -u boarddash /opt/300seconds/runtime/nano-runtime ctl controllerd '{"cmd":"stop"}'
sudo -u boarddash /opt/300seconds/runtime/nano-runtime ctl controllerd '{"cmd":"finish"}'
sudo -u boarddash /opt/300seconds/runtime/nano-runtime ctl memoryd '{"cmd":"put_goal","text":"내가 고른 독서"}'
sudo -u boarddash /opt/300seconds/runtime/nano-runtime ctl memoryd '{"cmd":"get_goal"}'
sudo -u boarddash /opt/300seconds/runtime/nano-runtime ctl memoryd '{"cmd":"delete_goal"}'
```

`help`는 상태·lease 승인만 하며 AI를 호출하지 않는다. LED/서보 `test`는 개발용 유한 진단이다. 일반 목표 API는 별도로 `pose/light/eyes`를 제공하고 보정 Arm을 요구한다. 스위치·매트릭스 미연결을 유지하고 matrix/all은 거부한다. 모델의 답을 이 개발용 `test`로 직접 연결하지 않는다.

controller lease는750ms, 갱신은50ms tick, Pico wire lease는 기존1초다. controller가 죽으면 picod/audiod가 각자 Stop/flush한다. CPU/커널 전체 정체의 물리 정지 시간을 보증하는 수치는 아니며 실측 결과는 검증 기록을 따른다. Stop 후 같은 epoch Renew는 거부하며 다음 요청은 새 epoch를 요구한다.

`audiod.capture.sock`은 length + PCM1 header + 실제 PCM, `audiod.playback.sock`은 같은 header의 입력이다.48kHz/S16LE/mono, 한 블록 최대4800샘플, current epoch·증가 sequence·200ms 이내 timestamp·유효 lease를 검사한다. playback 서버는 각 블록 수락 뒤 sequence를 8바이트 big-endian ACK로 보낸다. 송신자는 ACK를 기다리고 10ms 간격으로 보내며 지연된 음성을 버린다. ACK는 물리적 청취 완료가 아니다. 현재 Stop은 전체 audio pipeline을 NULL→PLAYING으로 전환해 장치 버퍼를 비우며 capture/AEC도 함께 재시작한다. AEC 소자 연결 성공은 실제 음향 제거 성능의 검증이 아니다.

## 검증

전체 hardware harness는 서비스를 직접 실행하고 종료한다. 기존 runtime target을 먼저 중지한 상태에서 실행하며, 마지막에 프로세스를 정리한다. 한 번의 왼손 LED 유한 시험 중 controller를 종료해 Stop을 확인한다. 서보·외부 API를 자동 시험하지 않는다.

```bash
sudo systemctl stop 300seconds-runtime.target '300seconds-runtime@*.service'
python3 software/tests/verify_runtime.py --output /tmp/rust-runtime-verification.json
software/target/release/nano-runtime cuda-check
# 설치한 systemd 실행판: 카메라/OCR·프로세스 종료·수동 복구·3분 quiet 및 전압 기록.
# 외부 AI 생성·서보 명령은 실행하지 않는다. 완료/실패 후 서비스를 정지한다.
sudo python3 software/tests/verify_installed.py --output /tmp/installed-verification.json
```

Nano의 사전 설치 NumPy/OpenBLAS CPU 자동 선택 오류를 피하려고 `workers/local_ai.py`는 NumPy/OpenCV import 전에 `OPENBLAS_CORETYPE=ARMV8`을 설정한다. 격리 venv도 일부 system-site-packages를 공유하므로 로그인 셸의 환경 변수만으로 해결했다고 간주하지 않는다.

[구현·실제 검증과 한계](../doc/software/Rust_마이크로아키텍처_실행과_검증.md), [아키텍처 개정](../doc/software/소프트웨어_아키텍처_계획.md)을 함께 읽는다.
