# Windows·Jetson·GitHub 동기화 검증

[진행 작업 종합 정리](../../../진행작업_종합정리와_Git동기화_2026-10-25.md)의 소스·문서·완료 산출물을 공유하는 기록이다. 운영 설치본을 새로 배포하거나 서비스를 재시작하는 작업과 구분한다.

## 게시 전 검사

- Windows: `dashboard-tests.log` 154개, `jetson-provider-tests.log` 83개, `protocol-tests.log` 13개 통과.
- Nano: Git index에서 내보낸 동일 소스를 임시 폴더에서 검사했다. `nano-dashboard-tests.log` 154개, `nano-jetson-provider-tests.log` 83개 통과. 위치·검사 tree는 `nano-validation-location.json`에 있다.
- JavaScript app·study·learning·analytics 구문 검사, 변경 Markdown의 로컬 링크 존재 검사, index의 `git diff --check` 통과.
- `jetson-source-comparison.json`: Nano 미커밋54개 중51개가 Windows와 같고,3개는 Windows의 후속 문서·SW2 검사가 더 최신임을 비교했다. Nano 원본은 로컬 보존·보드 stash/백업으로 유지한다.
- `snapshot-audit.json`: 신규 공유 파일의 크기와 키·암호 패턴 점검. 카메라 원본·개인 관찰 텍스트·원문 세션 진단은 `.gitignore`로 로컬 보관하며 기술 요약만 게시한다.

## 최종 동기화 기록

작업 커밋 `da7f58536792baaa8613bee0f9a586d6e77b1eea`를 일반 push한 뒤 Nano 원본54개를 tar·stash·보호 참조에 보존하고 GitHub main을 fast-forward했다. [sync-verification.json](sync-verification.json)에 Windows·Jetson·origin 커밋 일치, Jetson 작업 트리 청결, 서비스3개 active·PID 동일, 카메라 두 대·Pico·수집 정상 상태를 기록했다. `nano-git-sync.log`는 보드 측 같은 검증 결과다.

보존 tar는 Nano `/home/jetson/ict_makerton_git_backups/20261024T232343Z/uncommitted-sources.tar.gz`, stash는 `b961188a1c23e893ec9fd044cedc909ce3377db9`, 보호 참조는 `refs/backups/jetson-pre-sync-20261024T232343Z`다. 기존 stash는 삭제하지 않았다. Git source의 root 소유 음원 디렉터리2개만 jetson 소유로 정리해 원본 stash·checkout을 가능하게 했으며 운영 설치본은 건드리지 않았다.

이 검증 문서·JSON을 후속 문서 커밋으로 게시한 뒤 양쪽을 다시 fast-forward한다. 검증 JSON의 SHA는 기능 작업 커밋을 가리킨다. 정확한 최신 문서 커밋은 양쪽 `git rev-parse HEAD`와 `origin/main`으로 확인한다.
