# pstack 코드 점검과 최적화

2026-10-26 현재 Windows 작업본의 대시보드, 관찰 서비스, 장치 통신과 Pico 펌웨어를 점검했다. 재현한 결함 6건을 수정하고 분석 화면의 중복 DB 조회를 줄였다. 수정 범위는 로컬 소스이며 Jetson 배포와 펌웨어 업로드는 수행하지 않았다.

## 설치와 적용

`michael-denyer/pstack-claude`의 Codex 플러그인 `pstack` 0.9.102를 설치했다. `codex plugin list`에서 installed, enabled 상태를 확인했다. 원본은 Lauren Tan의 pstack이며 설치한 버전은 Codex 대응을 포함한 커뮤니티 포트다.

```powershell
codex plugin marketplace add michael-denyer/pstack-claude
codex plugin add pstack@pstack-claude
```

설치 경로는 `C:/Users/Administrator/.codex/plugins/cache/pstack-claude/pstack/0.9.102`다. 이번 점검에서는 설치된 `poteto-mode`, `how`, `swarm` 지침과 Codex 도구 대응 문서를 직접 읽어 적용했다. 다음 턴부터 스킬 이름으로 사용할 수 있다. 자동 라우팅용 SessionStart 훅의 신뢰 설정은 변경하지 않았다. 자동 적용을 원할 때 Codex의 `/hooks`에서 신뢰를 설정해야 한다. 수동으로는 `poteto-mode로 이 코드를 점검해줘`와 같이 요청한다.

기존 서보, 프로토콜, 펌웨어의 미커밋 변경을 포함한 작업본을 검토했다. 기존 변경과 삭제된 문서는 되돌리지 않았다. 이 점검으로 커밋, 푸시, PR 생성, 실제 장치 명령은 실행하지 않았다.

## 구조와 사용 흐름

대시보드의 `app.py`가 카메라, 오디오, Pico 브리지와 각 제어 객체의 수명을 관리한다. `Learning`은 10초마다 최신 카메라 프레임을 확인하고 SQLite에 수집 기록을 만든다. 최대 2개 배치 큐에서 관찰 서비스로 분석을 전달한다. `Store`는 결과와 사용량을 저장하고 동일 관찰 내용은 원본 기록을 참조한다.

수동 Decisions 요청은 `study_window.py`에서 두 카메라의 10쌍을 수집한다. `StudyReaction`은 분석 결과를 유한한 음성, 빛, 서보 반응으로 변환한다. Live는 대시보드가 스피커 잠금과 PCM 입출력을 소유하고 관찰 서비스가 외부 API 연결을 소유한다. TTS 키와 합성은 별도 worker 경계 안에 있다.

서보 제어는 브라우저 소유권과 epoch, USB 세션, 펌웨어 lease와 OE 제어를 거친다. 검토한 경로에서 lease와 epoch 검사를 우회하는 결함은 확인하지 못했다. 이 판단은 실제 정지 시간이나 물리 이동 범위의 검증을 대신하지 않는다.

## 수정한 결함

