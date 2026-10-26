## 11. 사용 사례로 흐름 따라가기

다음 순서는 코드 이해를 위한 메시지 흐름이다. 자동으로 장치를 움직이는 실습 스크립트가 아니다. 실제 명령은 배선과 보정, 장치 상태를 확인하고 기존 호스트 브리지를 통해 전송한다.

### 사례 1. 연결하고 상태만 읽기

호스트가 0이 아닌 session으로 `Hello`를 보낸다. 새 세션이면 펌웨어는 이전 동작을 정리하고 `SessionGate::open()`으로 sequence 캐시를 초기화한다. `HelloReply`, `Capabilities`, `ServoDriver`, ACK를 반환한다. Hello만으로 서보 PWM을 시작하지 않는다.

이후 새 seq의 `KeepAlive`를 계속 보내고 `GetStatus`를 요청한다. Status와 Outputs, 드라이버 진단을 함께 읽는다. `Status.running=None`만으로 모든 출력이 꺼졌다고 판단하지 않는다.

```text
호스트                  rx_task / device_task                 tx_task
 Hello(session=S)  ---> 이전 상태 정리, gate.open(S) ----------> HelloReply + ACK
 KeepAlive(seq=N)  ---> LAST_PING 갱신 -----------------------> ACK
 GetStatus        ---> 상태 스냅샷 --------------------------> Status + Outputs + ACK
```

### 사례 2. 서보 한 축을 목표각으로 이동

1. 살아 있는 session과 새 KeepAlive를 유지한다.
2. `Arm(ActuatorConfig)`에 축별 보정과 `servo_enabled=true`를 전달한다.
3. `SetServo { channel:2, target_cdeg:10000, move_ms:1000 }`을 보낸다. CH2는 사용자 번호로 서보 3번이다.
4. `device_task`가 fault, lease, Stop 상태, Application과 기존 이동을 검사한다.
5. `Application::servo()`가 다른 다섯 축을 보존한 목표 배열과 `pose_mask=0b000100`을 만든다.
6. ACK Ok 이후 `tick()`이 현재값에서 목표값까지 보간한다. 필요하면 속도 제한 때문에 요청한 시간보다 늘린다.
7. 선택 채널의 보정 pulse를 I2C로 쓴다. 유효성을 재검사한 뒤 OE를 LOW로 연다.
8. 완료 시 `Applied { request_seq, kind:4 }`를 보낸다.

단일 축 이동 중 새 단일 축 명령은 Busy다. 이 경로는 긴 이동 큐를 쌓지 않는다. 일반 포즈 이동의 목표 교체 정책과 똑같다고 가정하지 말고 해당 분기를 읽는다.

```text
SetServo -> servo_target -> target[6] + mask
         -> ACK Ok
         -> tick -> interpolate_pose -> cfg.ticks -> Pca::pulse
         -> 다음 tick들 ... -> Applied(kind=4)
```

### 사례 3. SW3로 조명 패턴 바꾸기

`touch_task`가 raw GPIO를 읽고 active-low 설정을 적용한다. `PatternButton`은 안정된 해제와 generation을 확인한 다음 디바운스된 `Pressed` 이벤트를 받는다. 설명에서 흔히 짧은 누름이라고 부르지만, 구현의 선택 시점은 release가 아닌 눌림 edge다.

`PATTERN_PRESS`에 최신 `(generation, entropy)`를 넣으면 `device_task`가 다음 tick에서 확인한다. 진단 Run이 없고 session과 lease가 살아 있어야 한다. 기존 Application 조명을 지운 뒤 `ButtonPatterns::select()`로 직전과 다른 패턴을 고른다.

`frame(now, segments, side)`는 시간에서 좌우 RGB 배열을 계산한다. 장치 태스크가 이 배열을 PIO·DMA로 전송한다. 계산 함수 자체에는 타이머 대기나 하드웨어 쓰기가 없다. Stop까지 계속 갱신하며, 다시 누르면 현재 패턴을 바로 바꾼다. 호스트가 없는 독립 SW3 실행은 이 경로에서 허용하지 않는다.

### 사례 4. SW4로 팔 패턴 실행

