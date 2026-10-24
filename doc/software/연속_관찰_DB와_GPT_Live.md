# 두 카메라 연속 관찰 DB와 GPT Live

2026-10-24 KST. 기존 장치 대시보드에 `관찰·Live` 검증실을 구현하고 사용자의 명시적 승인 후 **Nano에 배포했다.** 실제 OpenAI 이미지 분석·DB 연속 저장, GPT Live 한국어 인사 음성 PCM·자막·정상 종료를 확인했다. 물리 스피커 청취 확인, SW1 실물 누름, 전체 10분 대화는 아직 별도 검증이 필요하다.

## 수집과 저장

- 보드 대시보드가 운영되는 동안 센서 0·1에서 각각 최신 JPEG 한 장을 **10초 간격**으로 읽는다. 같은 시점의 두 장을 요청 한 번으로 전송하고 카메라별 결과를 독립 저장한다. 한 카메라가 고장 나도 다른 카메라의 자료는 수집한다.
- 이미 CSI를 소유한 미디어 worker의 JPEG를 재사용한다. CSI나 마이크를 추가로 열지 않는다. 프레임 수정 시각, worker 세대, 프리뷰 상태를 검증하며 남아 있는 오래된 JPEG를 새 관찰로 전송하지 않는다.
- `gpt-4.1-mini` + Responses API의 엄격한 JSON Schema로 **한국어 장면 설명, 키워드 최대 8개, 관찰 가능한 행동 코드, 근거 명료도, 불확실성**을 받는다. 모델은 worker 환경의 `LEARNING_VISION_MODEL`로 변경할 수 있다.
- 프롬프트 `dual-observation-v3`은 사진별 필수 객체 키와 고정 센서 번호를 사용한다. 초기 v1/v2의 간헐적 응답 검증 오류와 그 후 전송 보류 기록은 삭제하지 않고 보존했다. 휴대전화가 단순히 놓여 있는 상태를 실제 사용 행동으로, 사람 뒤의 빈 의자를 학습자의 자리비움으로 단정하지 않도록 지침을 보완했다.
- 행동 코드는 `reading`, `writing`, `typing`, `phone_use`, `looking_away`, `eating_drinking`, `handling_objects`, `person_present`, `seat_empty`, `unknown`이다. 이전 10프레임·15개 행동 분석은 별도 버튼으로 유지된다.
- 한 장으로 지속 시간·내적 집중력·의도·감정·사람의 신원을 추론하지 않는다. 휴대전화 사용이 관찰됐다는 결과와 학습 이탈이라는 판단을 구분한다. 서로 다른 카메라에서 같은 사람이 관찰될 수 있으므로 두 카메라 합계를 사람 수로 해석하지 않는다.
- 캡처와 API 요청은 별도 task다. 대기열은 최대 두 묶음이며 초과는 `dropped`로 기록한다. 지연을 따라잡으려고 몰아서 촬영하지 않는다. 대시보드 탭을 닫아도 서버 수집은 계속한다.
- 중지를 누르면 미전송 대기 자료는 `cancelled`로 기록한다. 이미 전송한 요청은 완료 후 DB에 저장할 수 있다. 같은 실패 요청은 재전송하지 않는다. 일반 오류 뒤에는 새 전송을 60초 보류하며 인증·429 오류는 수집을 중지한다. 디스크 여유가 100 MiB 미만이면 수집을 중지한다.
- 기본 DB: `/var/lib/300seconds-dashboard/learning.sqlite3`. `DASHBOARD_LEARNING_DB`로 변경한다. SQLite WAL, 외래키, 스키마 버전 1을 사용하며 재시작 시 미완료 관찰·Live 세션을 `interrupted`로 표시한다.
- 원본 JPEG·음성·API 키는 DB에 저장하지 않는다. 사진 SHA-256, 파일 시각, 세대 정보는 저장하지만 원본이 없으므로 나중에 동일 사진을 다시 분석할 수는 없다. 결과 텍스트는 누적 보존하고 자동 삭제하지 않는다.
- 수집 켜기·끄기는 DB에 저장하며 재시작 후 복원한다. 최초 설치는 `LEARNING_AUTOSTART=1`로 켜지도록 구성했다. 이후 사용자가 중지한 상태는 자동으로 켜지지 않는다.

