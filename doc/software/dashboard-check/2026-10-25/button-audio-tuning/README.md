# 버튼 카운트 0.8초·한자어 번호 음성 교체

2026-10-25 KST. 사용자 요청에 따라 카운트 간격을 500ms에서 **800ms**로 바꾸고 MP3 6개를 새로 합성했다.

- TTS 문구: **일번·이번·삼번·사번·오번·육번**. 숫자 `1번` 등의 입력이 고유어 “한번·두번”으로 해석되는 일을 피하도록 한글을 그대로 제공한다.
- 수정 소스: `apps/device-dashboard/pico-config.json`, `build_button_audio.py`, `assets/button-audio/` 및 현재 운영 문서.
- 합성 캐시 문구가 요청 문구와 다르면 기존 음원을 재사용하지 않고 중단하도록 검사한다. 교체 음원은 새 출력 폴더에서 생성했다.
- Pico의 기존 펌웨어에 800ms 설정을 전달했다. `GET /api/status`의 실제 장치 설정에서 `hold_interval_ms=800`을 확인했다. 펌웨어 플래시는 하지 않았다.
- 6개 입력 각각에서 800ms 이전에는 count가 증가하지 않고, 이후 count 1~12와 해제가 올바른지 Rust 계약 검사가 통과했다.
- Nano 오디오 관련 검사 **14개 통과**: [nano-tests.log](nano-tests.log).
- 새 MP3 6개 및 해당 MP3에서 디코딩한 PCM의 체크섬·코덱을 확인하고 실제 ALSA 출력으로 재생했다. [검증 JSON](verification.json).
- 연속 카메라 수집은 기존 `enabled=true`로 복원했다.

기존 설정·소스·음원과 SQLite 백업: `/var/lib/300seconds-dashboard/backups/button-audio-tuning-20261024T170236Z`. UTC 이름이며 한국 시간으로 10월 25일이다. [배포 기록](deployment.json), [합성 기록](synthesize.log).

물리 버튼을 원격으로 누르거나 사람의 청감으로 음성을 판정한 시험은 아니다. 설정값과 펌웨어 엔진의 시간 조건, 정확한 합성 입력, 파일의 실제 ALSA 출력 성공을 확인했다.
