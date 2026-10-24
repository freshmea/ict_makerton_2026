# BA-R9 기본음·한국어 TTS 재시험

2026-10-24, Jetson `192.168.184.76`의 실제 장치로 시험했다. 최종 사용자는 **기본음과 TTS가 모두 잘 들림**을 확인했다.

BA-R9의 3.5mm 오디오 입력은 기존 C-Media USB 오디오 어댑터의 헤드폰 출력에 연결돼 있다. ALSA `robot_playback`은 `hw:CARD=Device,DEV=0`을 사용한다. [제조사 설명서](../../../../BOM/manuals/Britz_BA-R9_manual.jpg)에서 USB 전원, 별도 전원 버튼, 볼륨 다이얼을 확인했다.

첫 시험에서는 대시보드 `/api/audio/play`의 `tone` 요청과 `aplay`가 성공했지만 사용자는 기본음·TTS 모두 들리지 않는다고 답했다. 출력 음소거는 해제돼 있었고 다른 재생 프로세스의 점유도 없었다. USB 믹서 출력을 17/37(46%, -20 dB)에서 31/37(84%, -6 dB)로 조정했지만 이 단계만으로는 들리지 않았다.

사용자가 **볼륨 다이얼 위의 별도 전원 버튼을 켠 뒤** 같은 경로로 재시험하자 기본음·한국어 TTS가 모두 들렸다. 전원 조작 전의 PCM 성공과 최종 실제 청취 성공을 구분한다. 대시보드 소스나 서비스 재시작 없이 해결했다.

- 기본음: 실제 대시보드 API의 660 → 880 → 1100 Hz, 각 0.3초 재생. 기존 마이크의 메모리 버퍼에서도 세 주파수의 순차 출력을 검출했다.
- TTS: 기존 `nano-runtime typecast-sample`의 Typecast `ssfm-v30` / 서연. “문제에 주어진 조건을 먼저 하나 찾아볼까?”를 합성해 동일한 `robot_playback`으로 재생했다. 최종 WAV는 44.1 kHz / mono / S16 / 2.95초였으며 합성·재생 종료 코드는 모두 0이다.
- TTS 시험은 총 2회, 각 23문자다. 기존 계정 크레딧 확인과 문자·호출 제한을 그대로 사용했다. 생성 WAV는 `/run`에서 재생 후 삭제했고 마이크 녹음은 저장하지 않았다.
- 최종 USB 출력은 84%(-6 dB), 음소거 해제다. `alsactl store`로 저장했다. 대시보드는 계속 active다.

원본 결과: [첫 기본음](tone-result.json), [첫 TTS](tts-result.json), [전원 켠 뒤 재시험 및 사용자 확인](retest-result.json), [최종 출력 설정](final-settings.json). 최초 믹서 상태는 Nano의 `/var/tmp/300seconds-ba-r9-20261024/alsa-before.state`에 백업했다.

TTS 출처: Typecast AI 합성 음성, 사용 캐릭터: 서연, <https://typecast.ai>.