## DB를 나중에 분석하는 방법

| 테이블 | 역할 |
| --- | --- |
| `batches` | 요청 묶음, 모델·프롬프트 버전, request ID, 확인된 토큰 사용량, 구조화된 원 응답 |
| `observations` | 카메라·UTC 촬영 시각·프레임 해시·상태·설명·키워드·행동·불확실성·연결된 Live 세션 |
| `annotations` | 사람이 검토한 라벨과 메모. 모델 결과를 덮어쓰지 않음 |
| `live_sessions` | 모드·시작/종료·SW1/대시보드 시작 경로·종료 사유·최종 사용량 확정 여부 |
| `live_events` | 사용자/AI 발화 조각·세션 기준 시작/종료 ms·수신 시각·백엔드 사용량 이벤트 |
| `settings` | 재시작 후 복원할 수집 상태 |

화면에서 기간, 카메라, 정확한 키워드 또는 행동 코드로 검색한다. 행동·키워드 빈도, 카메라별 성공·누락 수와 확인된 사용 토큰을 표시한다. 요약 API는 UTC 시간대별 집계도 제공한다. 한 요청의 사용량은 카메라 두 개 결과가 있어도 한 번만 합산한다. 네트워크 오류·거부·응답 검증 실패 시 실제 청구와 사용량이 확인되지 않을 수 있으므로 이 값은 계정 청구 총액이 아니다.

표의 검토 라벨은 CSV/JSONL에 함께 포함한다. API로 검토 메모도 저장할 수 있다. 원래 모델 출력, 사람이 검토한 값, 모델·프롬프트 버전을 구분해 평가 자료로 사용한다. CSV 수식 실행 문자는 이스케이프한다. JSONL은 값과 배열을 원형으로 유지한다. 내보내기는 페이지 단위로 읽고 요청 시점의 조회 종료 시각을 고정한다.

예: 한국 시간 날짜·카메라별 필기 관찰 횟수. `success`만 행동 집계에 사용하고 실패·누락 비율을 별도로 확인한다. 이것을 실제 필기 시간으로 확정하면 안 된다.

```sql
SELECT strftime('%Y-%m-%d', o.captured, 'unixepoch', '+9 hours') AS date_kst,
       o.camera, count(*) AS writing_observations
FROM observations o, json_each(o.actions_json) a
WHERE o.status = 'success' AND a.value = 'writing'
GROUP BY date_kst, o.camera;
```

운영 DB를 백업할 때 WAL 파일을 무시하고 본체 파일만 복사하지 않는다. Python `sqlite3.Connection.backup()`이나 SQLite `.backup`으로 일관된 스냅샷을 만든다. 장기 보존은 정기 스냅샷과 CSV/JSONL 보관을 권장하며, 보관기간 변경·삭제 정책은 별도로 정한다.

## GPT Live

- 요청한 **`gpt-live-1`**을 `/v1/live/sessions` primary WebSocket으로 연결한다. 기존 Realtime API 이벤트를 혼용하지 않는다. `session.start` → `session.started` 후 24 kHz mono PCM16 음성을 양방향 전송한다.
- 한국어 `noeul` 음성, 자유 대화/학습 QnA 모드를 제공한다. 복잡한 질문은 Responses 위임 백엔드 `gpt-6-luna`로 처리한다. 백엔드 모델은 `LEARNING_BACKEND_MODEL`로 변경한다. 외부 도구는 부여하지 않는다.
- 대시보드의 **대화 시작·종료**, 기기의 **SW1(GP6)**으로 시작·종료한다. SW1은 기본 학습 QnA다. USB 세션마다 최초 입력은 기준값만 잡으므로 부팅·재연결·버튼을 계속 누르고 있는 상태로 자동 대화를 시작하지 않는다. 짧은 누름도 상태의 press counter 변화로 검출한다.
- 카메라 분석과 Live는 동시에 운영할 수 있다. 마이크는 기존 `Audio` 소유자의 실시간 PCM 구독으로 공유한다. 기존 TTS·시험음·녹음 재생과 같은 스피커 잠금을 사용한다.
- **현재 보드 경로는 반이중**이다. AEC가 검증되지 않아 AI 출력 재생 중 마이크 입력을 무음으로 전송하며 발화가 끝난 후 다시 듣는다. API 자체의 full duplex 기능과 보드의 음향 처리를 구분한다. 말로 끼어드는 기능은 검증/지원 완료로 주장하지 않는다.
- 브라우저가 닫혀도 세션은 계속되지만 서버와 별도 provider worker가 각각 약 **600초** 제한을 강제한다. 종료 시 입력·출력을 멈추고 `session.close` 뒤 `session.closed`를 기다려 최종 사용량을 저장한다. 시간 초과/연결 손실 시 미확정으로 남기고 자원을 해제한다. 자동 재연결하지 않는다.
- 자막은 사용자·AI와 타임스탬프를 구분해 저장한다. 자막과 음성 재생 성공은 별개다. GPIO 스위치 연결 시험·실제 스피커 청취·10분 연속 안정성은 배포 후 확인할 항목이다.

