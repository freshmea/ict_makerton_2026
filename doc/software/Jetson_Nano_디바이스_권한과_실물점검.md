# Jetson Nano 디바이스 권한과 실물 점검

확인일: **2026-10-24 KST**, 대상 `jetson@192.168.219.127`. [환경 설치·운영 모드](Jetson_Nano_개발환경_설치와_모드전환.md) 이후 실제로 연결된 장치를 조사하고 권한을 적용했다.

## 1. 결과

| 대상 | 실제 인식·시험 | 판정 |
| --- | --- | --- |
| 스피커 | C-Media USB `0d8c:0014`, ALSA `Device` 카드의 재생 성공. 사용자가 **시험음이 정상적으로 들렸음**을 확인 | 실제 출력 확인 |
| 마이크 | 같은 USB 장치에서 48kHz/S16_LE/mono 녹음 성공. 동시 재생한 660/880/1100Hz 순서가 마이크 입력에서 검출됨 | 실제 입력·동시 입출력 확인 |
| Pico | USB `c0de:caff`, product **Pico2 NeoPixel Bench**, `/dev/ttyACM0`. 일반 사용자·별도 서비스 계정에서 serial/USB node 읽기·쓰기 open 성공 | 열거·접근 확인. 현재는 통합 binary 펌웨어 아님 |
| 카메라 0 | 사용자 확인 Camera V3/IMX708, CSI 연결. `/dev/video*` 없음, 실제 Argus 취득 **0프레임**, `No cameras available` | 실패: 현재 BSP의 IMX708 지원 부재 |
| 카메라 1 | 같은 조건에서 `sensor-id=1`도 실제 취득 **0프레임**, `No cameras available` | 실패: 현재 BSP의 IMX708 지원 부재 |

카메라의 media/GPU/VI/ISP 장치에 대한 일반 계정 접근은 통과했다. 이것을 카메라 센서 인식이나 프레임 취득 성공으로 표시하지 않는다. 센서 드라이버 지원 부재는 확인했지만 케이블·물리 모듈의 정상 여부까지 판별한 결과는 아니다.

## 2. 권한 설정

장치를 누구나 쓸 수 있게 `0666`으로 열지 않고 **지정 그룹과 로그인 불가 서비스 계정**을 구성했다.

| 사용자 | 용도 | 추가 그룹 | 서비스 상태 |
| --- | --- | --- | --- |
| `jetson` | 개발·제3자 프로그램 실행 | 기존 그룹 유지 + `render`, `robot-device` (`audio/video/dialout` 포함) | 기존 로그인 계정 |
| `pico` | Pico USB 단독 소유 프로세스 | `robot-device`, `dialout` | 시스템 계정, 암호 잠김, nologin |
| `audiod` | USB 오디오 소유 프로세스 | `audio` | 시스템 계정, 암호 잠김, nologin |
| `camerad` | 카메라/GPU 소유 프로세스 | `video`, `render` | 시스템 계정, 암호 잠김, nologin |

서비스 계정의 HOME은 `/var/lib/300seconds/{pico,audiod,camerad}`, 소유 계정 전용 `0700`이다. PulseAudio client의 `autospawn=no`를 설정했다. 초기 `/nonexistent/.config/pulse` 경고는 실제 녹음 성공과 별개였으며, HOME을 준비한 뒤 서비스 녹음 재시험에서 사라졌다. 서비스 계정을 sudo나 debug 그룹에 추가하지 않았다.

실제 udev 파일: **`/etc/udev/rules.d/99-z-300seconds-devices.rules`**. 원본은 [권한 설정 소스](../../tools/jetson/device_access.py)에 있다.

| 매칭 대상 | 적용 |
| --- | --- |
| Pico 통합 `c0de:cafc`의 tty | `root:robot-device`, `0660`, `/dev/pico-device` |
| 현재 NeoPixel `c0de:caff`의 tty | `root:robot-device`, `0660`, **`/dev/pico-neopixel`** |
| 위 두 Pico PID의 USB device node | `root:robot-device`, `0660`; 모든 USB 장치를 허용하는 규칙은 아님 |
| C-Media `0d8c:0014`의 sound node | 표준 `audio` 그룹, `0660` 유지 |
| video4linux·media node | 표준 `video` 그룹, `0660`; 기존 NVIDIA GPU 규칙은 유지 |

udev 규칙을 재로드하고 제한된 `change` 이벤트로 현재 노드에도 적용했다. USB reset/rebind는 하지 않았다. 현재 `/dev/pico-neopixel → ttyACM0`, USB audio node, `/dev/media0`에서 적용값을 확인했다. 통합 펌웨어가 없는 현재 `/dev/pico-device` 별칭은 만들지 않았다.

기존 VS Code 서버/프로세스는 새 그룹을 자동으로 물려받지 않는다. Remote-SSH의 **Kill VS Code Server on Host 후 재연결**하거나 새 로그인으로 프로그램을 시작한다. 기존 터미널에서 즉시 시험하려면 `sg robot-device -c '실행할 명령'`으로 새 그룹을 적용할 수 있다. 단순 창 재사용으로 기존 프로세스의 그룹이 바뀌지는 않는다.

