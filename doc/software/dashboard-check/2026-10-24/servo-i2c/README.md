# 재부팅 후 PCA9685 연결 오류 진단

사용자는 업데이트 후 전체 재부팅과 배선 재확인을 했지만 서보 연결 오류가 남는다고 보고했다. A0 패드 두 점은 납으로 연결되어 있다고 확인했다. 기존 초기 실기 기록에서도 0x41 응답이 있었으므로 A0 미설정으로 단정하지 않았다.

## 진단 이미지 업로드 직후 결과

| 항목 | 결과 |
| --- | --- |
| Pico USB | 연결 정상, 새 개별 제어 capability 확인 |
| 장치 시험 | 최종 `running=null`; 시험이 지속 실행 중인 상태는 아님 |
| 0x40 MODE 레지스터 읽기 | ACK 없음 |
| 0x41 MODE 레지스터 읽기 | ACK 없음 |
| SDA / SCL | 둘 다 디지털 HIGH |
| 초기화 | 실패, 주소 미선택, fault bit 1 유지 |
| 서보 출력 | 미Arm, pose 비활성, OE HIGH, 모터 구동 요청 없음 |
| 대시보드·TTS / 카메라·마이크 | 서비스 활성 및 장치 정상 상태 복구 |

[이전 상태](status-before.json), [출력 차단 상태의 실제 probe 및 상세 상태](live-diagnostics.json), [최종 장치 상태](final-health.json).

이번 관측은 기대 주소의 **ACK 부재**이며 40ms 타임아웃이나 SDA/SCL LOW 고정은 아니다. HIGH는 Pico 핀의 디지털 읽기 결과이고 PCA 보드의 전원 전압·선의 연속성을 입증하지 않는다. 0x42 이상 및 ALLCALL 주소를 스캔한 결과도 아니다. A0 납땜 보고만으로 접촉·다른 주소 패드·로직 전원·보드 정상 여부를 확정할 수 없다. VCC/GND 전원 도달, 신호선 접촉/연속성, 실제 주소 및 PCA 보드 자체 문제는 추가 구분이 필요하다.

당시 다음 요청은 Pico USB 연결·서보 6V OFF 상태에서 PCA 보드 쪽 VCC–GND 전압 직접 측정이었다. 이후 사용자가 **약 3.3V**라고 답했다. 일반적인 주소 설정은 [Adafruit 주소 설명](https://learn.adafruit.com/16-channel-pwm-servo-driver/chaining-drivers), 칩 전원·레지스터 정의는 [NXP 데이터시트](https://www.nxp.com/docs/en/data-sheet/PCA9685.pdf)를 참고했다.

## VCC 측정 후 복구 관측

재조회에서 PCA 0x41 응답과 오류 0이 확인됐다. 출력 차단 상태의 초기화 요청이 HTTP 200으로 성공했고 30초 동안 같은 USB 세션·오류 0·미Arm·OE HIGH를 유지했다. 관찰 종료 후 새 I2C 읽기·초기화 요청도 다시 성공했다. 사용자는 측정만 했고 USB/전원이나 배선은 바꾸지 않았다고 보고했다. [VCC 확인 시점](vcc-confirmed-status.json), [복구 확인·반복 초기화](vcc-recovery.json).

기록상 이전과 다른 Pico 세션 및 Nano의 짧은 uptime도 관찰했지만, 재시작의 원인은 확정하지 못했다. Nano의 INA3221 센서 입력은 4.496~4.560V였고 5W 모드에서도 OC 경고가 이어졌다. PCA 최초 무응답과의 직접 인과관계는 미확정이며, 통신 복구를 전원 안정성 해결로 판정하지 않는다. [시스템 기록](recovery-system-log.txt), [전원·커널 기록](recovery-power-log.txt), [전압 표본](recovery-power-samples.json). 센서 단위는 [NVIDIA 전력 관리 문서](https://docs.nvidia.com/jetson/archives/l4t-archived/l4t-3276/Tegra%20Linux%20Driver%20Package%20Development%20Guide/power_management_nano.html), 공급 전압 기준은 [NVIDIA 전원 안내](https://forums.developer.nvidia.com/t/power-supply-considerations-for-jetson-nano-developer-kit/71637)를 참고했다.

## 변경과 업로드

기존 펌웨어는 0x41 쓰기의 모든 실패를 같은 fault bit로 합쳤다. 새 진단 확장은 OE HIGH·출력 차단 상태에서 0x40/0x41의 MODE1과 MODE2를 각각 읽고, 주소별 정상 응답·ACK 없음·시간 초과·기타 오류·예약 비트 불일치를 전달한다. 정확히 한 주소만 유효할 때만 그 주소를 선택한다. 두 주소가 모두 응답하면 임의 선택하지 않는다. 부팅·진단·제어 시작은 PWM을 실행하지 않는다. 오류를 무시해서 Arm하는 경로는 추가하지 않았다.

`ServoDriverStatus`는 기존 wire v2 enum 끝의 새 메시지다. 기존 메시지 태그와 Servo 명령은 유지한다. Nano 브리지는 상태를 `servo_driver`로 전달하고 대시보드가 실제 결과에 맞는 문구를 표시한다. `last_error=0`은 마지막 쓰기 오류가 없다는 뜻이며, 미선택 상태에서는 쓰기를 아예 하지 않으므로 이것만으로 정상 판정하지 않는다. `probes`와 `initialized`를 함께 본다.

사용자가 서보 전원 OFF·BOOTSEL 재연결을 확인한 뒤 같은 serial `E679675A69C4039B`를 확인하고 기존 4MiB flash를 먼저 백업했다. 새 이미지 쓰기·읽기 검증과 CDC STATUS 복귀를 완료했다. [업로드 결과](flash-result.json), [배포 로그](deploy.log), [설치 코드/바이너리 해시 일치와 서비스 활성 확인](deployment-verification.json).

- UF2 SHA-256: `11729a7049684e93818a391cae592f06308fcd9df96dab7e1e5574987352b141`
- Nano 브리지 SHA-256: `006d007f6c3624370a5a29481d4feebc6ccd0c0f6ccb4056ca723c49bf3890bc`
- 이전 flash: `/home/jetson/ict_makerton_2026/tmp/pico-flash/20261024T103948.635103Z-linux/previous-flash.bin`
- 이전 flash SHA-256: `71fc7b3a4576ea5d99a81ffdb9dcb43f11726913853a7ef007de36bd235e78cc`
- 이전 설치 파일 백업: `/var/tmp/servo-i2c-before-20261024`

Rust 검사 40개와 Python 회귀 54개가 통과했다. 펌웨어 RP2350 cross build와 Nano native release build를 완료했다. [검사 로그](build-tests.log), [빌드·소스 정보](build-info.json). 자동화 검증은 모터를 회전시키거나 전압계를 읽지 않았으며 VCC 약 3.3V는 사용자의 실측 보고다.