| 우선순위 | 재현 조건과 영향 | 수정과 회귀 검증 |
| --- | --- | --- |
| P2 | 동일 내용의 관찰 신뢰도가 0.9에서 0.1로 내려가도 중복 기록이 원본의 0.9를 물려받는다. 통계와 Live 문맥에서 불확실한 관찰을 확실한 것으로 처리할 수 있다. | `learning_store.py`의 중복 행에 현재 신뢰도를 저장한다. 관찰 2개 중 확실한 학습 1개, 판단 불가 1개로 집계하고 눈·Live 문맥에도 0.1을 전달하는지 검사한다. |
| P2 | 시간 종료 후 120초가 지나도 분석이 pending이면 빈 시간별 통계가 확정된다. 분석이 끝나도 캐시가 계속 0으로 남는다. | 해당 시간에 pending 행이 있으면 확정하지 않는다. 종료 121초 뒤 pending, 이후 성공하는 경우를 검사한다. 캐시 버전을 변경해 시간별 통계를 재계산한다. |
| P2 | Live 연결 대기 중 Stop을 눌러도 첫 응답 뒤 `aplay`와 PCM 구독이 시작될 수 있다. | 핸드셰이크와 Stop을 함께 기다린다. Stop이면 연결을 닫고, 대기 작업 정리 후와 오디오 프로세스 생성 후에도 정지를 재확인한다. 응답 없는 연결과 핸드셰이크 정리 중 취소를 검사한다. |
| P2 | USB 브리지 프로세스가 살아 있지만 telemetry가 멈추면 재연결 버튼의 `start()`가 아무 일도 하지 않는다. | 출력 소유자를 먼저 닫고 기존 브리지를 정지한 뒤 다시 시작한다. 정지·시작 순서와 동시 재연결 거부를 검사한다. |
| P2 | Decisions 사진에 저장된 필드 `camera_role` 대신 `role`을 읽어 얼굴·책상 사진이 모두 combined로 표시된다. | `camera_role`을 사용한다. 얼굴 카메라가 0번일 때와 1번일 때 모두 각 사진의 역할을 검사한다. |
| P3 | Windows 기본 CP949 환경에서 한국어 UTF-8 `installation.json`을 읽지 못해 대시보드 import와 테스트가 실패한다. | 번들 설정 JSON을 UTF-8로 명시해서 읽는다. 최종 대시보드 테스트를 `-X utf8` 없이 실행한다. |

기존 중복 행에 저장되지 않은 신뢰도는 복구할 수 없다. 과거 `confidence=NULL` 행은 호환성을 위해 원본 신뢰도로 해석한다. 캐시 재계산이 소실된 과거 신뢰도를 복원하는 것은 아니다.

## 분석 조회 최적화

실제 자료 일별 화면을 구성할 때 시간별 보고서, 비교, 추세 패널이 같은 원본 구간을 반복 조회했다. `view()`가 해당 요청에서만 사용하는 `read_rows` 캐시를 만들고 `refresh()`, `_report()`, `_range()`로 전달한다. 캐시는 최대 8개 구간이며 요청이 끝나면 폐기된다. 다음 요청은 새 분석 결과를 읽는다.

대안으로 집계 결과 자체를 캐싱하는 방식을 검토했다. 이번에는 원본 행 조회를 재사용해 refresh와 각 패널이 같은 부분 시간 자료를 읽도록 했다. 상태를 인스턴스에 저장하지 않아 서로 다른 요청의 캐시가 섞이지 않는다.

독립 리뷰에서 전체 이력 재계산 시 메모리 증가 위험을 확인해 무제한 캐시를 8개 구간으로 제한했다. 31시간짜리 재계산 시험에서도 캐시의 현재 크기는 8이었다.

| 측정 항목 | 변경 전 | 변경 후 |
| --- | --- | --- |
| 준비된 캐시의 실제 자료 일별 화면 1회당 원본 조회 | 16회 | 4회 |
| 교대 실행 5회 각각의 조회 수 | 16, 16, 16, 16, 16 | 4, 4, 4, 4, 4 |
| 캐시 버전 필드를 제외한 응답 일치 | 기준 | 전부 일치 |
| 실패한 측정 요청 | 0 | 0 |

합성 관찰 1배치, 두 카메라, 당일 09:15 시점으로 측정했다. 비교 기준 소스는 커밋 `7de06dd40ae49e22ce14e60e53250bf160ad94b6`의 `log_analytics.py`다. 이는 SQL 조회 횟수의 감소다. Jetson의 전체 응답 시간이나 CPU 개선율을 측정한 결과가 아니다.

## 검증

최종 결과는 아래 실행 기록을 기준으로 한다. 테스트에서는 실제 장치와 외부 AI API를 호출하지 않았다.