## 3. ALSA 설정과 실제 오디오

프로젝트용 이름을 **`/etc/alsa/conf.d/99-300seconds-usb.conf`**에 추가했다. 전역 default/PulseAudio 설정 대신 프로그램에서 다음 PCM 이름을 명시한다.

| 이름 | 실제 장치·포맷 |
| --- | --- |
| `robot_capture` | `hw:CARD=Device,DEV=0`, 48kHz, S16_LE, mono |
| `robot_playback` | 같은 카드, 48kHz, S16_LE, stereo |
| `robot_usb` | 같은 카드의 mixer/control |

숫자 카드 인덱스 `2`를 애플리케이션에 고정하지 않았다. 현재 USB 어댑터 한 개의 ALSA ID는 `Device`다. 같은 종류의 어댑터를 추가하거나 ID가 바뀌면 설정기를 다시 실행해 실제 카드 매칭을 확인한다. 설정기는 C-Media 대상 카드가 정확히 한 개일 때만 진행한다.

실제 시험은 root가 아닌 **`audiod`(UID998)**에서 수행했다.

- baseline: 2초, 96,000개 mono sample, RMS 약 **-49.54dBFS**, peak 617, clipping 0개.
- full duplex: 5초, **240,000개 sample**을 녹음하면서 3초간 세 시험음을 stereo로 재생했다. 녹음·재생 명령 모두 종료 코드 0, xrun 오류 없음.
- 660/880/1100Hz 검출값은 baseline 대비 각각 약 **18.9/19.2/22.4dB** 높았다. 다른 시험 주파수 대비 구분 조건도 모두 통과했다.
- 짧은 녹음 파일 재생도 성공했고, 사용자 청취 확인을 받았다. mixer의 직접 Mic playback은 off 상태였으며 ALSA hardware capture를 사용했다.
- 별도 **실제 systemd unit의 `audiod` 프로세스**에서도 USB node open과 1초 녹음을 통과했다.

음성 인식 정확도·AEC·음질 등급·장시간 지연/안정성은 이번 시험의 판정 대상이 아니다. 짧은 주파수 검출을 전체 음성 기능 완료로 확대하지 않는다.

녹음 WAV는 보드의 `/var/tmp/300seconds-audio-20261024`에 `audiod` 소유로 보관하고 Git에 복사하지 않았다. 저장소에는 측정 JSON과 명령 출력만 남겼다.

## 4. 제3자 프로세스와 systemd 검증

아래 명령은 영구 서비스 등록 없이 transient unit을 실행해 **각 서비스 계정으로 장치 node를 실제 open**한다. Pico에는 payload를 보내지 않는다.

```bash
sudo /opt/300seconds/jetson/check-device-access.sh pico
sudo /opt/300seconds/jetson/check-device-access.sh audio
sudo /opt/300seconds/jetson/check-device-access.sh camera
```

실제 결과: `pico`는 serial+USB 2개 node, `audiod`는 control/capture/playback 3개 node, `camerad`는 media/nvmap/VI/ISP/VIC/GPU 6개 node를 읽기·쓰기 모드로 열었다. 모두 비root 프로세스이며 `NoNewPrivileges=yes`로 통과했다. 반대로 `nobody`의 Pico 접근은 **EACCES(13)**로 거부됨을 확인했다.

다른 프로그램 계정에 접근을 주려면 필요한 역할 그룹만 추가하고 그 프로세스를 재시작한다. 예를 들어 오디오만 필요하면 `audio`, Pico만 필요하면 `robot-device`, 카메라는 `video,render`다. 네트워크/API 접근 권한을 여는 설정은 아니다.

카메라 서비스 설정 예시:

```ini
[Service]
User=camerad
Group=camerad
SupplementaryGroups=video render
PrivateDevices=no
PrivateTmp=no
NoNewPrivileges=yes
```

NVIDIA Argus socket은 `/tmp/argus_socket`에 있으므로 카메라 프로세스의 private `/tmp`는 실제 daemon과 맞지 않을 수 있다. `PrivateDevices=yes` 또는 별도 `DevicePolicy/DeviceAllow` 제한이 있는 서비스에서는 그룹만으로 해결되지 않으므로 unit의 장치 namespace/cgroup 정책도 맞춰야 한다. 이번 transient unit은 실제 host 장치와 `/tmp`를 사용했다.

권한이 있다는 것은 여러 프로세스가 같은 장치를 동시에 소유해도 된다는 뜻은 아니다. Pico는 `picod`, 마이크/스피커는 `audiod`, 카메라는 `camerad` 하나가 소유하고 다른 프로세스는 IPC로 요청하는 기존 경계를 유지한다. 직접 ALSA 사용과 데스크톱 PulseAudio의 같은 PCM 동시 점유는 `EBUSY`를 낼 수 있다. 이번 시험 당시 PulseAudio에는 active stream이 없었다.

