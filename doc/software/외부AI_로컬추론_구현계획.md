# 외부 판단 API · 생성 LLM · Nano 로컬 처리 구현 계획

이 문서는 착수 당시 비교·실행 계획을 보존한다. 후속 구현·실제 계정 확인·무료 상한·모델 변경·검증은 [전체 기능 구현과 운영](전체기능_구현과_운영.md)에 기록한다. Jev/Decisions/Gemini 어댑터와 로컬 경량 처리는 코드에 추가했으며 실제 계정 A/B 전체를 완료했다는 뜻은 아니다.

현재 선택은 **Gemini3.5 Flash-Lite 단일 판단/힌트 요청 + Typecast ssfm-v30/서연 TTS**다. 한국어 로컬 ASR은 Vosk small ko0.22, 요청한720p 교재 OCR은 Tesseract kor+eng, 사람/얼굴 후보는 YOLOX-Nano TensorRT8 FP16와 YuNet으로 구현했다. Typecast는 실제 사용자 청취 확인을 통과했으며 매 합성 전 공식 계정 잔여 크레딧과 로컬 문자 상한을 검사한다. OpenAI는 인증/목록만 확인하고 무료 크레딧 확인 전 추론을 차단한다. Jev·Decisions의 실제 계정 A/B, 다양한 한국어 정확도 평가와 실제 AEC/double-talk는 후속 검증이다.

확인일: 2026-10-24 KST. [사업계획서](../계획서/300_Seconds_사업계획서.md)의 핵심은 아이가 주도하는 조용한 대기, 요청한 힌트 하나, 중단·정정, 선택한 목표와 기억이다. 카메라 관찰이나 모델 판단만으로 먼저 말하거나 서보를 움직이지 않는다. 이 문서는 **구현 계획**이며 공급자 계정의 API 호출·한국어 정확도·유료 비용·경량 모델 FPS를 실측한 결과가 아니다.

## 1. 역할을 나눈 실행 흐름

```text
IMX219 두 대 -> camerad(NVMM 축소) -> 3슬롯 tmpfs -> visiond(CUDA/경량 추론)
USB 마이크 -> audiod(AEC -> 로컬 VAD 후보) -> 허가된 turn의 PCM -> ASR
                                                        |
               로컬 관찰 + 최근 사용자 발화 + 선택한 목표 + 허용 행동
                                                        |
                    Jev / OpenAI Decisions / Gemini 분류 비교
                                                        |
                 Rust controller: quiet/Stop/epoch/불확실성 정책 검사
                                                        |
                 허용된 도움 요청 -> 생성 LLM -> 짧은 힌트 -> TTS
                                                        |
                     audiod PCM(epoch/lease) -> 스피커
```

모델은 `wait / clarify / offer_hint / end_session` 중 제안을 반환한다. `servo_angle`, GPIO, shell 명령은 응답 계약에 넣지 않는다. `host-core::decision::permit`은 Stop·미요청·이전 epoch·2초 넘은 관찰을 Wait로 바꾸고, 유효 확률이 아니거나 후보 임계값0.85 미만이면 Clarify로 제한한다. **0.85는 검증 전 보수적 시작값**이며 공급자별 한국어 라벨 데이터로 조정한다. 현재 `dialogued`는 미설정 오류를 반환하고 외부 API를 호출하지 않는다.

## 2. 접근 가능한 공식 API 비교

공식 문서 접근 가능과 실제 계정 사용 가능을 구분한다. 세 공급자 모두 이번 작업에서 키·결제·할당량·지역·모델 호출 권한은 확인하지 않았다. 키를 받으면 최소 가상 텍스트로 인증/모델 목록부터 확인하며 실제 아이의 영상·음성으로 시험하지 않는다.

| 후보 | 공식 호출·출력 계약 | 프로젝트에서 맡길 일 | 제약·검증 |
| --- | --- | --- | --- |
| TypeSafe Jev | `POST https://api.typesafe.ai/v1/systemone`; `state` + 이름별 `questions`; `noul/choice/score`, `answers` map. 배포 시 실제 model ID 고정 | “힌트만”, “기다려”, “다시 설명” 의도 분류·생성 필요 여부 | 텍스트/구조화 상태부터 시작. 이미지·box는 공식 문서의 danger-zone opt-in 기능이므로 초기 경로에서 제외. 생성 힌트·ASR·TTS 대체 아님 |
| OpenAI Decisions | `POST https://api.openai.com/v1/decisions`, `gpt-6-luna`; `input` + `questions` array, predicate/choice/score와 확률/신뢰도 | 같은 의도/개입 판단 평가, 필요 시 제한된 이미지 증거 | 공식 changelog의 **2026-10-22 GA** 확인. JSON 입력·질문별 이미지·최대400질문은 문서상 기능이며 이 프로젝트 실측 지연은 미정 |
| Gemini structured output | `generateContent`의 JSON Schema 구조화 출력, 실제 사용 가능한 Flash 계열 ID를 Models에서 확인·고정 | 판단과 짧은 한국어 힌트·문제 설명을 한 공급자로 구성하는 기준선 | JSON 형식 성공과 판단 정확도는 다름. 요청 기반 생성·취소·토큰 제한을 검사 |
| Gemini Live / OpenAI 음성 API | 별도의 스트리밍 음성 세션과 취소 계약 | 이후 자연스러운 ASR/TTS·말 끼어들기 통합 후보 | 초기에는 ASR→판단→생성→TTS 분리 경로로 각 단계 지연/취소를 관측. 기존 소비자용 구독을 API 사용권으로 간주하지 않음 |