## 인증 경계와 API

OpenAI 키는 기존 전용 `300seconds-observer.service`만 소유한다. 새 worker는 대시보드 venv의 `websockets==13.1`을 사용한다. 대시보드는 허용된 Unix socket RPC만 보내며 브라우저에 키를 반환하지 않는다. 기존 5회짜리 GPT 테스트 장부는 초기화하거나 변경하지 않는다. 새 연속 수집은 별도 기능으로 정상 API 요금이 발생한다.

변경 API에는 기존 동일 Origin·CSRF 토큰 검사를 적용한다. 로그인 기능은 기존과 마찬가지로 없으므로 신뢰하는 LAN 범위에서만 사용한다. 이 기능은 외부 공개용 인증을 새로 구성하지 않는다.

| API | 동작 |
| --- | --- |
| `GET /api/learning` | 수집·대기열·Live·공급자 설정 상태 |
| `POST /api/learning/collection` | `{"enabled":true/false}` |
| `GET /api/learning/records` | `since`, `until` Unix 초, `camera`, `keyword`, `before`, `limit` |
| `GET /api/learning/summary` | 기간·카메라·키워드별 통계와 시간대별 성공/누락 |
| `GET /api/learning/export` | 같은 필터, `format=csv/jsonl` |
| `POST /api/learning/records/{id}/annotation` | `label`, 선택 `note` |
| `POST /api/learning/live/start` | `{"mode":"study"}` 또는 `chat` |
| `POST /api/learning/live/stop` | 대화 종료 |
| `GET /api/learning/live/history` | 최근 세션·자막, `session_id`, 이벤트 `before` |
| `GET /api/learning/live/export?session_id=...` | 세션 메타데이터와 원 발화 조각 JSONL |

## 검증·배포

2026-10-24 Nano `/tmp`에서 **대시보드 73개, 공급자·기존 분석 68개, 총 141개 검사 통과**. 공급자 출력 보완 후 해당 공급자 검사 5개를 다시 통과했다. 실제 배포·사진 전송·음성 시험은 자동 승인 검토의 최초 차단 후 사용자의 명시적 승인을 받고 수행했다.

- 실제 사진 분석 사전 시험: 입력 1,038·출력 224토큰, 두 카메라 모두 설명·키워드·행동 반환. GPT Live 시작 후 즉시 종료 시 최종 사용량 확정.
- 실제 보드 Live 시험: **10.0초 세션**, 마이크 입력 PCM 441,600 bytes, 출력 PCM 360,000 bytes(24 kHz mono S16, 약 7.5초) 처리. "안녕, 나는 AI 학습 친구야. 오늘 뭐 이야기하거나 공부해볼까?" 자막 저장, `session.closed` 최종화 확인, 정상 종료와 스피커 잠금 해제.
- 실시간 분석과 Live를 함께 실행했다. 검증 시점 사진 분석 **카메라별 30건, 총 60건 성공**. 이후에도 수집을 켜 놓았다. v2 적용 직후 최근 20건은 모두 성공했고, 초기 형식 오류·보류는 별도 기록했다. 모든 행동의 인식 정확도를 정답 데이터로 검증한 것은 아니다.
- 최종 v3 적용 뒤 **24건 연속 성공**을 확인했다. 센서별 최근 프레임 간격은 약 10초이고, 수집 enabled·오류 없음·공급자 연결 상태를 확인했다. [최종 상태·기록·집계](dashboard-check/2026-10-24/learning/final-verification.json).
- 실제 API에서 CSRF 없음·다른 Origin 403, 잘못된 센서 번호 422, 카메라 0 CSV 다운로드 200과 레코드 제공 확인.
- 실제 브라우저의 상태·자막·종료 표시와 콘솔 오류 없음 확인. Wi‑Fi 지연으로 이력 조회가 늦어졌다고 전체 수집·Live를 오프라인 처리하지 않도록 분리했고 조회 타임아웃을 보완했다. 기기의 Wi‑Fi·전원 안정성 자체를 해결한 변경은 아니다.

