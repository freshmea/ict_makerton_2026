# OpenAI Decisions 카메라 테스트와 예산

후속 변경: 아래는 초기 3회 단일 사진 시험 기록이다. 현재는 [10프레임 대시보드 분석](10프레임_학습행동_분석과_대시보드.md)으로 확장해 최대 5회·이미지 10장·질문 24개 이하·텍스트/질문 20KB 이하를 허용한다. 기존 3회를 보존해 장부를 `/var/lib/300seconds-observer/openai-budget.json`으로 이관했다. 최종 누적은 5회·추정 $0.0013735이며 현재 로컬 호출 제한에 도달했다. 아래의 당시 장부 경로·3회 제한·대시보드 미연동 설명은 초기 시점의 기록이다.

2026-10-24 KST. 사용자가 OpenAI API에10달러를 결제했다고 알리고 사용량을 아껴 테스트하도록 요청했다. **Nano에서 OpenAI Decisions의 실제 텍스트1회·사진2회, 총3회 요청이 성공했다.** 표준 단가와 응답 usage로 계산한 합계 추정 비용은 **$0.0003067**이다. 계정 전체 잔액·다른 애플리케이션의 비용을 조회한 값은 아니다.

## 테스트 계획과 지출 제한

1. 과금 없는 모델 목록 조회로 기존 키 인증과 `gpt-6-luna` 접근을 확인한다.
2. 짧은 텍스트 predicate 요청1회로 실제 Decisions 계약·usage를 확인한다.
3. 현재 카메라0의 JPEG1장을 `detail=low`로 보내 결과·관찰 가능성을 확인한다.
4. 사용자가 요청한 두 번째 카메라(sensor-id1) 비교에 마지막1회를 사용했다. **최대3회를 모두 사용했고 추가 호출은 중지했다.**

이번 작업의 목표 상한은$0.10이다. 구현한 로컬 장부는 최대3회, 호출 전$0.02씩 예약하므로 최대 예약 합계는$0.06이다. 개별 요청은 이미지 최대2장·각 변640픽셀 이하·JPEG100KB 이하·텍스트/질문12KB 이하·질문6개 이하로 제한한다. 이 예약은 작은 요청에 대한 보수적인 실행 여유이며 계정의 서버 측 달러 제한이 아니다. 실제 토큰 수가 예약 허용량을 넘거나 네트워크 타임아웃·인증 실패·사용량 오류가 발생하면 자동 재시도를 하지 않는다. 429는 재시도 대기시간을 장부에 기록한다.

키·원본 사진·Base64 요청 본문은 장부에 기록하지 않는다. 장부는 `/var/lib/300seconds/openai-observer-budget.json`이며 root 권한으로 관리한다. 별도 프로세스의 동시 호출은 lock으로 직렬화한다. 장부를 지우거나 다른 프로그램으로 호출하면 이 도구의 제한에 포함되지 않는다. 기존 runtime 제공자 설정·서비스는 변경하지 않았다.

## 공식 API와 가격 확인

