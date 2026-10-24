# OpenCode Jev 카메라 관찰 설정과 테스트

후속으로 [책상 기준 10프레임·15개 행동 분석과 대시보드 버튼](10프레임_학습행동_분석과_대시보드.md)을 추가했다. JEV 무료 한도 제한은 유지하며 실제 JEV 사진 응답은 여전히 미검증이다. 아래는 초기 CLI 설정·시험 기록이다.

2026-10-24 KST. 사용자 요청에 따라 카메라 사진으로 관찰 가능한 학습 행동·학습 영역 방향을0~10으로 평가하고, 자리비움 여부를 반환하는 **단발 CLI**를 구현했다. 키 입력 후 실제 OpenCode API를 시험했으나 무료 사용량 한도가 소진돼 **실제 사진 추론 응답은 아직 받지 못했다.** PC·Nano의 계약 테스트와 실제 카메라 수집 시험은 별도로 완료했다.

후속으로 사용자가 OpenAI API 결제 후 Decisions 테스트를 요청해 **OpenAI의 텍스트·실제 사진 호출에 성공**했다. [OpenAI 테스트·예산 기록](OpenAI_Decisions_카메라_테스트와_예산.md)을 참고한다. 이 결과는 OpenCode/Jev의 무료 한도 회복이나 이미지 처리 성공을 의미하지 않는다.

사용자는 **무료 한도 안의 테스트만** 요청했다. 도구는 `jev-1.13-free`만 허용하고 유료 모델 ID를 거부한다. 자동 유료 전환·백그라운드 업로드·정기 실행·하드웨어 제어는 없다.

## 키 위치와 형식

Nano의 `/etc/300seconds/jev-observer.env`를 사용한다. 이 파일을 root 소유0600으로 생성했고 사용자가 키 입력 완료를 알렸다. 실제 수집 점검에서 `credential_present=true`를 확인했으며 키값을 출력하거나 PC에 복사하지 않았다. 이 사실은 인증 성공과는 구분한다.

```bash
sudo nano /etc/300seconds/jev-observer.env
```

내용은 한 줄에 한 항목이며, 등호 뒤에 OpenCode Console/Zen에서 발급받은 키를 넣는다. `Bearer ` 접두사는 파일에 넣지 않는다.

```dotenv
OPENCODE_API_KEY=여기에_발급받은_OpenCode_키
JEV_MODEL=jev-1.13-free
JEV_DASHBOARD_URL=http://192.168.184.76:8000
JEV_PERSON_CAMERA=0
JEV_DESK_CAMERA=1
JEV_SEAT_ROI=0,0,1,1
JEV_SAMPLES=3
JEV_SAMPLE_INTERVAL=1
```

저장 후 권한을 유지한다.

```bash
sudo chown root:root /etc/300seconds/jev-observer.env
sudo chmod 600 /etc/300seconds/jev-observer.env
```

설정은 실행할 때 읽으므로 **서비스 재시작은 필요 없다.** DHCP 주소가 바뀌면 `JEV_DASHBOARD_URL`을 실제 대시보드 주소로 수정한다. 환경변수로 같은 항목을 지정하면 파일 값보다 우선한다. 파일은 셸로 실행하지 않고 데이터로 읽는다.

빈 예시: [jev-observer.env.example](../../software/config/jev-observer.env.example). 저장소 안의 `software/config/jev-observer.env`도 Git 제외 대상으로 추가했으며 실제 운영 키는 Nano의 `/etc` 파일에 둔다.

**OpenCode 키와 TypeSafe 직접 발급 키는 서로 다른 자격 증명이다.** 기존 Rust `dialogued`의 `TYPESAFE_API_KEY`·TypeSafe 직접 호출 설정과 이번 도구는 독립적이다. 기존 AI·TTS 키와 서비스 설정은 수정하지 않았다.

## 공식 API 계약과 구현

