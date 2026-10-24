# 재부팅 뒤 카메라 연결 대기 진단

2026-10-25 KST. 부팅 후 한 센서가 커널 탐색 단계에서 누락돼 두 카메라 준비 조건을 충족하지 못했다. 시작 지연으로만 표시되던 문제와 정상 카메라 미리보기가 함께 차단되던 문제를 수정했다. 두 카메라가 복구된 결과는 아니다.

## 확인된 원인과 남은 점검

- 부팅 약1.8초: `imx219 7-0010`에서 I²C 주소0x10 응답 없음, probe `-121`로 실패. `imx219 8-0010`은 바인딩 성공.
- 현재 `/dev/video0`만 존재하고 `/dev/video1`은 없음. Argus 로그는 `Invalid camera device specified 1 specified, 0 max index`다.
- 한 영상 경로는 이미 약30fps였지만, 웹과 snapshot API가 두 카메라 전체의 `ready`만 확인하여 정상 영상도 막고 있었다.
- 실제 입력 레일 `POM_5V_IN`은 4,512~4,520mV였고, 커널의 `OC ALARM 0x00000001`이 반복됐다. 전원 불안정과 케이블 접촉을 점검해야 한다. 낮은 전압만으로 센서 미인식의 단일 원인을 확정하지 않는다.
- 부팅 중 Wi-Fi 주소가 준비되기 전 대시보드 첫 bind가 실패했으나 약26초에 자동 재시작 성공했다. 현재 장시간 카메라 대기는 센서 한 대의 미인식과 전체 준비 조건 때문이었다.

[NVIDIA Nano 개발 키트 가이드](https://developer.download.nvidia.com/embedded/L4T/r32-3-1_Release_v1.0/Jetson_Nano_Developer_Kit_User_Guide.pdf)의 전원 안내는 최소4.75V와 주변장치 부하가 큰 경우 J25의5V/4A 전원 사용을 설명한다. 물리 점검은 정상 종료·전원 분리 후 양쪽 CSI 리본 케이블의 방향·삽입·잠금과 전원 어댑터·케이블·연결부를 확인하는 순서다. 현재 센서 번호는 OS 열거 번호이며 미인식 시 기존 물리 카메라 번호와 달라질 수 있다.

## 변경·검증

- `Cameras.can_preview`와 웹 미리보기를 카메라별 준비 상태로 변경했다. 다른 카메라가 빠져도 정상 카메라의 snapshot/MJPEG를 제공한다.
- 전체 `ready`는 여전히 두 카메라가 모두 준비돼야 true다. Decisions/JEV 20장 분석을 한 카메라만으로 실행하도록 바꾸지 않았다.
- 작업 시작15초 뒤에도 영상이 없는 카메라는 `영상 없음 · 카메라 연결·전원을 확인하세요.`로 표시한다. 새로 고침 시 캐시가 갱신되도록 JS 버전을 바꿨다.
- 로컬·Nano에서 관련23개 검사 통과. 정상 카메라의200 응답, 미준비 센서503, 오래된 프레임 차단, 두 카메라 분석 차단을 검증했다.
- 실기 재시작 뒤 camera0 snapshot HTTP200 / 15,700bytes, camera1 HTTP503을 확인했다. camera0 약30.01fps, camera1은0fps와 명시적인 경고다.
- 연속 관찰 설정은 기존 enabled=true로 복원했다. 센서가 빠진 상태에서는 기존 두 카메라 분석의 준비 조건을 통과하지 않는다. 이번 점검에서 유료 Decisions를 호출하거나 모터를 구동하지 않았다.

`diagnosis.json`에 부팅·전후 카메라 상태, 전압 레일명, 커널 기록과 HTTP 응답을 저장했다. `nano-tests.log`, `deployment-source.diff`, `deploy-verify.log`에 검사·변경·배포 근거가 있다. Nano 백업은 `/var/lib/300seconds-dashboard/backups/camera-partial-20261024T205942Z`다.

웹을 새로 고쳐 `1/2 온라인`, 정상 카메라의 MJPEG 영상·30fps, 다른 카메라의 연결·전원 확인 안내를 확인했다.

원본 카메라 화면 `dashboard-partial-camera.png`에는 사람이 포함돼 로컬에만 보관한다. 공개 기록은 위의 상태·HTTP 응답과 `diagnosis.json`이다.