SW4도 `PatternButton`을 사용하지만 인덱스 4와 `ARM_PATTERN_PRESS`를 쓴다. 다음 조건이 추가된다.

- PCA fault가 없다.
- CH0~CH3의 소프트웨어 기준각이 모두 알려져 있다.
- 호스트가 서보 사용을 Arm으로 소유하고 있지 않다.
- 이미 일반 포즈를 이동 중이지 않다.

`ArmPatterns`는 첫 선택 당시 기준각을 저장하고 1초 구간 아홉 개로 움직임을 만든다. 기준각에서 최대 ±12도이며 각 목표는 0~180도 범위로 제한된다. 재선택해도 기준각은 바꾸지 않고 현재 위치부터 시작하므로 누를 때마다 중심이 밀리지 않는다.

9초가 되면 계산 함수는 기준각을 반환한다. 출력부는 CH0~CH3을 off하고 공통 OE를 HIGH로 올린 뒤 `clear()`한다. CH4~CH5의 **소프트웨어 목표값**은 바꾸지 않는다. OE가 공통이므로 그 두 채널의 실제 PWM 전달까지 독립적으로 계속 유지한다는 뜻은 아니다.

### 사례 5. SW6로 독립 진단

SW6은 부팅 후 raw 해제가 30ms 유지된 뒤 새 누름을 받는다. `Gesture`는 기본 500ms hold 구간 수로 release 때 진단을 선택한다.

| 구간 수 | 선택 |
| --- | --- |
| 0 또는 1 | 눈 매트릭스 |
| 2 | 왼손 NeoPixel |
| 3 | 오른손 NeoPixel |
| 4 | 서보 순차 진단 |
| 5 | 눈 → 왼손 → 오른손 → 서보 |
| 누른 채 6 도달 | 전체 Stop |

동작 중 새 SW6 눌림도 Stop이다. 진단 요청은 `LOCALS`를 거쳐 `Run`을 만든다. `Run`이 module과 phase를 순서대로 진행하고 완료·중단을 `TestEvent`로 보낸다.

SW3·SW4와 달리 SW6 유한 진단은 원격 session이 없어도 가능하다. 원격 session이 있으면 동일한 호스트 lease를 적용한다. 취소된 누름의 release는 새 진단을 시작하지 않는다.

### 사례 6. 동작 중 Stop 또는 연결 끊김

정상 CRC·version의 Stop은 session과 seq 검사 전에 OE를 HIGH로 올리고 generation을 바꾼다. USB 연결 끊김, lease 만료, SW6 Stop과 안전 검사도 같은 정지 경로를 사용한다. 일반 작업은 저장해 둔 generation과 현재 generation이 달라지면 더 진행하지 못한다.

장치 태스크는 Application·패턴을 제거하고 모든 출력 정리를 시도한다. 진단 중이었다면 중단 이벤트의 `done=true, fault=true`를 보낸다. 이는 자연 완료가 아니라 중단이라는 뜻이며 하드웨어 고장 비트와는 별개다. Stop만으로 `Status.faults`를 지우지 않는다.

CPU panic에서는 OE를 HIGH로 쓰지만 이미 LED나 매트릭스에 래치된 표시는 남을 수 있다. 소프트웨어 Stop을 독립 전원 차단 장치로 해석하면 안 된다.

### 사례 7. 위치 기준을 복원하거나 PCA를 점검

`SeedServoPositions`는 저장한 마지막 명령각을 복원한다. 출력이 차단되고 구동 중이 아닐 때 기준 배열과 알려진 축 mask만 바꾼다. 이 명령은 PWM을 발생시키지 않으며 실제 각도를 측정하지도 않는다.

`CheckServoDriver`는 Run과 Application이 없고 OE HIGH일 때 PCA를 probe·초기화한다. 0x40과 0x41 중 정상 주소가 정확히 하나여야 한다. 초기화에 성공한 경우에만 PCA fault를 지운다. GPIO HIGH/LOW를 확인해도 전압을 측정한 것은 아니다.

### 사례 8. BOOTSEL로 전환

wire `Bootloader`와 picotool reset interface는 출력 정리 요청으로 합류한다. USB 제어 handler 안에서 바로 reset하지 않는다. 장치 태스크가 정리 오류가 없는지 확인하고 지연 후 ROM USB boot로 전환한다. 제어 요청 Accepted와 실제 ROM 진입은 다른 시점이다.

