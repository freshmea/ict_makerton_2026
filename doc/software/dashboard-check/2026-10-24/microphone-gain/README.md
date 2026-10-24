# 마이크 녹음 증폭 적용·검증

2026-10-24 KST, 사용자 승인 후 `192.168.184.76` Nano에 적용했다. 기본 +12 dB, 조절 0~30 dB, 녹음 구간 전체 선형 증폭과 -1 dBFS 피크 보호다. 상단 MICROPHONE은 최근 3초 출력 피크이며 원본·출력 평균은 오디오 패널에 별도 표시한다. WAV와 스피커 녹음 재생이 같은 처리 함수를 사용한다.

- Nano 전용 venv에서 `test_audio test_hardware test_eye_expressions test_observer_api` **32개 통과**. 이 중 오디오 테스트는 10개이며 실제 PCM 증폭, 선형 파형 보존, int16 극값, 무음, 설정 저장·재로딩, 잘못된 값, WAV·재생 경로를 검사한다. 장치를 열거나 실제 스피커 시험음을 재생하는 테스트는 아니다.
- 실제 HTTP 3초 WAV: 48 kHz / 16 bit / mono / 144,000 samples. 검증 구간 RMS 약 -20.49 dBFS, 피크 약 -3.16 dBFS, full-scale samples 0. 오디오는 저장하지 않고 수치만 기록했다. [WAV 수치](live-wav.json)
- 브라우저에서 +30 dB 적용 시 실제 +20.8 dB로 제한되고 피크 -1.0 dBFS와 `피크 보호 중`을 확인했다. 키보드로 +12 dB로 복원했다. 음성·배경 소음은 계속 변하므로 시점별 값은 다르다. 직접 청취에 의한 음질 평가는 포함하지 않는다. [브라우저 검증](browser-qa.json)
- 모바일 390 px에서 문서 너비도 390 px, 가로 넘침 없음. 데스크톱·모바일 화면을 직접 확인했고 Chrome console 오류·경고 모두 0이다. [데스크톱](audio-desktop.png) · [모바일](audio-mobile.png)
- CSRF 없음·외부 Origin은 403, 음수·상한 초과·NaN·허용하지 않은 필드는 422. 최종 health는 API·Pico·카메라·마이크 모두 정상이며 증폭값은 +12 dB다. 기존 서보 I2C fault는 이 오디오 작업의 검증 대상이 아니다. [HTTP 검증](http-qa.json)
- 실행본과 Nano 저장소 파일의 SHA-256 일치를 확인했다. 배포 전 백업: `/opt/300seconds/dashboard/backups/microphone-gain-20261024T053522Z`. 시작 직후의 카메라 준비 상태와 이후 최종 health는 구분한다. [배포 기록](deployment.json)

운영 규칙과 API 필드는 [대시보드 README](../../../../../apps/device-dashboard/README.md)의 마이크 절을 따른다.
