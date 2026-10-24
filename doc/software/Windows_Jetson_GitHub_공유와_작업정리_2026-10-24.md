# Windows·Jetson GitHub 공유와 작업 정리

기준일: **2026-10-24 KST**. Windows와 Jetson에 나뉘어 있는 소스·설정 예제·문서·검증 자료를 GitHub에서 함께 관리하기 위한 작업 기록이다. 과거 실기 검증과 이번 Git 정리 중 재실행한 검사를 구분한다.

## 저장소와 동기화 상태

| 대상 | 경로·상태 |
| --- | --- |
| GitHub | [freshmea/ict_makerton_2026](https://github.com/freshmea/ict_makerton_2026), 기준 브랜치 `main` |
| Windows | `D:\repository\ict_makerton_2026` |
| Jetson | `/home/jetson/ict_makerton_2026`, 최근 운영 주소 `192.168.184.76` |
| 시작 시 Windows·원격 기준 | `8cc1550fe2bcf638904927bd934cd32114f20e65` |
| Windows 수집 | 최초 수정·신규 파일 237개, 약 5MB. 문서·검사 근거 등을 포함해 **248개 파일**을 커밋 |
| Windows GitHub 게시 | **완료**. 작업 스냅샷 [`9c3146016f0772fe34467d069a896f2bbaaaea33`](https://github.com/freshmea/ict_makerton_2026/commit/9c3146016f0772fe34467d069a896f2bbaaaea33)를 기존 `main`에 일반 push. 로컬·원격 해시 일치 확인 |
| Jetson 수집 | 인증 후 **219개 파일** 원본 해시 수집·비교 완료. 로컬 백업 사본 14개는 원본 stash에 보존 |
| Jetson 기준 정렬 | 기존 `3d4b198`에서 GitHub `main`으로 fast-forward 완료. 실행 서비스 3개 active 유지 |
| 통합 완료 판정 | **완료**. Windows·Jetson·GitHub `main` 내용 검증 커밋 [`e738742`](https://github.com/freshmea/ict_makerton_2026/commit/e7387428fe372e1029bc507cb4d1e51c6fb1cd94) 일치, 양쪽 작업 트리 청결 확인 |

2026-10-24 **23:57 KST**, 두 저장소의 같은 통합 커밋과 청결 상태, 보드 서비스 3개 active, API·Pico·카메라·마이크 정상 응답을 확인했다. [최종 통합 확인 원본](dashboard-check/2026-10-24/git-share/integration-verification.json). 이 완료 기록과 원본 JSON만 후속 문서 커밋으로 게시하고 양쪽 `main`에 다시 fast-forward한다. 따라서 최종 브랜치 끝은 위 내용 검증 커밋 다음의 문서 커밋이며, 정확한 최신 SHA는 `git rev-parse HEAD`와 `git rev-parse origin/main`으로 확인한다.

첫 게시 시 같은 Windows 저장소의 「카메라 분석과 GPT Live 대시보드 구현」 채팅에서 교육 프롬프트·DB 참조 기능을 계속 편집 중이었다. 해당 작업의 완료를 확인한 뒤 후속 문서와 `dashboard-check/2026-10-24/live-context/` 실기 자료 13개도 이번 통합에 포함했다.

사용자가 접속 정보를 제공한 뒤 Jetson 원본을 비교했다. **207개 파일은 내용 동일**, **4개는 기존 공유 커밋과 같은 이전 내용**, **5개는 개별 검토**, **3개는 보드에만 있던 새 메모**였다. 개별 검토한 5개 중 4개는 Windows의 후속 검증 설명을 유지했고, `pico-config.json`은 파싱한 JSON 값이 같아 Windows 형식을 유지했다. 보드에만 있던 메모는 모두 가져왔다. [파일별 비교·결정·원본 해시](dashboard-check/2026-10-24/git-share/jetson-comparison.json).

보드의 원본 tracked/untracked 작업은 stash `d739252344d84d3239a632814d2fe3af3c3d3519`와 `refs/backups/jetson-before-github-sync-20261024`에 보존했다. root 소유 프롬프트 디렉터리는 stash 내용과 일치함을 확인한 뒤 `tmp/git-share-20261024/preserved-prompts`에도 보관했다. 기존 stash와 운영 환경파일·모델·DB·실행본은 유지했다. Git 정리 중 서비스를 재시작하거나 Pico를 flash하지 않았다.

## 지금까지 수행한 작업

| 분야 | 구현·적용 내용 | 근거와 검증 범위 |
| --- | --- | --- |
| Jetson 기반 환경 | Ubuntu 20.04/L4T 환경 조사, Rust 개발 환경, headless/desktop 전환, udev·비root 접근·ALSA 별칭 | [기존 종합 기록](Jetson_Nano_작업_종합기록_2026-10-24.md), [개발 환경](Jetson_Nano_개발환경_설치와_모드전환.md) |
| 장치 대시보드 | FastAPI, 두 CSI 카메라·RTSP/웹 미리보기, 마이크·스피커, USB Pico 제어, systemd, 현재 IP로 활성화·비활성화 스크립트 | [장치 대시보드](Jetson_Nano_장치_대시보드.md), [소스·설치](../../apps/device-dashboard/README.md) |
| 스위치·눈 | SW4 GP9 수정과 6개 입력, MAX7219 회전·기기 좌우 보정, 50종 표정·짧은 동작·Stop·자동 소등 | [눈 좌우 교정](dashboard-check/2026-10-24/eye-side-correction/), [50종 검증](dashboard-check/2026-10-24/eye-expressions/) |
| 서보 | 6축 개별 슬라이더, lease·정지·미Arm 안전 경로, PCA9685 0x40/0x41 진단과 상세 상태 확장 | [개별 제어](dashboard-check/2026-10-24/servo-sliders/), [I2C 진단](dashboard-check/2026-10-24/servo-i2c/README.md) |
| 서보 회전폭 설정 | 대시보드 프로필 500~2500µs 복원, 보드 저장소·설치본·Pico 설정 읽기 확인 | [설정 검증](dashboard-check/2026-10-24/servo-pwm-range/README.md). 변경 후 자동 모터 이동·물리 180° 계측은 수행하지 않음 |
| 오디오·TTS | BA-R9 실제 청취·음량 설정, Typecast 문장 입력·별도 worker·연속 요청, 마이크 기본 +12dB·0~30dB·-1dBFS 피크 보호·WAV/RMS 표시 | [BA-R9](dashboard-check/2026-10-24/ba-r9/README.md), [TTS 입력](dashboard-check/2026-10-24/tts-input/README.md), [연속 TTS](dashboard-check/2026-10-24/tts-continuous/README.md), [증폭](dashboard-check/2026-10-24/microphone-gain/README.md) |
| 단발·연속 사진 분석 | GPT/JEV 단발 관찰, 10프레임·15종 행동 분석, 두 카메라 동시 관찰·SQLite 저장·검색·집계·CSV/JSONL·검토 라벨 | [10프레임 분석](10프레임_학습행동_분석과_대시보드.md), [관찰 DB와 Live](연속_관찰_DB와_GPT_Live.md) |
| GPT Live | 자유 대화/학습 QnA, 한국어 PCM·자막·사용량 저장, SW1 트리거 로직, 600초 제한·정상 종료·스피커 잠금 공유 | [실제 10초 세션·사진 분석·배포 결과](연속_관찰_DB와_GPT_Live.md). 현재 보드 경로는 반이중 |
| 교육 지침·대화 문맥 | 기존 교육 프롬프트를 음성 모델·QnA 백엔드에 적용, 최근 관찰·학습 대화를 제한된 참고 JSON으로 전달, 실제 API 설정 대조·DB 스냅샷 보존 | [후속 실기 확인](dashboard-check/2026-10-24/live-context/README.md). 관찰 2건·이전 대화 1건, API 설정 일치·9초 세션·정상 종료 확인 |
| Pico 공통 코드 | protocol 확장, Rust/Embassy 펌웨어, USB 브리지·capability·PCA 진단 상태 전달, Linux 빌드·flash 백업·읽기 검증 | [펌웨어](../../firmware/pico2-device-bench/README.md), [브리지](../../tools/pico-device-bench/README.md), [Linux 업데이트](Jetson_Nano_Linux_펌웨어_업데이트.md) |
| 영상·전원 진단 | LAN/로컬 MJPEG 비교, Argus 충돌·전압·OC·CPU·네트워크 상태 기록 | [지연 현장 진단](Jetson_Nano_카메라_지연_현장진단_2026-10-24.md), [단절·저전압 진단](Jetson_Nano_카메라_단절과_저전압_진단_2026-10-24.md) |
| 제작·제출·발표 | P5 출력 플레이트 안내와 배치 JSON/SVG, 3MF 수정, 제출 자료·발표 구성·기술 보강·PDF | [P5 출력 플레이트](../BOM/mechanical_v8/P5/PRINT_PLATES.md), [제출 자료](../제출자료.md), [발표안](../presentation/발표_가안_2026-10-24.md), [기술 보강](../presentation/기술보강_2026-10-24.md) |

## 이번 공유 전 재검증

| 검사 | 실행 환경 | 결과 |
| --- | --- | --- |
| 대시보드 전체 Python 테스트 | Windows 프로젝트 `.venv-learning`, `unittest discover -s apps/device-dashboard` | 최초 73개, 최종 스테이징 소스 **79개 통과** |
| 관찰·학습 공급자 테스트 | 같은 가상환경, `unittest discover -s tools/jetson` | 최초 68개, 최종 스테이징 소스 **72개 통과** |
| Pico protocol | 저장소 로컬 Rust 1.90, `--features std` | **12개 통과** |
| USB 브리지 | 저장소 로컬 Rust 1.90, locked/offline | **12개 통과** |
| Pico 펌웨어 로직 | 저장소 로컬 Rust 1.90, Windows host target | **16개 통과** |
| Linux 업로더·셸 검사 | Jetson | 인증 후 실행 결과는 아래 Jetson 검증과 원본 로그에 기록 |
| 대시보드·관찰 Python 재검사 | Jetson 실제 venv | **79 + 72 = 151개 통과** |
| Linux 업로더 방어 검사 | Jetson Python 3.8 | **11개 통과**, 실제 flash 없음 |
| Rust protocol·브리지·펌웨어 로직·runtime | Jetson Rust 1.90, locked/offline | **12 + 12 + 16 + 19 = 59개 통과** |
| Linux 셸 구문 | Jetson `bash -n` | **24개 파일 통과** |
| 서비스·API | Jetson 실기 | 대시보드·관찰·TTS 모두 active, `/api/health` 정상 응답 |
| 인증 정보·파일 크기 점검 | Windows 수정·신규 파일 전체 | 실제 키·비밀번호 미검출. 탐지 항목은 테스트용 값·Bearer 환경변수 참조. 최대 파일 약 2MB |

Windows 전역 Python의 Pydantic 버전은 프로젝트 요구 버전과 달라 해당 환경에서 오류가 났다. 프로젝트 가상환경의 지정 의존성으로 다시 실행해 통과했다. 전역 Rust도 Cargo lock v4를 지원하지 않아 저장소 로컬 Rust 1.90을 사용했다. Linux 업로더의 `fcntl`은 Windows에 없으므로 보드에서 검사해야 한다.

Windows 최초 검사 181개에 이어, 게시 대상 Python 소스·자산 76개를 Git index에서 별도 폴더로 내보내 재검사했다. 최종 스냅샷 기준 Windows **191개**, Jetson **221개** 검사가 통과했다. [Windows 검사 요약](dashboard-check/2026-10-24/git-share/verification.json), [Jetson 검사 요약·상태](dashboard-check/2026-10-24/git-share/jetson-validation/verification.json), [Jetson 개별 로그](dashboard-check/2026-10-24/git-share/jetson-validation/)를 함께 보관한다. 두 운영체제에서 같은 계약을 반복 확인한 수를 포함하며 독립 기능 412개가 구현됐다는 뜻은 아니다.

이번 공유 작업의 테스트는 외부 AI API를 호출하거나 모터를 구동하지 않는다. 이전의 실제 배포·유료 API 사용·청취 결과는 각 상세 문서의 당시 기록을 따른다.

## Git에 포함하는 자료와 로컬 보관 자료

- 공유: 소스, 설치 스크립트, 비밀값 없는 설정/환경 예제, Markdown, 재현 가능한 테스트, 허용된 진단 JSON·로그·화면, 기구/제출/발표 자료.
- 기존 추적 중인 UF2는 이번 변경도 보존한다. 새 빌드 캐시·대량 생성 파일을 일괄 추가하지 않는다.
- 로컬 보관: 실제 `.env`·API 키·SSH 인증 정보, `tmp/`, `.local-tools/`, `target/`, 가상환경, 새 생성 flash 백업·런타임 모델, 관찰 SQLite 및 WAL/SHM.
- 운영 DB·실행본은 각각 `/var/lib/300seconds-dashboard/`, `/opt/300seconds/`에 있다. Git checkout의 동기화와 실행 서비스 재배포는 별개다.
- `.gitattributes`로 셸/Python/Rust/공유 문서와 대시보드 자산의 LF를 지정해 Windows↔Linux 줄바꿈만으로 생기는 차이를 줄인다.

## 충돌을 줄이는 공동 작업 순서

1. Windows 또는 Jetson에서 작업을 시작하기 전에 `git status --short --branch`를 확인한다. 미커밋 작업이 있으면 먼저 해당 작업 브랜치에 커밋한다.
2. 깨끗한 작업 트리에서 `git switch main`과 `git pull --ff-only origin main`으로 최신 기준을 가져온다. fast-forward가 안 되면 작업을 덮어쓰지 않고 이력 차이를 확인한다.
3. 장치·기능별 브랜치를 만든다. 예: Windows `codex/windows-dashboard-20261024`, Jetson `codex/jetson-device-20261024`. 같은 브랜치·같은 파일을 양쪽에서 동시에 수정하지 않는다.
4. 한쪽에서 논리 단위로 커밋·push하고 GitHub에서 병합한 뒤, 다른 쪽은 깨끗한 상태에서 `main`을 fast-forward한다. 이 과정에서 다른 쪽의 작업이 남아 있으면 먼저 별도 브랜치에 보존한다.
5. 텍스트 충돌은 공통 조상과 양쪽 변경을 비교해 수동 통합하고 검사를 다시 실행한다. 펌웨어·3MF·PDF 같은 바이너리는 자동 병합하지 않고 두 버전을 보존해 선택한다.
6. 공유 완료 후 Windows·Jetson에서 `git rev-parse HEAD`와 `git rev-parse origin/main`, `git status --porcelain`을 비교한다. 해시 일치·미커밋 변경 없음이 소스 동기화 완료 조건이다.

```bash
# 양쪽 공통: 작업 트리가 깨끗한 상태에서 실행
git fetch origin
git switch main
git pull --ff-only origin main
git rev-parse HEAD
git rev-parse origin/main
git status --short --branch

# 새 작업 시작 예시: 실제 작업명으로 브랜치를 만든다.
git switch -c codex/jetson-device-20261024
# 수정·검사 후 변경할 파일을 명시하여 커밋한다.
git add tools/jetson/README.md
git commit -m "docs: record Jetson device checks"
git push -u origin HEAD
```

`reset --hard`, `clean -fd`, 강제 push로 다른 쪽 작업을 제거하지 않는다. GitHub를 교환 기준으로 사용하고 저장소 전체를 파일 복사로 덮어쓰지 않는다. 이 절차는 향후 동시 편집의 충돌 가능성을 줄이며 모든 미래 충돌을 자동으로 없애는 보장은 아니다.

## 남은 실기 확인

추가된 [3D 프린트 출력 메모](<../3D 프린트 출력상황.md>)도 함께 공유한다. 원본의 완료·진행 중·상태 미기재 구분을 보존하고 실제 STL로 연결했다. 상태 미기재를 대기·미완료로 추정하지 않았다.

### Jetson에서 가져온 원본 요구사항 메모

| 원본 메모 | 현재 반영·남은 범위 |
| --- | --- |
| [GPT Live 시작 때 학습 문맥이 부족함](<gpt-live 해결 해야할 문제.md>) | 후속 교육 지침·최근 카메라 관찰·이전 학습 대화 참조를 구현하고 전달·API 설정 일치를 검증했다. 장기 학습 효과·모든 상황의 답변 품질을 입증한 것은 아님 |
| [태블릿 학습 화면·키워드 자동 연동](<구현 되면 좋을 듯한 기능.md>) | 향후 제안으로 보존. 태블릿 연결·화면 캡처·앱 사용 분석은 이번 구현 범위에 없음 |
| [화장실·휴식·대화 터치 버튼 역할](<터치 센서 버튼의 작동 방식.md>) | 원본 역할 제안으로 보존. 현재 SW1 Live 트리거와 다르므로 실제 배선·버튼 매핑과 혼동하지 않는다. 전체 역할 적용은 후속 설계 대상 |

### 추가 실기 검증 대상

- Nano 입력 저전압·반복 OC 경고와 카메라 Argus 충돌의 장시간 안정성. 과거 약 4.50~4.56V 관측과 PCA 통신 복구를 구분한다.
- PCA는 후속 점검에서 0x41 응답·초기화·fault 0이 확인됐지만 최초 무응답 원인은 미확정이다. 축별 기구 결합·끝점·하중·전원 시험은 별도다.
- GPT Live의 보드 스피커 청취, SW1 실제 누름·해제에 의한 시작/종료, 10분 연속 운용, AEC·음성 끼어들기.
- 정답 데이터에 의한 행동 인식 정확도 평가와 최종 학습 동반자 전체 시나리오.
- HDMI 실물 표시·키보드 로그인, SD 백업·복원, USB/서비스 장애 회귀.

초기 실패·후속 복구·미검증 항목을 함께 보존한다. 코드 공유가 완료됐다는 사실을 전원·카메라·서보·대화 제품 전체의 안정성 검증 완료로 해석하지 않는다.