출처: [TypeSafe API](https://docs.typesafe.ai/api/system-one), [모델 버전](https://docs.typesafe.ai/models), [이미지 실험 기능 공지](https://typesafe.ai/blog/jev-1-14), [OpenAI Decisions](https://developers.openai.com/api/docs/guides/decisions), [GA changelog](https://developers.openai.com/api/docs/changelog), [Gemini Models](https://ai.google.dev/gemini-api/docs/models), [Gemini structured output](https://ai.google.dev/gemini-api/docs/structured-output).

추천 착수 순서는 **Gemini의 생성 경로를 기준선으로 만들고 Jev와 Decisions를 같은 판단 데이터셋으로 비교**하는 것이다. 후보를 모두 매 turn 호출하지 않는다. 한국어 오분류·확률 보정·실측 지연·호출 비용이 나은 판단 공급자 하나를 선택한다. 별도 판단 호출이 생성 모델 한 번보다 이점이 없으면 불필요한 API 단계를 줄인다. 공식 “빠르다”는 설명을 Nano→클라우드 왕복 지연이나 프로젝트 SLA로 사용하지 않는다.

공식 과금표는 [TypeSafe 모델 표](https://docs.typesafe.ai/models), [OpenAI 가격](https://developers.openai.com/api/docs/pricing), [Gemini 가격](https://ai.google.dev/gemini-api/docs/pricing)을 확인한다. 제3자 Jev gateway와 TypeSafe 직접 API의 가격·키를 혼용하지 않는다. 비용은 `(판단 입력 + 생성 입력/출력 + ASR/TTS + 이미지 + 실패/재시도)`로 측정하고 월 요청량·세션 길이로 계산한다. 모델/티어별 실제 가격·캐시 조건은 배포 직전 다시 고정한다. 무료 티어의 데이터 사용 조건도 별도 확인한다.

## 3. Nano에서 처리할 데이터와 CUDA 범위

이 보드는 **구형 Nano 4GB / Maxwell sm_53 / CUDA10.2 / TensorRT8.0.1 / Python3.8**이며 Orin Nano가 아니다. 최신 CUDA12·TensorRT10 전용 wheel을 설치하거나 전역 OpenCV/TensorFlow를 교체하지 않는다. `pkg-config opencv4`는4.6.0이고 여러 OpenCV 버전의 라이브러리가 함께 보이므로 실제 링크·ABI를 먼저 대조한다.

| 단계 | 처리 위치·입출력 | 구현/검증 기준 |
| --- | --- | --- |
| 카메라 취득·축소 | NVIDIA `nvarguscamerasrc -> nvvidconv`, 분석용320×240 NV12 /10fps씩 | 현재 Rust camerad의 실제 프레임 경로. 원본720p30과 분석 FPS 구분 |
| 밝기·움직임 기초 | CUDA luma 평균·전 프레임과 절대 차 평균; CPU 참조와 비교 | 현재 `visiond` C ABI CUDA kernel. 실제 의미 추론·사람 감지는 아님. 작은 영상에서는 전송/launch 비용 때문에 CPU가 빠를 수 있어 비교 후 선택 |
| 재석 후보 | YOLOX-Nano 등 소형 사람 검출, 두 카메라 중 유효 view의 person box와 신뢰도 | ONNX opset·고정 입력·연산자 지원·실제 TensorRT8.0 엔진 빌드부터 통과. FP16/FP32 후보, 엔진은 보드에서 생성 |
| 얼굴 방향 보조 | YuNet 얼굴 box/landmark, 필요 시 MediaPipe face/pose lite | 얼굴이 안 보임은 부재/졸음 판정이 아님. 손/교재에 가려진 사례를 unknown으로 처리 |
| 음성 기초 | audiod48kHz AEC/노이즈 처리 뒤 로컬 VAD 후보 | RMS는 현재 진단값이며 음성 의도/VAD 정확도 증거가 아님. 스피커 자기 음성·무음·잡음/동시 발화를 평가 |
| 임베딩/기억 검색 | 우선 SQLite 명시적 목표/메모; 이후 소형 CPU 임베딩 또는 외부 PC | 기록 동의·삭제·출처·최근 확인 시각부터 구현. GPU에 대형 언어모델을 상주시켜 카메라 메모리를 압박하지 않음 |

현재 CUDA 코드는 지속 GPU 버퍼·stream과 block reduction으로 개정했다. 실제76,800픽셀 통계50회에서 CPU p50/p95 954/1027µs, CUDA 2760/3177µs여서 이 작은 통계는 CPU를 기본으로 선택했다. YOLOX 의미 추론은 실제 보드에서 생성한 TensorRT8 FP16 엔진을 사용한다. NVMM에서 CPU 슬롯으로 내려오는 복사는 이미 존재하며 zero-copy라고 표현하지 않는다. Nano는 INT8 가속/Tensor Core가 있는 Orin으로 취급하지 않는다. [실측](board-info/2026-10-24/full-media.log), [Nano 사양](https://developer.nvidia.com/embedded/jetson-nano), [NVIDIA SM5.3 정밀도 지원 표](https://developer.download.nvidia.cn/compute/machine-learning/tensorrt/docs/5.1/rc/TensorRT-Support-Matrix-Guide.pdf). 옛 지원 표는 하드웨어 특성 참고이며 현재 엔진 성공을 대체하지 않는다.

### MediaPipe와 작은 모델을 선택하는 기준

- [MediaPipe Python 공식 설치 기준](https://developers.google.com/edge/mediapipe/solutions/setup_python)은 Python3.9 이상이다. 현재3.8에 단순 pip 설치를 성공 전제로 두지 않는다. 별도 Python 환경·aarch64 wheel·glibc를 검증하거나 C++ adapter/외부 PC에서 먼저 비교한다.
- [MediaPipe GPU 문서](https://developers.google.com/edge/mediapipe/framework/getting_started/gpu_support)의 GPU 경로는 OpenGL ES 등을 다룬다. “GPU delegate”를 CUDA/TensorRT 사용으로 바꾸어 말하지 않는다.
- [Pose Landmarker Lite](https://developers.google.com/edge/mediapipe/solutions/vision/pose_landmarker)는 작은 pose 후보지만 ROI 검출·추적·후처리까지 필요하다. 모델 weight만 가져오면 전체 MediaPipe graph와 같다고 가정하지 않는다.
- [YOLOX-Nano](https://github.com/Megvii-BaseDetection/YOLOX)는 ONNX/TensorRT 이식 후보, [OpenCV YuNet](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet)은 작은 얼굴 검출 후보다. 최신 YuNet demo가 요구하는 OpenCV와 현재 ABI가 다를 수 있어 특정 모델 revision·입력 tensor·SHA256·라이선스를 manifest에 고정한 뒤 테스트한다.
- 우선순위는 person 존재 후보 → face box 보조 → pose 일부다. 얼굴 식별·감정·집중 점수는 구현 목표에서 제외한다. weight 크기만으로 RAM/latency/정확도를 판정하지 않는다.

## 4. 관찰을 의미 있는 상태로 바꾸는 과정

두 카메라의 실제 설치 방향은 아직 확정하지 않는다. 배치 후보는 학습자/손을 보는 view 하나와 책상/교재를 보는 view 하나이며 설치 후 camera index·ROI·가림을 캘리브레이션한다. 현재320×240 분석 프레임은 교재 OCR 성공을 보장하지 않는다. 도움 요청 시 camerad가 독점을 유지한 채720p JPEG branch를 잠시 열고 ROI/회전/품질 검사 뒤 OCR하는 경로를 구현했다. 원본/후보는 현재 요청 동안만 처리하며 확인한 문제 문장만 모델 문맥에 넣는다.

교재 입력은 **사용자가 선택한 문제 crop → 회전/대비·초점 품질 검사 → OCR 후보 → confidence/원문 대조 → 생성 모델 문맥** 순서로 처리한다. [Tesseract](https://github.com/tesseract-ocr/tesseract)는 CPU 기준선, [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR)의 작은 모델은 이후 변환 후보로 비교한다. 최신 전체 Paddle 환경을 이 Nano에 바로 설치하지 않고 모델 revision·한국어 지원·ONNX 연산자·라이선스를 확인한다. 낮은 신뢰도·필기/수식은 추정 정답으로 굳히지 않고 사용자 확인 또는 허가된 crop의 외부 멀티모달 해석으로 넘긴다.

음성은 기존 WebRTC DSP 뒤의 bounded VAD와 Vosk small Korean CPU를 구현했다. 실제 한 문장 일치를 확인했지만 다양한 발화의 정확도는 미측정이다. 로컬 대안 [whisper.cpp](https://github.com/ggml-org/whisper.cpp)의 작은 다국어 모델은 후속 비교 후보이며 한국어에 영어 전용 모델을 선택하지 않는다. 최신 CUDA backend의 구형 sm53/CUDA10.2 빌드가 보장되는 것은 아니므로 실제 지원·지연을 확인한 뒤 바꾼다. 실시간성을 확보하지 못하면 무리하게 Nano의 GPU·RAM을 점유하지 않는다. 음향 검증은 excitation 부족으로 AEC 합격 판정을 내리지 않았으며 barge-in 기본값은 계속 비활성이다.

1. 각 카메라 프레임에 producer generation, frame ID, Nano monotonic 시각, 유효 영역/가림 여부를 붙인다. 오래되거나 재시작 전 프레임은 버린다.
2. 밝기·움직임은 품질 gate로만 사용한다. 사람/얼굴의 confidence·box·추적 안정도를 별도로 유지하고 미검출을 즉시 부재로 바꾸지 않는다.
3. 초기 후보는2~3초 temporal smoothing·hysteresis다. `present / absent / unknown`과 관찰 근거를 출력하며, 다른 시각·다른 view를 단일한 사실로 합치지 않는다.
4. 마이크 VAD도 epoch·허가·AEC 품질과 묶는다. VAD만으로 대화 요청이나 중단을 확정하지 않는다. 명시적 Stop은 모델 응답을 기다리지 않는다.
5. 판단 API 입력은 `help_requested`, 최신 ASR 텍스트, 짧은 관련 기억, 품질·나이·불확실성을 포함한 상태다. 기본은 구조화 요약이며 두 카메라 원본 영상을 계속 전송하지 않는다.
6. 결과를 동일한 `Decision`으로 정규화하고 모델 refusal/미지원 타입/NaN/스키마 오류/timeout을 명시적 실패로 처리한다. 생성 취소 뒤 예전 epoch의 텍스트·PCM은 수락하지 않는다.
7. 승인된 턴에서만 짧은 힌트 하나를 생성·재생하고 `finish`로 quiet로 돌아간다. 저장은 사용자가 확인한 목표·요약만 대상으로 하며 모델 추정은 사실로 저장하지 않는다.

## 5. 구현 순서와 통과 조건

| 단계 | 산출물 | 통과 조건 |
| --- | --- | --- |
| A Rust 기초 | controller/pico/media/memory 프로세스·IPC·lease·epoch | 실제 Nano의 장치 경로·Stop·controller 사망·오래된 PCM/프레임 거부. [Rust 실행·검증](Rust_마이크로아키텍처_실행과_검증.md) |
| B 경량 관찰 | 고정 모델 manifest + C ABI TensorRT/선택 MediaPipe worker | 각 모델 정확도·오탐·미탐·p50/p95·CPU/GPU/RAM·지속 부하. CUDA kernel 성공과 분리 |
| C 음성 수직 경로 | 허가된 capture→ASR→생성→TTS→PCM | 실제 한국어 문장, AEC acoustic 시험, 요청 취소/기기 버퍼 flush, 중복 재생 없음 |
| D 판단 API A/B | Jev / Decisions / Gemini adapter, 공통 offline fixture와 실제 계정 시험 | 공급자 응답 provenance·정확한 model ID·usage·wall time, raw fixture는 합성 자료. 모의 성공과 API 성공 분리 |
| E 핵심 경험 | 힌트 하나→기다림, 중단·정정, 목표·기억 삭제/이어보기 | 금지된 선제 개입0건, Stop 우선, 계정/네트워크 실패 때 quiet 유지. 실제 사용자 동의 후 시나리오 검증 |

평가 세트는 최소 후보200개로 시작한다: 명시적 요청/기다려/맞장구/정정/잡음ASR/가림·부재/낮은 신뢰도·오래된 상태를 균형 있게 작성하고 train·threshold 튜닝·holdout을 분리한다. 표본 수와 지연 목표는 **착수 전 제안값**이며 이미 통과한 수치가 아니다. 호출당 인증·모델 가용성·rate limit·429/5xx·회로 차단·총 deadline을 검사하며 구동 명령은 재시도하지 않는다. 서로 다른 workload의 공급자 홍보 지연을 비교하지 않는다.

키는 서비스의 별도0600 환경/credential 경로로 전달한다. `.env`, 음성·영상 원본, 실사용자의 개인 정보는 저장소에 넣지 않는다. 현재 구현은 API 키를 요구하거나 외부로 장치 데이터를 전송하지 않는다.
