# Rust micro-architecture 실행과 검증

이 문서는 **초기 기초 실행판**의 검증 기록이다. 후속 AI/음성/경량 모델/기억/Pico v2 구현과 검증은 [전체 기능 구현과 운영](전체기능_구현과_운영.md)을 따른다. 아래 초기 수치와 제한을 현재 전체 기능 미구현 상태로 해석하지 않는다.

2026-10-24 KST, 실제 Nano에서 기존 장치 진단을 Rust 서비스 기반으로 전환했다. 소스는 [software](../../software/README.md), 변경한 설계는 [아키텍처 0절](소프트웨어_아키텍처_계획.md#0-2026-10-24-rust-micro-architecture-개정), 다음 단계는 [외부 AI·로컬 추론 계획](외부AI_로컬추론_구현계획.md)을 따른다.

## 운영 상태

기존 `300seconds-dashboard.service`는 **disabled/inactive**다. `/opt/300seconds/dashboard`와 소스·설정은 보존했다. 새 Rust 실행판은 root 소유 `/opt/300seconds/runtime`, 비root `boarddash` 계정이며 **부팅 자동 시작 없이 수동 target**으로 설치했다. 검증 때 실행하고 종료하므로 기본 상태에서 모니터·카메라·마이크를 계속 점유하지 않는다. 기존 GPU/Argus/SSH/네트워크와 HDMI 로그인은 유지한다. Pico flash는 이번 전환에서 다시 쓰지 않았다.

```bash
sudo systemctl start 300seconds-runtime.target
sudo -u boarddash /opt/300seconds/runtime/nano-runtime ctl controllerd '{"cmd":"status"}'
sudo -u boarddash /opt/300seconds/runtime/nano-runtime ctl controllerd '{"cmd":"help"}'
sudo -u boarddash /opt/300seconds/runtime/nano-runtime ctl controllerd '{"cmd":"stop"}'
sudo systemctl stop 300seconds-runtime.target
# 이전 모니터를 명시적으로 다시 사용할 때만:
sudo systemctl start 300seconds-dashboard
```

서로 충돌하는 unit을 등록해 두 실행판이 USB/CSI/audio를 동시에 열지 못하게 한다. 새 target에는 `[Install]`을 두지 않았다. `help`는 턴·lease 승인일 뿐 LLM 호출이나 서보 자동 시험이 아니다.

## 구현 경계

| 모듈/프로세스 | 실제 구현 |
| --- | --- |
| host-core |64KiB 길이 프레임·typed JSON·deadline, 750ms controller lease·epoch·retired owner 차단, PCM1 binary header, bounded3슬롯, 외부 판단 정책 gate |
| controllerd | quiet/help_requested/stopped/fault, 명시적 Help,50ms tick 갱신, Stop/Finish 시 epoch 폐기. 활성 턴을 새 Help가 조용히 대체하지 못함 |
| picod | 기존 검증된 Rust 브리지 자식 한 개. controller 사망 시 자체 lease 만료→wire Stop. 자식은 parent-death signal도 받음 |
| camerad | 두 CSI720p30 caps 취득, nvvidconv320×240 NV12, 분석 출력10fps,3슬롯 tmpfs. 실제 buffer 크기 불일치 시 오류 |
| visiond | 현재 camera generation·500ms 이내 슬롯만 읽기,200ms 간격 최신값, CUDA sm53 또는 CPU 밝기·프레임 차 값. 사람·집중·감정 추론 없음 |
| audiod | 같은 GStreamer pipeline의 capture DSP·stereo playback echo reference.48kHz mono PCM 별도 소켓, current epoch·sequence·200ms age·lease 검사, Stop 시 장치 버퍼 reset |
| memoryd | 목표1개 저장·조회·삭제, SQLite WAL·bound parameter. 장기 학습 기억/벡터 검색 전체는 후속 |
| dialogued | 준비된 service/IPC 경계와 provider_unconfigured 오류. 가상 생성문·가짜 API 성공 없음 |

Unix 제어 소켓은0660·동일 서비스 uid를 검사한다. 일반 요청은 최대16개, 별도 stop-only endpoint는4개, PCM 연결도4개로 제한한다. 내부 USB UDP backend는 **systemd picod private network namespace** 안에 있어 다른 로컬 프로세스가 직접 호출해 lease를 우회할 수 없다. 직접 프로세스를 실행하는 개발 harness는 이 운영 격리를 대체하지 않는다.

목표값·일반 서보 자세·고정 독서 조명/효과의 새로운 wire command는 구현하지 않았다. 현재 `test`는 유한 개발 진단이며 AI 제안의 실행기로 사용하지 않는다. 해당 기능은 다음 firmware revision에서 task별 출력 소유권·보정·Stop 회귀와 함께 추가한다.

## 데이터·취소 계약

프레임은 `/run/300seconds/cam{0,1}.{0,1,2}.frame`의 고정 크기3슬롯이다. `FRM1`·generation·frame ID·Nano sample 수신 monotonic 시각·320×240·payload 길이와 tightly packed NV12를 기록한다. 생산자는 exclusive nonblocking flock, 소비자는 shared flock 동안 복사한다. 세 슬롯이 사용 중이면 frame을 버리고 dropped를 증가시킨다. 소비자 사망 시 커널이 lock을 해제한다. mmap 자체 seqlock이나 Rust Mutex를 공유 메모리에 넣지 않았다. 시각은 센서 노출 시작의 정밀 계측값이 아니다.

오디오는 `/run/300seconds/audiod.capture.sock`·`audiod.playback.sock`으로 제어와 분리한다. length + `PCM1`, epoch/sequence/monotonic timestamp/rate/sample count/mono S16LE payload를 사용한다. 큐는4개, appsrc queued bytes9600, 장치 buffer 후보40ms다. Stop 후 예전 epoch PCM은 거부한다. 현재 Stop은 top-level pipeline을 NULL→PLAYING으로 바꿔 DAC 버퍼를 비우므로 capture/AEC도 잠시 재시작한다. acoustic echo attenuation·말 끼어들기의 실제 인식률을 검증한 것은 아니다.

디바이스가 준비되지 않으면 lease를 주지 않는다. Stop 후 같은 epoch Renew를 거부하고 이전 controller generation이 다시 acquire하는 것도 차단한다. controller의 죽음을 picod의 USB heartbeat로 가리지 않는다. 실패한 Stop은 성공으로 보고하지 않고 cleanup 미확인 latch를 유지한다. 전체 CPU·커널 정체나 audiod 전체 hang의 물리 음소거를 보증하는 구조는 아니다.

## 검증 자료

빌드·회귀는 실제 Linux/aarch64 Rust1.90에서 수행했다. 현재 Nano native GStreamer1.16.3·ALSA1.2.2·SQLite3.31.1·CUDA10.2를 작은 C ABI로 링크한다. CUDA는 sm53 kernel을 실제 실행해 CPU 참조와 같은 결과인지 비교한다. 전역 라이브러리 교체나 최신 CUDA 설치는 하지 않았다.

| 최종 검사 | 결과 |
| --- | --- |
| host-core/native 단위 검사 |8+2=10개 통과, Nano release 링크 성공 |
| 실제 7프로세스 acceptance |19개 통과, 정리 후 각 역할 return code0. 강제 종료했던 controller는 새 프로세스로 재시작해 quiet 확인 |
| 실제 CUDA 실행 |76,800 luma 픽셀의 평균·프레임 차를 CPU 참조와 비교해 일치 |
| controller 사망 시 정지 |실행 중 NeoLeft 확인 후 SIGKILL, 약821ms 뒤 lease 무효·Pico OE HIGH·running=None 관찰. 단일 측정이며 p95/부하 보증 아님 |
| systemd 비root 실행 |boarddash로7개 역할 실행, private network namespace와 호스트 UDP backend 접근 불가 확인 |
| 분석 프레임 속도 |두 카메라 각각 약9.99fps, 약10.31초 구간. 센서 caps720p30과 구분 |
| 카메라 장애·복구 |camerad 중지 뒤 vision fresh=false, 재시작 뒤 새 generation의 프레임만 수락 |
| 오디오 경고 |최종 실제 장치 acceptance 로그에서 CRITICAL0개, current PCM 수락·Stop 장치 flush·stale PCM 거부 |
| 최종 배포 |빌드/설치 바이너리 SHA256 일치, 모니터 disabled/inactive, runtime static/inactive, 남은 nano-runtime 프로세스 없음, tty1 active |

- [Rust 단위 검사·릴리스 빌드](board-info/2026-10-24/rust-runtime-build.log)
- [실제 장치 acceptance JSON](board-info/2026-10-24/rust-runtime-hardware.json)
- [비root systemd·namespace·카메라 재시작](board-info/2026-10-24/rust-runtime-systemd.json)
- [설치·수동 시작·종료 로그](board-info/2026-10-24/rust-runtime-systemd.log)
- [최종 소스·배포 해시와 서비스 상태](board-info/2026-10-24/rust-runtime-final.json)
- [오디오 mono/stereo 경고 분리](board-info/2026-10-24/rust-audio-channel-probe.log)

검증 숫자와 관찰 지연은 위 최종 원본을 기준으로 해석한다. 장치 acceptance는 실제 카메라·PCM·CUDA·SQLite, quiet 중 구동 거부·과기한/큰 프레임 거부·미연결 매트릭스 거부·현재 epoch 재생·Stop 후 PCM 거부·controller 사망·재시작 quiet를 확인한다. LED 시험이 **실행 중임을 먼저 확인한 뒤** controller를 SIGKILL하고 OE HIGH/실행 없음으로 전환되는 단일 관찰을 기록한다. 서보를 자동 시험하거나 API 응답을 물리 각도 계측으로 해석하지 않았다.

첫 통합 과정에서 오디오 mixer의 비어 있는 appsrc 대기와 USB DAC mono 채널 경고를 발견했다. mixer를 제거하고 명시적 무음 공급으로 live clock을 유지하며, DAC 앞에서 stereo로 변환했다. mono 캡처와 stereo 재생을 분리 확인한 뒤 전체 재검증을 수행했다. 카메라/오디오 thread를 join해 Argus 정리 전에 프로세스가 먼저 끝나는 문제도 수정했다. 기존 미사용 nvcompositor의 missing libgstbadvideo 경고는 시스템에 남은 별도 설치 이력이며 이 실행판은 nvcompositor를 사용하지 않는다.

stereo 변환에는 appsrc의 고정 S16LE/48k/mono/interleaved caps와 유효한0~100ms latency를 명시했다. 구버전 GStreamer의 caps/latency 경고를 숨기는 대신 협상 조건을 바로잡았다.

## 다음 구현과 남은 한계

기본 Rust 장치·IPC 실행판과 최종 학습 동반자를 구분한다. 외부 API 키/계정·실제 ASR/생성/TTS, 경량 모델 weights/추론·재석 정확도, acoustic AEC·음성 중단, 스위치/매트릭스 실연결, 장기 기억·일반 자세/조명 API·전원 부하·장시간 장애 시험은 다음 단계다. 공급자 비교와 통과 조건은 [외부 AI·로컬 추론 계획](외부AI_로컬추론_구현계획.md)에 구체화했다.
