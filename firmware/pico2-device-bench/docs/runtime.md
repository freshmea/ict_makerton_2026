# RP2350 실행부와 내부 API

이 HTML은 `main.rs` 바이너리를 RP2350 대상으로 문서화한 결과다. 비공개 항목을 포함하므로 태스크, 장치 소유자, 큐와 `application::Application`의 내부 상태를 탐색할 수 있다. 라이브러리 HTML의 전체 해설과 사용 사례를 먼저 읽고 이 페이지로 오면 각 설명을 실제 함수에 연결할 수 있다.

## 실행 순서

```text
main
  -> OE HIGH
  -> I2C / PIO / DMA / SPI 구성
  -> Devices::stop_all
  -> touch_task 실행
  -> USB CDC와 BOOTSEL interface 구성
  -> usb_task / rx_task / tx_task / safety_task 실행
  -> device_task가 Devices를 소유
```

Embassy와 cortex-m 매크로가 진입 함수를 확장하므로 함수 목록에 `__embassy_main`, `__cortex_m_rt_main` 같은 이름도 보인다. 학습할 원본은 `src/main.rs`의 `async fn main`이다. 각 항목의 Source 링크로 실제 소스를 확인할 수 있다.

## 내부 API 탐색

| 기호 | 확인할 질문 |
| --- | --- |
| [`rx_task`] | 바이트가 명령으로 바뀌고 Stop이 우선 처리되는 곳은 어디인가? |
| [`device_task`] | 명령 수락 조건과 주기적인 실제 쓰기는 어떻게 나뉘는가? |
| [`application::Application`] | 목표각, 현재 명령각, 출력 대기 상태를 누가 보관하는가? |
| [`Devices`] | I2C·SPI·PIO의 소유권은 어디에 모이는가? |
| [`Pca`] | 주소 probe, timeout, PWM·FULL_OFF 쓰기는 어떻게 수행하는가? |
| [`Matrix`] | 논리 좌우 눈을 물리 배치로 바꾸는 시점은 언제인가? |
| [`touch_task`] | SW3·SW4·SW6의 의미가 어떤 경로에서 갈리는가? |
| [`request_stop`] | 큐를 기다리지 않는 즉시 차단 동작은 무엇인가? |
| [`run_valid`] | await 이후 무엇을 다시 확인하는가? |
| [`safety_task`] | 호스트 연결과 제어 태스크의 생존을 어떻게 확인하는가? |
| [`tx_task`] | 응답·이벤트 유실과 USB 전송 실패를 어떻게 처리하는가? |

## 공유 통로

`COMMANDS`는 USB 일반 명령 8개, `LOCALS`는 SW6 요청 2개를 보관한다. 직접 응답은 `RESPONSES` 8개, 이벤트는 `EVENTS` 16개다. `PATTERN_PRESS`와 `ARM_PATTERN_PRESS`는 최신 버튼 선택을 전달한다. `STOP_WAKE`는 장치 태스크를 깨워 출력 정리를 시작한다.

`SNAPSHOT`은 최신 터치 상태, `SESSION`은 현재 호스트 세션이다. 원자 상태 `STOPPED`, `GENERATION`, `LAST_PING`, `DEVICE_TICK`은 취소와 생존 확인에 쓰인다. 장치 작업의 일부가 await 중일 수 있으므로 이 상태를 한 번만 확인하고 끝내지 않는다.

## 완료와 정지

ACK는 수락 결과이고 Applied는 소프트웨어 적용 결과다. 포즈와 한 축 이동은 보간 완료에, 조명은 첫 프레임 쓰기에, 눈은 프레임 적용에 Applied가 발생한다. 실제 센서 측정은 없다.

Stop은 먼저 OE HIGH와 generation 변경을 수행한다. 장치 태스크의 정리 뒤 ACK를 보낸다. `Status.running`은 진단 `Run`만 표시하며 일반 출력은 `Outputs`도 확인해야 한다. `Outputs.armed`와 실제 서보 출력 활성화도 서로 다르다.

이 HTML 생성은 하드웨어 연결이나 펌웨어 업로드를 수행하지 않는다.