| 범위 | 결과 | 기록 |
| --- | --- | --- |
| 대시보드 Python | 163개 통과 | `tmp/pstack-review-2026-10-26/dashboard-final.log` |
| Jetson 관찰·Decisions Python | 84개 통과 | `tmp/pstack-review-2026-10-26/jetson-after.log` |
| Rust 공통 프로토콜 | 13개 통과 | `tmp/pstack-review-2026-10-26/protocol-local.log` |
| Rust Pico 펌웨어 호스트 로직 | 24개 통과 | `tmp/pstack-review-2026-10-26/firmware-host.log` |
| Rust USB 브리지 | 13개 통과 | `tmp/pstack-review-2026-10-26/bridge-host.log` |
| 조회 횟수 비교 | 전후 각각 5회, 결과 일치 | `tmp/pstack-review-2026-10-26/query-comparison.json` |

대시보드와 관찰 서비스 검증 명령은 다음과 같다.

```powershell
./.venv-learning/Scripts/python.exe -B -m unittest discover -s apps/device-dashboard -p 'test_*.py'
./.venv-learning/Scripts/python.exe -B -m unittest discover -s tools/jetson -p 'test_*.py'
```

Rust는 시스템 기본 Cargo 1.75 대신 저장소의 `.local-tools/rustup/toolchains/1.90.0-x86_64-pc-windows-msvc/bin`과 `.local-tools/cargo`를 사용했다. 펌웨어는 `--target x86_64-pc-windows-msvc --lib`로 호스트 로직을 검사했다. 임베디드 바이너리 빌드나 업로드 결과가 아니다.

`software/crates/host-core`의 테스트는 Linux의 `clock_gettime`, `flock`, 파일 디스크립터 API에 의존해 Windows 빌드가 실패했다. 이 부분은 Linux에서 다시 검사해야 하며, 통과한 297개 테스트에 포함하지 않았다.

## 남은 확인과 개선 우선순위

1. Jetson에서 Linux 전용 Rust runtime을 빌드하고 테스트한다. 이번 심층 검토의 중심은 현재 대시보드, 관찰 서비스, Pico 통신과 펌웨어였으며 전체 Rust 서비스 구현을 모두 검토한 것은 아니다.
2. 배포 전 실제 USB 브리지 재연결과 Live 연결 중 Stop을 확인한다. 카메라, 전원, 서보 각도와 정지 시간도 실기에서 확인한다.
3. 브라우저에서 분석·제어 화면의 실제 조작을 확인한다. 이번 사용 흐름 검토는 소스 추적과 HTTP·소유권 회귀 테스트이며 브라우저 전체 조작 시험은 아니다.
4. 대시보드는 신뢰하는 LAN에서 사용하는 설계다. 외부 공개가 필요하면 사용자 인증과 네트워크 접근 제어를 별도 작업으로 설계한다.
5. 대규모 모듈 분리는 구체적인 변경 필요가 생길 때 진행한다. 이번에는 실행으로 확인한 결함과 중복 조회를 우선 수정했다.

`Prove It Works` 원칙에 따라 결함을 회귀 테스트로 재현했고, `Laziness Protocol`에 따라 기존 모듈과 저장 형식을 유지하는 작은 변경을 선택했다. 독립적인 분석·취소 처리 리뷰에서 찾은 경합과 메모리 문제도 반영했다. 실제 장치 검증과 배포는 남아 있다.

최종 소스와 테스트, 실행 기록, 보고서는 별도 `gpt-6-astra` 에이전트가 읽기 전용으로 검토했다. 차단할 코드 결함은 보고되지 않았다. 사용할 수 있는 모델이 GPT 계열이므로 서로 다른 제공자·모델 계열을 통한 검토는 수행하지 못했다. 이 최종 리뷰는 기록을 검사한 것이며 테스트를 재실행한 것은 아니다.
