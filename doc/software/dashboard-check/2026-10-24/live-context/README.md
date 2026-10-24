# GPT Live 교육 프롬프트·DB 참조 적용 검증

2026-10-24 KST. 이전 **「GPT Live 학습 프롬프트 작성」** 대화(ID `01a16c54-cf09-7d82-9c33-1b9f193816aa`)의 교육 프롬프트를 복구해 적용했다. 원문 답변 ID는 `msg_0427ededcd73d1eb016adc3ee64f4c8191a9c79dea8826320e`다.

## 변경 전 점검

실제 Nano 설치본을 읽은 `before-audit.log`에서 상세 교육 지침과 DB 참조가 모두 없음을 확인했다. 당시 Live에는 짧은 기본 멘토 지침과 인사 메시지 하나만 전달되고 있었다. 프런트 지침 SHA-256은 `75be8ef697eeac9b098d9c04b8a186dfcbdc60c9f91963a583b3f089cf57ac64`였다.

## 적용 내용

- [복구 원문](../../../../../tools/jetson/prompts/mentor-original-20261024.txt), [현재 적용문](../../../../../tools/jetson/prompts/mentor-education.txt), [출처·조정 내역](../../../../../tools/jetson/prompts/mentor-manifest.json).
- 원문의 따뜻한 말투, 한 번에 질문 하나, 관찰→이유→비교·예측→확인→자기 설명, 단순 사실에 먼저 답하기, 막히면 힌트·예시와 필요시 정답·이유 설명을 음성 모델과 Responses 백엔드 모두에 적용했다.
- 이전 대화의 **시간당 5분·하루 20분**은 이 대화에서 사용자가 요청·승인한 **한 세션 10분**과 달라서 적용하지 않았다. 600초 제한을 유지하고 30초·10초 전 앱 안내를 추가했다. 반이중 오디오의 제한도 실제 동작에 맞게 반영했다.
- 세션 시작 시 최근 30분 성공 관찰 중 센서별 최신 한 건, 같은 기간의 성공/누락 수·행동 빈도와 최근 24시간 학습 대화 중 사용자 발화가 있는 종료 세션 최대 두 개의 짧은 발화 일부를 선택한다. 단순 인사만 있는 세션은 이전 학습 대화로 사용하지 않는다.
- 참조 JSON은 최대 6,500 UTF-8 bytes로 제한하고, 추가 LLM 요약 요청은 보내지 않는다. 원본 사진·원음은 포함하지 않는다. 과거 사용자가 현재 사용자와 같다고 가정하지 않으며 관찰을 의도·집중력·행동 시간으로 확정하지 않도록 지시한다.
- 참조는 `session.input`의 **user 참고 자료**로 전달하고 Responses 백엔드에도 `response.item.create`의 user 메시지로 전달한다. DB 문장이나 과거 발화는 시스템 지시문으로 승격하지 않는다.
- API가 반환한 `session.started`의 실제 프런트 지침·백엔드 지침·시작 메시지를 요청과 비교한다. 일치하지 않으면 적용됐다고 표시하지 않고 세션을 실패 처리한다.
- SQLite 스키마를 1→2로 추가 이행하고 `live_contexts`에 시작 시점 참조·해시·기록 ID·교육 버전·API 확인 결과를 고정 저장한다. 이후 DB가 바뀌어도 과거 세션의 참조는 보존한다.

## 실제 확인

`verification.json`의 검사 전부 통과:

| 항목 | 실제 결과 |
| --- | --- |
| 교육 버전 | `mentor-education-v1` |
| 적용 교육 원문 SHA-256 | `4bfd460483f51ec0d2b995403ad0ad24d7e87465f8ba3193a97156c6108b12d4` |
| 프런트 지침 API 일치 | true |
| 백엔드 지침 API 일치 | true |
| 시작 DB 참조 API 일치 | true |
| 참조 관찰 ID | 563, 564 |
| 이전 학습 대화 | 1건 |
| 참조 JSON | 2,444 bytes |
| 실기 Live 세션 | 9.0초, 정상 종료·최종 사용량 확정 |
| 보드 출력 PCM | 336,000 bytes |

DB 참조와 교육 지침의 **전달·설정 일치**를 확인한 시험이다. 모든 교육 상황에서의 답변 품질, 실제 스피커 청취, 10분 전체 대화 또는 마무리 안내 음성의 실청취 시험은 별도다.

대시보드 **79개**, 공급자·기존 분석 **72개**, 총 **151개** 회귀 검사 통과. 실제 화면의 적용 확인·참조 건수·조회 링크와 콘솔 오류 없음도 확인했다. `dashboard-applied.png`는 실제 운영 화면이다.

백업: `/var/lib/300seconds-dashboard/backups/live-context-20261024-140208`. 변경 전 소스와 SQLite backup API로 만든 `learning-before.sqlite3`을 보존했다. 카메라 수집은 적용 전 켜져 있던 상태를 복원했다. API 키나 계정 인증값은 검증 파일에 저장하지 않았다.

## 검증용 조회

- `GET /api/learning/live/policy`: 현재 서비스가 사용하는 교육 지침 본문·버전·출처·해시.
- `GET /api/learning/live/context`: 다음 대화에 사용할 현재 DB 참조.
- `GET /api/learning/live/context?session_id=...`: 해당 세션 시작 때 고정한 실제 참조와 API 적용 확인 결과.
- `GET /api/learning/live/history?session_id=...`: 자막·참조 스냅샷·교육 적용 기록.

공식 연결 근거: [시작 시 텍스트 문맥과 지침](https://developers.openai.com/api/docs/guides/live-conversations), [Responses 위임·user 자료 전달](https://developers.openai.com/api/docs/guides/live-delegation).