백업: `/var/lib/300seconds-dashboard/backups/learning-feature-20261024-130946`. 설치 스크립트의 줄바꿈 처리 오류는 소스 적용 전 발견해 기존 서비스를 복구한 뒤 수정·재배포했다. 최초 원본과 공급자 후속 보완본 백업을 보존했다. 실기 결과 원본은 [실연결 검증 JSON](dashboard-check/2026-10-24/learning/live-verification.json), [공급자 사전 시험](dashboard-check/2026-10-24/learning/provider-preflight.json)을 참조한다.

## 유료 API와 예상 운영 비용

무료 모델이 아니다. 2026-10-24 확인한 GPT‑4.1 mini의 표준 단가는 입력 **$0.40/100만 토큰**, 출력 **$1.60/100만 토큰**, 캐시 입력 $0.10/100만 토큰이다. 여기서는 보수적으로 캐시 할인 없이 계산한다. [공식 모델 가격](https://developers.openai.com/api/docs/models/gpt-4.1-mini).

성공한 실제 두 카메라 요청 **54회**, 입력 57,695·출력 13,579토큰을 기준으로 계산한 확인분 비용은 약 **$0.0448**다. 오류·미확인 응답의 비용과 세금·환율은 포함하지 않았으며 계정 청구액을 조회한 것이 아니다. 이 평균 사용량으로 10초 간격 정상 운영을 환산하면:

| 운영 시간 | 두 카메라 사진 분석 예상 비용 |
| --- | ---: |
| 1시간 | 약 $0.30 |
| 하루 8시간 | 약 $2.39 |
| 하루 24시간 | 약 $7.17 |
| 24시간 × 30일 | 약 $215 |

실제 요금은 사진 내용·설명 길이·캐시·실패·모델 가격 등에 따라 달라진다. API 요청은 시간당 360회, 사진은 두 카메라 합계 시간당 720장이다. 화면의 중지 버튼으로 추가 전송을 멈출 수 있으며, 이미 전송된 요청은 완료 후 저장될 수 있다. 계정 API 크레딧이 남아 있더라도 모델이 무료가 되는 것은 아니다.

GPT Live는 별도 **$0.05/분**, 10분당 **$0.50 + 위임 백엔드 모델 사용료**다. 실제 세션 길이를 초 단위로 청구한다. [공식 Live 요금](https://developers.openai.com/api/docs/pricing).

```bash
cd apps/device-dashboard
/opt/300seconds/dashboard/venv/bin/python -B -m unittest -v test_learning test_audio test_hardware test_eye_expressions test_observer_api test_servo_controls test_tts_worker
cd ../../tools/jetson
/opt/300seconds/dashboard/venv/bin/python -B -m unittest -v test_learning_provider test_study_window test_jev_study_observer test_openai_study_observer
```

전체 설치는 기존 `apps/device-dashboard/install.sh`를 사용한다. 운영 중 장치 소유자가 재시작되므로 짧은 카메라·오디오 중단이 생긴다. 현재 테스트 중인 저장소에는 다른 장치 변경도 있어 전체 설치/배포 전 적용 파일을 확인하고 백업한다. 임시 테스트 위치와 로그는 [검증 폴더](dashboard-check/2026-10-24/learning/)에 기록한다.

공식 근거: [이미지 입력](https://developers.openai.com/api/docs/guides/images-vision), [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs), [GPT Live WebSocket](https://developers.openai.com/api/docs/guides/voice-websockets), [세션·자막·종료](https://developers.openai.com/api/docs/guides/live-conversations), [Responses 위임](https://developers.openai.com/api/docs/guides/live-delegation).