### 사례 9. 일반 조명과 눈 프레임 적용

서보를 쓰지 않는 Arm 설정으로도 `Application`을 만들 수 있다. `SetLight`는 RGB, 밝기, 주기를 저장하고 다음 tick에서 양쪽 프레임을 쓴다. 주기 0은 고정 조명이며 그 외에는 삼각파 밝기를 사용한다. 첫 쓰기 뒤 Applied kind 2를 보낸다. SW3 패턴은 이 명령을 수락할 때 해제한다.

`SetEyes`는 논리 좌우 8행과 밝기를 저장한다. `matrix_installed=true`가 필요하며 다음 tick에서 장착 보정, SPI 쓰기와 enable을 수행한 뒤 Applied kind 3을 보낸다. 양쪽 눈을 하드웨어에 래치한 뒤에는 새 프레임이 없어도 표시가 남는다. 따라서 대기 중 눈 프레임이 없다는 사실이 눈이 꺼져 있다는 뜻은 아니다.

## 12. 명령별 읽기 지도

| 명령 | 주요 처리 | 결과 읽기 |
| --- | --- | --- |
| Hello | 새 세션이면 이전 상태 정리, ACK 캐시 초기화 | HelloReply·Capabilities·ServoDriver·ACK |
| KeepAlive | 새 seq일 때 lease 갱신 | ACK |
| GetStatus | 현재 상태 조회 | Status·Outputs·Capabilities·ServoDriver·ACK |
| Configure | idle에서 RAM 설정과 터치 설정 교체 | ACK, 이후 Status |
| Arm | 보정·허용 조건 검사 후 Application 생성 | ACK, Outputs |
| SetPose | 6축 목표 보간 | ACK, Applied kind 1 |
| SetServo | 선택 축 목표 보간 | ACK, Applied kind 4 |
| SetLight | 일반 조명 목표 | ACK, 첫 적용 시 Applied kind 2 |
| SetEyes | 눈 프레임 목표 | ACK, Applied kind 3 |
| SeedServoPositions | 출력 없이 명령 기준각 복원 | ACK, Outputs |
| CheckServoDriver | 비구동 상태에서 PCA probe·초기화 | ServoDriver·ACK |
| RunTest | 유한 진단 Run 생성 | ACK, TestEvent |
| Stop | 즉시 OE 차단 후 전체 정리 | ACK, 상태·중단 이벤트 |
| Bootloader | 출력 정리 뒤 ROM boot | 정리 결과 ACK, USB 재열거 |

Configure는 RAM 설정이므로 재부팅하면 기본값으로 돌아온다. 위 표의 ACK는 모든 전제조건을 만족했을 때의 응답 흐름이며, 조건에 따라 Busy·Fault·NoSession·InvalidConfig 등으로 거절될 수 있다.

## 13. 변경할 때 어디서 시작할까

| 변경 목표 | 먼저 볼 곳 | 확인할 계약 |
| --- | --- | --- |
| SW3 새 효과 | `light_patterns::pattern_frame` | RGB 상한, tail 검정, side·segment 구분 |
| SW4 새 팔 동작 | `arm_patterns::STEPS`와 테스트 | 기준각 유지, 속도, 복귀, CH4~CH5 값 보존 |
| 새 장치 명령 | 공통 `Message` → RX → `device_task` → Application | wire 호환성, ACK·Applied, session·generation·lease |
| 단일 서보 동작 | `servo_target` → `Application::servo/tick` | 축 mask, 전체 보정 범위, Busy와 취소 |
| 버튼 방식 변경 | `TouchEngine`, `ReleaseGuard`, `Gesture`, `PatternButton` | raw 해제, 디바운스, generation 변경 |
| 장치 드라이버 변경 | `Pca`, `Matrix`, `Devices` | timeout, OE 재개방 전 검사, 오류 비트 |

호스트 단위 테스트는 순수 계산과 메시지 계약을 확인한다. 임베디드 빌드는 실제 타깃에서 타입과 의존성이 맞는지 확인한다. 실제 점등·움직임·전원·지연은 별도의 장치 검증이 필요하다.