2026-10-24 확인한 [OpenCode 모델·Jev 문서](https://opencode.ai/v2/docs/console/models/#jev)의 공식 경로를 사용한다.

```text
POST https://opencode.ai/inference/systemone/v1/systemone
Authorization: Bearer <OPENCODE_API_KEY>
Content-Type: application/json
TypeSafe-Danger-Zone-Images: true
User-Agent: 300seconds-jev-observer/0.1
```

과거 Zen 경로를 추측해 사용하지 않고 현재 문서의 경로를 고정했다. 모델 목록 API에서도 `jev-1.13-free`를 확인했다. 키는 정해진 HTTPS API로만 보낼 수 있고 리다이렉트를 따르지 않는다.

요청은 `model`, `state`, `assets`, `questions`로 구성한다. `state.frames_oldest_first`에 시각과 카메라 역할·이미지 참조를 넣고, `assets`에JPEG의 `format=jpg`, `data_base64`를 넣는다. 개별 이미지는 `state`에서 한 번 참조한다. 키와 실제 Base64 요청 본문은 저장하지 않는다.

[TypeSafe 이미지 문서](https://docs.typesafe.ai/images)에 따라 정지JPEG를 사용하고 이미지 opt-in 헤더를 보낸다. Jev1.13 자체의 이미지 지원은 실험 기능이며, **OpenCode 게이트웨이가 이 헤더·이미지 요청을 정상 전달하는지는 실제 사진 요청으로 아직 검증하지 못했다.** 무료 한도 오류를 이미지 지원 실패로 해석하지 않는다.

대시보드가 이미 소유한 카메라의 `/api/cameras/{id}/snapshot.jpg`를 읽는다. 센서를 새로 열지 않는다. 각 카메라에서3장씩, 표본 사이 약1초를 두고 수집해 하나의 요청으로 보낸다. 상태 조회·네트워크 시간 때문에 실제 수집 간격은1초보다 길 수 있고 카메라 두 대는 하드웨어 동기화되지 않는다. 기본640×360 JPEG는 Jev의 최소 변 길이280픽셀 조건을 만족한다.

`preflight`는 수집만 하고 `analyze`만 사진을 업로드한다. 카메라 worker run ID·ready·JPEG 최신성을 전후로 확인하고, 수집 중 재시작·오래된 프레임이면 중단한다. 요청당 최대6장으로 제한한다.

## 반환 값과 판단 불가

다음 JSON은 **반환 형태를 보여 주는 예시**이며 실제 카메라에서 받은 추론 결과가 아니다.

```json
{
  "status": "ok",
  "focus_score": 8.0,
  "study_gaze_score": 7.5,
  "is_away": false,
  "valid": {
    "focus_score": true,
    "study_gaze_score": true,
    "is_away": true
  }
}
```

| 필드 | 의미 |
| --- | --- |
| `focus_score` | 눈에 보이는 읽기·쓰기·학습 자료 조작 행동의 정도,0~10. 내적 집중력 측정이 아님 |
| `study_gaze_score` | 확인 가능한 눈·머리 방향이 학습 영역을 향하는 정도,0~10. 정밀 시선 추적 장비의 보정값이 아님 |
| `is_away` | 최신 사진의 지정 자리 비어 있음=true, 사람이 차지함=false. 특정인의 신원이나 지속적인 부재를 판정하지 않음 |
| `valid` | 각 값이 이번 관찰에서 반환 가능한지 표시 |
| `probabilities` | 자리·사람·행동·시선 관찰 가능성에 관한 모델 출력 |
| `score_confidence` | 모델의 점수 분포에 따른 확신도. 검증된 정답률이 아님 |

Score 질문은5개 행동 기준을 사용한다. [공식 Score 계약](https://docs.typesafe.ai/primitives/score)에서5개 기준의 결과 범위는0~4이므로, 코드에서 **2.5를 곱해0~10으로 변환**한다. 11개 기준을 보내는 방식은 API의 최대10개 기준 제한과 맞지 않는다.

사람 존재 확률이0.8 이상이면 `is_away=false`로 반환한다. 자리 관찰 가능성이0.8 이상이면서 사람 존재 확률이0.2 이하일 때만 `is_away=true`이며 나머지는 `null`이다. 후속 OpenAI 두 번째 카메라 시험에서, 얼굴이 분명한 근접 화면을 자리 전체가 안 보인다는 이유로 무효화하던 공통 로직을 수정했다. 가림·화각 불명·천장/벽 사진은 자리비움으로 강제 변환하지 않는다. 자리에 사람이 없거나 관찰 가능성/점수 확신도가 낮으면 관련 점수도 `null`이다. 이때 `valid=false`와 `reasons`를 확인한다. 0점은 실제 관찰된 낮은 학습 행동에만 사용한다.

이 임계값은 초기 구현값이며 현재 사용자·카메라 배치에 대해 정확도를 검증한 값이 아니다. 실사용 전 재석·자리비움·자료 보기·다른 곳 보기·가림의 정답 표본으로 검증한다.

## 카메라 배치 점검

현재 스냅샷을 직접 확인했을 때 카메라0은 옆으로 돌아간 화면에 책상·키보드 비중이 크고, 카메라1은 전선·근접 물체가 흐리게 보였다. 학습자 눈·머리와 학습 자료 방향을 신뢰성 있게 평가할 준비가 됐다고 볼 수 없다.

카메라0이 지정 자리의 사람·머리 방향을, 카메라1이 책/노트/화면 등 실제 학습 영역을 보도록 장착한다. `JEV_PERSON_CAMERA`·`JEV_DESK_CAMERA`는 실제 장착에 맞춰 바꾼다. `JEV_SEAT_ROI=x,y,width,height`는 카메라0의 정규화 좌표이며 기본값은 전체 화면이다. 옆자리 사람을 재석으로 판단하지 않도록 대상 자리로 좁히고, 회전된 화면은 장착 방향부터 조정한다. ROI는 모델에 전달하는 영역 설명이며 로컬 이미지 잘라내기는 하지 않는다.

로컬 화각 검토용 이미지는 Git 제외된 `tmp/jev-observer/`에만 두었으며 결과 증거 폴더에는 올리지 않았다.

## Nano에서 실행

도구: `/opt/300seconds/jetson/jev-study-observer.py`. Nano 저장소에도 소스·테스트·빈 설정 예시를 복사했다.

```bash
# 실제 카메라 수집만 확인. 외부 업로드 없음.
sudo python3 -B /opt/300seconds/jetson/jev-study-observer.py preflight

# 무료 한도가 회복된 뒤 키·텍스트 응답 확인. API 요청1회.
sudo python3 -B /opt/300seconds/jetson/jev-study-observer.py auth-test

# 화각을 맞춘 뒤 실제 사진 분석. API 요청1회.
sudo python3 -B /opt/300seconds/jetson/jev-study-observer.py analyze \
  --output /var/tmp/jev-study-result.json
```

각 실행은 한 번으로 종료한다. 인증과 분석을 함께 자동 호출하지 않는다. `--output`은 분석 결과와 이미지 크기·해시·시각 등 메타데이터만 기록하며 사진·키·원시 요청 본문은 기록하지 않는다. 현재 대시보드에 점수를 자동 표시하거나 로봇 동작을 유발하는 연동은 추가하지 않았다.

## 실제 테스트 결과

| 시험 | 결과 |
| --- | --- |
| PC 계약·오류 처리 검사 | 21개 통과.0~10 변환, bool/null 구분, 가림·자리비움, 낮은 확신도, 잘못된 응답, 키·이미지 유출 방지, 유료 모델 차단 포함 |
| Nano Python3.8 검사 | 최종21개 통과. 설치 증거 참조 |
| 실제 카메라 수집 | 두 대×3장, 총6장, 각각640×360, 총89,496bytes, 동일 worker generation, 키 존재 확인. 외부 업로드 없음 |
| 기본 Python 클라이언트 요청 | HTTP403 / Cloudflare1010. 고유 클라이언트 User-Agent 명시 후 다음 오류를 수신 |
| 무료 Jev 텍스트 요청 | HTTP429, `FreeUsageLimitError`, `Retry-After: 71109`초 |
| 실제 사진의 Jev 평가 | **미실행**. 무료 한도 소진으로 인증 단계에서 중단 |
| 일반 유료 모델 | **호출0회**. 자동 승인 검토가 과금 동의 없이 전환하는 요청을 차단했고 사용자가 무료 테스트만 선택 |

무료 한도 응답은13:14:51 KST 무렵의 기록이다. 당시 `Retry-After`를 더하면 **2026-10-25 약09:00 KST**다. 이는 해당 응답이 안내한 재시도 시각이며 무료 모델의 장기 제공·향후 성공을 보장하지 않는다. 반복 재시도나 다른 IP·자격 증명을 사용한 한도 회피는 하지 않았다. 키가 틀렸다고 결론 내리지 않으며, 정상 인증·사진 처리 성공도 아직 주장하지 않는다.

증거:

- [무료 한도 실제 응답](board-info/2026-10-24/jev-rate-diagnosis.json)
- [실제 카메라 수집 결과](board-info/2026-10-24/jev-camera-preflight.json)
- [Nano 설치·테스트 기록](board-info/2026-10-24/jev-install-verification.json)
- [클라이언트·초기 HTTP 오류](board-info/2026-10-24/jev-auth-test-client.json), [403 진단](board-info/2026-10-24/jev-auth-diagnosis.json)

소스: [jev-study-observer.py](../../tools/jetson/jev-study-observer.py), [검사 코드](../../tools/jetson/test_jev_study_observer.py). 공식 참고: [OpenCode Jev](https://opencode.ai/v2/docs/console/models/#jev), [TypeSafe 이미지](https://docs.typesafe.ai/images), [Score](https://docs.typesafe.ai/primitives/score), [Noul](https://docs.typesafe.ai/primitives/noul), [Cloudflare1010](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/cloudflare-1xxx-errors/error-1010/).