[공식 OpenAI Decisions 안내](https://developers.openai.com/api/docs/guides/decisions)와 [요청·응답 레퍼런스](https://developers.openai.com/api/reference/resources/decisions/methods/create)를 확인했다.

- 엔드포인트: `POST https://api.openai.com/v1/decisions`
- 모델: `gpt-6-luna`
- 평가: `predicate`, `choice`, `score` 중 이 도구는 predicate4개와 score2개를 함께 사용한다.
- 사진: `input_image`에 inline JPEG data URL, `detail=low`를 사용한다.
- 표준 uncached 입력 단가: **100만 토큰당$0.10**, 출력 토큰 요금 없음.

이번 짧은 일회성 비교에서는 `prompt_cache_options={"mode":"explicit"}`만 지정하고 breakpoint를 넣지 않아 캐시를 사용하지 않는다. 실제 응답의 cache-read·cache-write 토큰도 모두0이었다. 지역·긴 문맥·캐시 등의 조건이 달라지는 운영에서는 해당 가격을 다시 확인해야 한다. 최종 청구액은 OpenAI Billing을 따른다.

## 실제 결과

| 시험 | 시각 KST | 입력 토큰 | API 왕복 시간 | 표준 추정 비용 |
| --- | --- | ---: | ---: | ---: |
| 짧은 텍스트·램프 켜짐 predicate | 13:25:58 | 159 | 1,148.4ms | $0.0000159 |
| 카메라0 사진1장·관찰 질문6개 | 13:26:18 | 1,454 | 993.9ms | $0.0001454 |
| 카메라1(두 번째 카메라) 사진1장 | 13:30:53 | 1,454 | 414.5ms | $0.0001454 |
| **합계** | | **3,067** | | **$0.0003067** |

세 요청 모두 HTTP200, 반환 모델 `gpt-6-luna`, 출력 토큰0이었다. 램프 테스트의 true 확률은1.0이었다. 이 합계는 사용자가 언급한10달러의 약0.0031%이며, 계정에 정확히 얼마가 남았는지를 계산한 값은 아니다. 관리자 키가 필요한 조직 전체 Usage/Costs 조회를 위해 추가 자격 증명을 요구하지 않았다.

사진은640×360,20,761bytes였고 새 camera worker generation의 최신 JPEG를 가져왔다. 응답에서는 자리 관찰 가능성0.00, 재석 확률0.23, 학습 행동 관찰 가능성0.06, 시선 관찰 가능성0.03을 반환했다. 관찰 가능성 기준에 미달해 애플리케이션 결과는 다음과 같다.

```json
{
  "status": "unknown",
  "focus_score": null,
  "study_gaze_score": null,
  "is_away": null,
  "valid": {
    "focus_score": false,
    "study_gaze_score": false,
    "is_away": false
  },
  "reasons": ["seat_not_observable"]
}
```

**이는 API 실패가 아닌 관찰 불가 결과다.** API 자체는 score와 predicate를 모두 반환했다. 하지만 자리가 제대로 보이지 않는 상황에서 낮은 원시 점수를 집중도·시선 점수로 확정하거나, 얼굴이 없다는 이유로 자리비움=true로 바꾸지 않았다. 요청한 집중 점수는 보이는 학습 행동의 대리 지표이며 내적인 집중력 측정이 아니다. 시선도 정밀 눈동자 추적이 아닌 보이는 방향의 추정치다.

로컬에서 현재 화각을 추가 확인했다. 카메라0은 옆으로 돌아가 있고 전경에 키보드·책상·가방이 크게 보이며 여러 사람이 배경에 있다. 지정 학습자의 자리와 학습 영역을 관찰할 배치로 먼저 맞춰야 한다. 이 확인에는 추가 OpenAI 요청을 사용하지 않았다.

### 두 번째 카메라 재시험과 재석 규칙 수정

카메라1의 사진은640×360,19,150bytes였다. 모델은 사람 존재 확률1.00, 자리 전체의 관찰 가능성0.03, 학습 행동 관찰 가능성0.01, 시선 관찰 가능성0.00을 반환했다. 현재 화각을 별도로 확인하니 사람 얼굴·상체는 보이지만 책상·학습 자료는 보이지 않았다.

기존 변환 로직은 자리 전체가 보이지 않으면 명확한 사람 존재까지 무효화했다. 이를 수정해 **지정 영역의 사람 존재 확률이0.8 이상이면 `is_away=false`**로 반환한다. 반대로 **자리비움=true는 자리 영역이 분명히 보이고 사람 존재 확률이0.2 이하일 때만** 반환한다. 자리도 사람도 불확실하면null이다. 이 수정은 재석과 부재를 비대칭으로 판정하며, 배경 사람을 대상자로 식별하거나 신원을 추론하는 기능은 아니다. ROI·카메라 배치와 실제 정답 표본 검증은 여전히 필요하다.

이미 받은 응답을 새 규칙으로 재평가했으며 **추가 API 요청·과금은 없다.** 집중·시선의 관찰 가능성 검사와null 처리는 유지했다.

```json
{
  "status": "partial",
  "focus_score": null,
  "study_gaze_score": null,
  "is_away": false,
  "valid": {"focus_score": false, "study_gaze_score": false, "is_away": true},
  "reasons": ["study_behavior_uncertain", "gaze_uncertain"]
}
```

사진을 보고 내적 집중 상태를 추측하거나 낮은 원시 점수를 곧바로 낮은 집중도로 표시하지 않는다. 공부 시선 점수를 내려면 학습 영역의 위치와 눈·머리 방향을 함께 확인할 수 있어야 한다.

## 코드와 검증

[openai-study-observer.py](../../tools/jetson/openai-study-observer.py)를 Nano 저장소 및 root 소유 `/opt/300seconds/jetson/`에 설치했다. 카메라 수집·판단 불가 처리는 같은 폴더의 [Jev 관찰 도구](../../tools/jetson/jev-study-observer.py)를 가져와 재사용하며 JEV API를 호출하지 않는다.

PC·Nano Python3.8에서 [OpenAI 도구 테스트15개](../../tools/jetson/test_openai_study_observer.py)와 [공통 관찰 도구 테스트23개](../../tools/jetson/test_jev_study_observer.py), 합계38개가 통과했다. 최대3회 지속 제한, 비용 계산, 동시 실행, 손상된 장부,429·타임아웃 중단, 비밀 유출 방지, 부적절한 payload, predicate/score 변환, refusal 처리, 이미지1장 단발 요청 조합을 검사했다. 두 번째 카메라의 명확한 재석·관찰 불가 학습 행동을 구분하는 회귀 검사도 포함한다.

Score는5개 기준의0~4 결과를2.5배해0~10으로 바꾼다. predicate는 관찰 가능성과 함께 threshold를 적용해bool 또는null로 변환한다. 학습 행동·시선·자리비움의 정확도나 임계값을 실제 정답 영상 세트로 검증한 것은 아니다. 모델이 올바른 형태의 답을 반환한 것과 행동 인식 정확도를 구분한다.

증거:

- [키 존재·모델 조회](board-info/2026-10-24/openai-decisions-preflight.json)
- [텍스트 API 실제 응답](board-info/2026-10-24/openai-decisions-text-test.json)
- [사진 API 실제 응답·정규화 결과](board-info/2026-10-24/openai-decisions-camera0.json)
- [두 번째 카메라 응답·수정된 변환 결과](board-info/2026-10-24/openai-decisions-camera1.json), [수정 전 결과 보존본](board-info/2026-10-24/openai-decisions-camera1-original.json)
- [재석 규칙 회귀 검사](board-info/2026-10-24/openai-camera2-regression.json)
- [로컬 예산 장부](board-info/2026-10-24/openai-decisions-budget.json)
- [설치 해시·Nano 검사](board-info/2026-10-24/openai-decisions-install.json)

## 키와 다음 실행

기존 **`/etc/300seconds/ai.env`의 `OPENAI_API_KEY`**를 사용한다. 실제 키를 출력·복사하지 않고 파일 권한0600과 인증·추론 성공을 확인했다. OpenCode 키를 OpenAI로 보내지 않는다. 기존 `NANO_ALLOW_OPENAI_INFERENCE`·runtime 제공자 선택을 전역으로 켜지 않고 이번 명시적 단발 CLI에서만 사용했다.

카메라 설정은 `/etc/300seconds/jev-observer.env`의 대시보드 URL·자리ROI를 재사용한다. CLI의 `--cameras 0,1`이면0을 사람 카메라,1을 학습 영역 카메라로 취급한다. `--cameras 0`이면 같은1장을 두 역할의 증거로 쓰며 다른 화각의 증거는 만들지 않는다.

```bash
# 로컬 사용량 확인. API 요청 없음.
sudo python3 -B /opt/300seconds/jetson/openai-study-observer.py budget

# 사용 예시. 현재3회 소진 상태이므로 실행해도 로컬 예산에서 차단된다.
sudo python3 -B /opt/300seconds/jetson/openai-study-observer.py analyze --cameras 0,1 \
  --output /var/tmp/openai-study-result.json
```

첫 텍스트 테스트는 이미 성공했으므로 반복할 필요가 없다. 도구는 주기적으로 실행되지 않으며 대시보드나 로봇에 자동 제어를 추가하지 않았다. 새 운영 예산을 정하기 전 장부를 자동 초기화하지 않는다.

## 운영 빈도 비용 가정

이번 **사진1장·1,454토큰 요청과 매번 동일한 사용량**이라고 가정한 계산이다. 실제 영상·카메라 수·질문 길이에 따라 달라지며 아래 주기 실행을 시작하지 않았다.

| 분석 주기 | 8시간 요청 수 | 표준 추정 비용 |
| --- | ---: | ---: |
| 1분에1회 | 480 | 약$0.0698 |
| 10초에1회 | 2,880 | 약$0.4188 |
| 5초에1회 | 5,760 | 약$0.8375 |

먼저 시야를 맞춘 정답 표본으로 검증하고, 운영한다면 필요한 시점의 단발 분석이나 낮은 빈도부터 측정해 예산을 잡는다. 네트워크 장애 시 오래된 사진을 재전송하거나 자동 재시도하는 방식은 현재 도구에 없다.