## 5. Pico 범위

현재 USB descriptor는 **`c0de:caff / Pico2 NeoPixel Bench`**다. 통합 진단은 **`c0de:cafc / pico-device-v1`**이므로 서로 다른 장치로 구분했다. 현재 보드에 통합 바이너리 Hello/Status를 보내거나 펌웨어를 바꾸지 않았다.

검증한 것은 실제 USB 열거, CDC 드라이버 바인딩, 별칭/권한, `jetson`과 `pico`의 읽기·쓰기 open이다. protocol/서보·터치·LED 통합 동작은 후속 시험이다. 기존 [picod 템플릿](../../tools/pico-device-bench/picod.service)의 User `pico`도 준비됐지만 서비스 자체를 등록/자동 시작하지 않았다.

## 6. IMX708 카메라 두 개의 실패 근거

사용자는 두 모듈 모두 **Camera V3 / IMX708, CSI 연결**이라고 확인했다. 보드에서 확인한 값은 다음과 같다.

- 현재 live device tree의 module0/1은 각각 **`imx219 7-0010`**, **`imx219 8-0010`**을 지정한다.
- 커널 설정에는 IMX219·IMX477 등이 있고 **IMX708 설정/모듈/overlay는 찾지 못했다**.
- 부팅 로그에서 두 IMX219 probe 모두 I2C 응답 실패 **`-121`**로 끝난다.
- `/dev/media0`는 있지만 센서 프레임용 **`/dev/video0`, `/dev/video1`은 없다**.
- `camerad`에서 sensor-id0/1을 각각 실제 실행했으나 **수신 프레임 0**, NVIDIA plugin 출력 **`No cameras available`**였다. 권한 거부 오류로 판정한 것이 아니다.

따라서 현재 **L4T R32.6.1 / 커널4.9.253-tegra**의 장치 설정과 IMX708 지원부터 맞춰야 한다. 기존 IMX219/IMX477 overlay 이름만 바꾸거나 udev 권한만으로 센서 드라이버가 생기지 않는다.

공개된 [RidgeRun IMX708 드라이버](https://github.com/RidgeRun/NVIDIA-Jetson-IMX708-RPIV3)는 Nano용 patch를 **JetPack4.6.4** 대상으로 명시한다. 현재 보드는 JetPack4.6에 해당하는 R32.6.1이므로, 그대로 설치 가능한 동일 BSP 드라이버로 검증된 것은 아니다. IMX708을 유지하려면 지원 BSP에 맞추거나 현재 BSP로 포팅하고 **두 CSI 채널 지원을 별도로 검증**하는 작업이 필요하다. 이 작업은 이번 권한/점검 범위에서 커널·DTB 교체나 보드 재플래시로 진행하지 않았다.

## 7. 재적용과 증거

```bash
# 장치 매칭·그룹·named ALSA PCM·udev 재적용
sudo /opt/300seconds/jetson/configure-device-access.sh

# 실제 오디오 재시험: 소리를 내고 짧게 녹음한다.
sudo -u audiod python3 -B /opt/300seconds/jetson/check-usb-audio.py \
  /var/tmp/300seconds-audio-20261024
```

최초 파일/계정/그룹 상태는 `/var/lib/300seconds/device-access/baseline.json`에 root 전용으로 보관했다. 이 디바이스 설정은 프로젝트/데스크톱 양쪽 모드에서 유지된다. 기존 모드 복원은 새 계정/권한/ALSA 설정을 제거하지 않는다. 모드 baseline과 device-access baseline을 구분한다.

| 증거 | 내용 |
| --- | --- |
| [최종 상태 JSON](board-info/2026-10-24/device-final-state.json) | 실제 오디오 지표·사용자 확인, 카메라0/1 실패, 계정·node·live DT·서비스·배포 코드 해시 |
| [서비스 프로세스 시험](board-info/2026-10-24/device-service-tests.log) | 3개 transient unit 접근, ALSA 경고 해소, 카메라 취득 원본 출력 |
| [최종 접근 시험](board-info/2026-10-24/device-final-access.log) | systemd 실제 녹음·jetson open·비인가 계정 거부·계정 잠김 확인 |
| [최초 오디오 시험](board-info/2026-10-24/device-access-and-audio.log) | 실물 녹음·재생·duplex·주파수 측정, 초기 HOME 경고 포함 |
| [커널·USB·오디오 조사](board-info/2026-10-24/device-root-preflight.json) / [드라이버 조사](board-info/2026-10-24/device-diagnostics.json) | 포맷·mixer·probe 오류·IMX708 미존재 근거 |
| [구현 소스](../../tools/jetson/) | 권한 설정기·서비스 open 확인·오디오·실제 프레임 확인 코드 |

최종 상태에서도 SSH·네트워크·팬·Argus 서비스는 active, GUI와 ROS 서비스는 inactive였다. 카메라 실패를 성공으로 처리하지 않았다.
