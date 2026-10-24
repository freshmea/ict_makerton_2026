# 카메라 1 장착 방향 180도 보정

2026-10-25 KST. 완성품에서 카메라1이 180도 돌아간 장착 상태라는 사용자 요청에 따라 `media_worker.py`의 `CAMERA_ROTATIONS`를 SENSOR0=180°, SENSOR1=0°로 적용했다. `nvvidconv flip-method=2`를 카메라1의 JPEG와 H.264 경로에 각각 적용하므로 MJPEG·snapshot·분석 입력·RTSP 방향이 같다. 네 촬영 프로필 모두 적용되며 재부팅 후에도 유지된다.

Nano의 설치된 `gst-inspect-1.0 nvvidconv`에서 2=rotate-180을 확인했다. 네 프로필·두 인코더 조합의 GStreamer 파이프라인을 실제 파싱하여 카메라1 두 변환기 모두2, 카메라2 두 변환기 모두0임을 확인했다. 영상 작업만 같은 프로필로 재시작했으며 대시보드 전체·Live·Pico를 재시작하지 않았다. 배포 전 연속 수집을 잠시 멈췄다가 기존 설정으로 복원했다.

배포 후 두 카메라 `ready=true`와 회전 메타데이터 `[180,0]`, 새 snapshot JPEG를 확인했다. 카메라1의 변경 전·후 사진을 직접 열어 180도 방향 변화도 확인했다. 이번 변경에서 유료 Decisions 분석이나 모터 구동을 수행하지 않았다.

`result.json`, `validate-pipelines.log`, `deploy-verify.log`에 검증 기록을 보관한다. 회전 전후 원본 사진은 로컬에만 보관하고 공개 Git에는 포함하지 않는다. Nano 백업은 `/var/lib/300seconds-dashboard/backups/camera1-rotation-20261024T212157Z/media_worker.py`다.
