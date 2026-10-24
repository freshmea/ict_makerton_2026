# 버튼 번호 MP3·count 비프음 배포 검증

2026-10-25 KST. Jetson Nano `192.168.184.76`. 시간 이름의 `20261024T...Z`는 UTC다.

## 결과

- Nano Python 3.8에서 대시보드·오디오·학습·TTS·장치 회귀 **94개 통과**: [nano-tests.log](nano-tests.log).
- 로컬 Rust `pico-device-protocol` **13개 통과**. 추가한 `button_audio_contract.rs`는 6개 입력 각각에서 30ms 디바운스, 1회 Pressed, 0.5초 간격 count 1~12, 해제 후 interval 중지를 확인한다.
- Typecast 기존 서비스를 통해 “1번”~“6번”을 각각 합성해 MP3 6개와 디코딩한 WAV 캐시를 저장했다. 최초 요청은 provider 응답 시간 초과였고 재시도에서 6개를 완료했다. [합성 로그](synthesize-six-mp3.log).
- `ffprobe`로 6개 모두 MP3 / 48kHz / mono임을 확인했다.
- 실제 USB ALSA 출력에 생산 코드 `ButtonAudio`를 연결하고 자동 시험용 펌웨어 형태 이벤트를 전달했다. 번호 **6/6**, 비프음 **18/18**, 폐기·거절 **0**, 오류 없음.
- 24kHz mono primary `aplay`가 열린 상태에서 48kHz 버튼 비프음을 별도 `aplay`로 겹쳐 출력했다. 두 출력 모두 성공했고 기존 주 재생 잠금은 유지됐다.
- 배포된 `/api/status`에서 `button_audio.running=true`, `ready=true`, 캐시 `[1,2,3,4,5,6]`, Pico·마이크 연결을 확인했다. 연속 카메라 수집은 `enabled=true`로 복원됐다. [검증 JSON](verification.json), [전체 출력 로그](speaker-verification.log).

## 배포 범위

- `app.py`, `hardware.py`, `learning.py`, `button_audio.py`, `build_button_audio.py`, `test_button_audio.py`
- `/etc/alsa/conf.d/99-300seconds-usb.conf`의 재생 경로를 같은 사용자 `dmix`로 연결. 캡처·기본 PCM은 변경하지 않았다.
- 음원 영구 위치: `/var/lib/300seconds-dashboard/button-audio/` (manifest 포함 13개 파일)
- 앱 배포 및 저장소 묶음: `apps/device-dashboard/assets/button-audio/`
- 백업: `/var/lib/300seconds-dashboard/backups/button-audio-20261024T153816Z`
- 임시 검증: `/tmp/button-audio-20261024T153816Z/dashboard`

기존 소스·ALSA 설정과 SQLite를 백업했다. 실행 중인 Live가 있으면 배포를 중단하도록 검사했고, 카메라 수집을 잠시 멈추고 진행 중인 분석이 끝난 다음 대시보드만 재시작했다. TTS·observer 서비스는 재시작하지 않았다. Nano 저장소에도 적용 소스와 음원을 복사했다.

## 검증 한계

자동 스피커 시험은 실제 ALSA 장치를 사용했지만 GPIO 버튼을 물리적으로 누르지는 않았다. 시험용 이벤트 발생기는 별도 프로세스에서 생산 `ButtonAudio`를 실행하며 실제 SW1의 GPT Live 시작을 유발하지 않았다. 실제 Pico USB 수신 → 콜백의 24개 연속 이벤트 전달은 장치 없는 회귀 검사에 포함된다. 사용자는 각 버튼을 직접 눌러 번호 발음과 볼륨을 최종 청감 확인할 수 있다.

유료 GPT Live 세션은 새로 열지 않았다. Live 마이크 차단과 출력 25% 감쇠는 회귀 검사로 검증했고, 두 출력의 ALSA 공존은 위 실제 동시 재생 시험으로 확인했다. 재부팅은 하지 않았으며 기존 enabled systemd 서비스의 시작 경로에 기능을 연결했다. Pico 펌웨어는 기존 이벤트 구현을 그대로 사용하므로 이번 작업에서 플래시하지 않았다.

설계·운영: [버튼 음성 피드백](../../../버튼_음성_피드백.md).
