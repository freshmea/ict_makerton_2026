# Pico USB 연결 시 전원 꺼짐 재조사

2026-10-29 한국 시간. 사용자 설명: Pico USB 연결 시 Jetson이 부팅 중 꺼지며, NeoPixel을 20개 넘게 연결한 뒤 발생한 것으로 보임. NeoPixel 전원은 Pico 3V3에 연결되어 있다고 확인했다. '5핀 전원'은 커넥터 설명으로 보이나 정확한 어댑터 정격과 공급 대상은 확인하지 못했다.

## 실측과 로그

- 처음에는 192.168.219.127:22가 반복 시간 초과였다. 사용자가 전원을 다시 연결한 뒤 SSH 접속이 복구됐다.
- 현재 boot ID: 813fb293-4d20-40ec-aecb-d18b8484c5ed. 조사 중 USB 목록에는 Pico가 없다.
- 이번 부팅에는 Oops/kernel panic/OC ALARM을 발견하지 못했다. ext4 orphan inode 정리와 recovery complete는 비정상 종료 후 복구와 일치하지만, 사용자의 수동 전원 차단으로도 생길 수 있다.
- root 권한으로도 이전 부팅의 kernel journal은 No entries였다. 남은 이전 journal에는 사용자 세션 시작 일부만 있다. 종료 순간의 전압 또는 과전류 차단 기록은 확보하지 못했다.
- pstore의 panic 파일은 여전히 10월 25일 보존분이다. 지난번 SquashFS panic을 이번 Pico 연결 장애의 원인으로 재사용하지 않는다.
- kern.log의 최근 OC ALARM 검색 결과는 10월 25일 기록이다. 이번 꺼짐의 과전류 확정 증거가 아니다.
- Pico가 인식되지 않는 현재 상태에서 POM_5V_IN 1초 간격 5회: 4896, 4952, 4952, 4912, 4968 mV. 입력 전류는 576, 464, 464, 576, 464 mA. 부팅 순간이나 LED 연결 부하의 값이 아니다.
- 장치의 부팅 초기 시각은 RTC/NTP 보정 때문에 불일치한다. last의 음수 경과 일수나 로그 벽시계로 장애 시각을 단정하지 않는다.

## 판단

후속 사용자 실물 확인: NeoPixel을 제거하고 진행하자 정상 부팅됐다. 이는 LED 부하 또는 연결 배선과 장애의 연관성을 강하게 뒷받침한다. LED 수량만의 문제인지, 3V3 레귤레이터 과부하인지, 단락/배선/USB 입력 전압강하인지는 분리 측정하지 않았으므로 확정하지 않는다.

NeoPixel 전원을 Pico의 3V3 출력에서 받는 구성은 우선 수정할 전원 설계 문제다. Pico 2 공식 데이터시트는 3V3 외부 부하를 300mA 미만으로 권고하며, 실제 여유는 RP2350 소비와 VSYS 전압에 의존한다. LED 부하·돌입전류·단락·케이블 전압강하가 USB 및 Jetson 입력 전원에 영향을 주었을 가능성이 높지만, 레귤레이터 과부하만으로 Jetson 전체가 반드시 꺼지는 것은 아니다. 이번 로그만으로 차단 부품이나 고장 여부를 확정하지 못했다.

Adafruit의 일반 RGB NeoPixel 전원 설계용 최악 조건은 최대 밝기 흰색에서 60mA/개다. 20개면 1.2A이나, 이는 사용자 LED의 모델·3.3V 조건·현재 밝기에 대한 실측값이 아니다. 저장소 펌웨어는 부팅 때 두 출력에 검정 프레임을 보내고, SW3 패턴 채널은 32/255로 제한한다. 일반 SetLight 밝기 상한은 64/255다. 따라서 '20개 초과=항상 1.2A=과부하 확정'이라고 설명하면 안 된다. 현재 Pico가 연결되지 않아 장착 펌웨어를 이번 조사에서 읽어 검증하지는 못했다.

## 권장 분리 확인과 배선

전원을 끈 상태에서 NeoPixel의 전원/GND/DIN을 Pico에서 모두 분리한 뒤 Pico 단독 USB 연결로 부팅 여부를 비교한다. 3V3 전원선만 빼고 DIN을 계속 구동하는 시험은 피한다. Pico 단독에서도 꺼지면 USB 케이블, Pico/다른 주변장치의 단락, Jetson 전원 경로까지 조사해야 한다.

5V 정격 NeoPixel이면 충분한 용량의 안정된 별도 5V 전원에서 LED에 직접 공급하고 Pico와 GND를 공유한다. 3.3V GPIO 데이터는 적절한 5V 레벨 시프터를 거쳐 DIN으로 보낸다. 외부 5V를 Pico 3V3에 넣거나 Jetson USB의 VBUS와 무조건 병렬 연결하지 않는다. Pico VBUS로 LED 전원선만 옮기면 부하가 여전히 Jetson USB에 남으므로 전원 분리가 아니다.

원격에서는 로그와 센서만 읽었다. 점등·서보·부하·재부팅 시험이나 펌웨어 변경은 수행하지 않았다.

## 자료

- [Raspberry Pi Pico 2 데이터시트, 3V3 설명](https://datasheets.raspberrypi.com/pico/pico-2-datasheet.pdf), PDF 10쪽.
- [Adafruit NeoPixel 전원 안내](https://learn.adafruit.com/adafruit-neopixel-uberguide/powering-neopixels).
- 같은 폴더의 root-previous-kernel.txt, root-previous-tail.txt, root-boots.txt, power-evidence.txt, current-kernel.txt.
