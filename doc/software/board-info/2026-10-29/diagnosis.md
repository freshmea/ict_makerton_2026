# Jetson Nano 부팅 장애 원격 진단

조사일: 2026-10-29, 한국 시간. SSH 대상: `192.168.219.127`, 호스트 `nano`.
비밀번호는 기록하지 않았다. 원격 설정 변경, 서비스 재시작, 재부팅, 패키지 변경은 하지 않았다.

## 결론과 확실성

1. **이전 부팅의 SquashFS 커널 충돌과 최종 hard lockup은 확인됐다.** `/var/lib/systemd/pstore/dmesg-ramoops-{0,1,2}`에 보존된 기록에서 부팅 8.999초에 첫 메모리 접근 오류가 발생한다. `squashfs_bh_to_actor` → `squashfs_process_blocks` → `read_wq_handler` 경로이며, 9.248초에 `kthread_data`의 2차 오류, 36.294초에 watchdog hard LOCKUP에 의한 kernel panic이 이어진다. `crash-pstore.txt`에 보존했다.
2. **사용자가 첨부한 사진과 같은 계열의 오류이나 동일 부팅이라고 확정하지 않는다.** 보존 파일의 수정 시각은 장치 기준 2026-10-25 03:43 +01:00이다. 이는 보존 시각이며 정확한 장애 발생 시각을 보장하지 않는다. 사진에서 읽히는 paging request 오류와 kthread 경로는 일치하지만 전체 최초 오류와 타임스탬프를 사진에서 확정할 수 없다.
3. **가장 유력한 조사 대상은 구형 커널의 SquashFS 처리와 Snap 이미지 접근이다.** 현재 Snap 이미지 15개가 SquashFS로 마운트되어 있다. 프로젝트 모드는 snapd를 제한하지만 이미지 마운트까지 제거하지 않는다. 어느 이미지가 충돌을 유발했는지, 결함의 정확한 코드 위치나 데이터 손상 여부는 아직 증명하지 못했다. 이 기록만으로 SD카드/RAM 고장이라고 판정하지 않는다.
4. **대시보드 접속 불가는 별도로 원인이 확정됐다.** 실제 IP는 `192.168.219.127`인데 `/etc/300seconds/dashboard.env`의 `DASHBOARD_BIND=192.168.184.76`이 남아 있다. 서비스가 `Errno 99: cannot assign requested address`로 반복 종료되고 시작 횟수 제한에 걸렸다. 조사 종료 시 8000 포트의 listener가 없다.
5. **HDMI 연결이 해결했다는 증거는 없다.** 현재 연결된 모니터로 부팅한 커널에는 Oops/panic이 없지만, 모니터 유무를 제외한 조건을 통제한 재현 시험은 하지 않았다.

## 현재 상태와 제한

- Ubuntu 20.04.6, L4T R32.6.1, kernel 4.9.253-tegra. NVIDIA R32.6.1의 공식 sample rootfs는 Ubuntu 18.04 기반이므로 현재 구성은 공식 기본 조합과 다르다. 이를 단독 원인으로 단정하지 않는다.
- SSH 접속 가능, 기본 target은 의도된 프로젝트 모드인 `multi-user.target`이다.
- 현재 부팅에서 Oops, kernel panic, OC ALARM, 블록 I/O 오류를 발견하지 못했다.
- POM_5V_IN 센서: 약 1초 간격 5회, 4880/4952/4952/4952/4912 mV. 현재 주변장치와 낮은 부하에서의 관측이다. 부팅 순간, 서보/LED 연결 상태, 부하 상태의 전원 안정성을 검증한 결과가 아니다.
- 현재 USB 목록에는 Pico가 없으며 두 CSI 카메라 모두 probe -121 오류가 있다. 주변장치가 분리된 상태일 수 있으므로 고장으로 확정하지 않는다.
- 루트 파일시스템 59GB 중 47GB 사용, 가용 약 9GB. 부팅 시 ext4 journal recovery와 orphan inode 정리가 있었지만 SD카드 매체 고장을 입증하는 로그는 없다.
- `journalctl -b -1`이 없는 이유를 단순 휘발성 로그 설정으로 설명하면 부정확하다. 실제 설정은 `Storage=persistent`, `SystemMaxUse=16M`, `MaxRetentionSec=2day`다. 4일 전 기록은 보존 범위 밖이며 용량 제한도 있다. 정확한 삭제 계기는 확인하지 못했다. 기존 답변의 일반적인 가능성 설명을 이 실측 결과로 대체한다.

## 후속 조치

- 대시보드는 기존 설정을 백업한 뒤 bind 주소와 방화벽을 현재 네트워크에 맞추면 된다. 모든 인터페이스로 무조건 공개하기보다 프로젝트의 네트워크 접근 정책을 먼저 확인한다.
- 커널 장애는 현재 데이터를 백업한 후 Snap 마운트/부팅 접근을 가역적으로 차단하여 비교 부팅하는 것이 유력한 분리 시험이다. snapd만 중지하는 것으로는 마운트가 없어지지 않는다. 이 진단에서는 원격 연결을 유지하기 위해 재부팅·마운트 변경을 수행하지 않았다.
- 장기 해결은 사용 중인 애플리케이션 의존성을 검토하여 Nano에 맞는 공식 BSP/OS 조합 또는 검증된 커널 수정으로 정리하는 것이다. OS 재설치나 커널 업그레이드를 임의 실행하지 않았다.

## 근거

- `crash-pstore.txt`: 보존된 Oops 2건과 watchdog panic. 같은 부팅의 누적 스냅샷이므로 독립 장애 3건으로 세지 않는다.
- `kernel-current.txt`: 현재 부팅 전체 커널 로그.
- `services.txt`, `service-config.txt`, `verification.txt`: bind 실패, journal 정책, 현재 IP와 입력 전압.
- `health.txt`, `package-detail.txt`: 마운트·장치·패키지 상태.
- [NVIDIA R32.6.1 공식 배포 정보](https://developer.nvidia.com/embedded/linux-tegra-r3261): Ubuntu 18.04 기반 sample filesystem 및 JetPack 4.6.
- [NVIDIA 포럼의 동일 SquashFS 호출 경로 사례](https://forums.developer.nvidia.com/t/jetson-nano-compatibility-issues-with-ubuntu-20-04/352577): 비슷한 환경의 사용자 보고이며 이 보드의 원인을 대신 증명하지 않는다.
