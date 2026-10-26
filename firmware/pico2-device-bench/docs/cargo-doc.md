# Cargo로 한국어 HTML 문서 만들기

이 패키지의 설명 문서와 API 주석은 Rust의 rustdoc으로 HTML이 된다. 라이브러리의 전체 해설은 `architecture.md`와 `use-cases.md`를 `include_str!`로 포함한다. 설명을 고친 뒤 다시 생성하면 Markdown과 HTML이 같은 내용을 사용한다.

## Windows에서 생성하기

저장소 루트에서 실행한다.

```powershell
./firmware/pico2-device-bench/build-docs.ps1
```

브라우저도 열려면 다음을 사용한다.

```powershell
./firmware/pico2-device-bench/build-docs.ps1 -Open
```

스크립트는 저장소에 준비된 Rust 1.90을 우선 사용한다. 없으면 PATH의 Cargo와 rustc를 사용하므로 Rust 1.90 이상과 임베디드 대상이 필요하다. `--locked --offline`으로 실행하므로 의존성과 대상 표준 라이브러리는 미리 준비되어 있어야 한다. 생성 중 사용한 환경 변수는 종료 시 복원한다. 장치 연결이나 업로드는 하지 않는다.

두 HTML의 역할은 다르다.

| HTML | 내용 | Windows 기본 출력 경로 |
| --- | --- | --- |
| 라이브러리 | 전체 해설, 데이터 흐름, 사용 사례, 순수 로직 API와 예제 | `target/learning-docs/library/x86_64-pc-windows-msvc/doc/pico2_device_bench/index.html` |
| RP2350 실행부 | 태스크·큐·드라이버·Application의 비공개 내부 API | `target/learning-docs/device/thumbv8m.main-none-eabihf/doc/pico2_device_bench/index.html` |

경로는 `firmware/pico2-device-bench` 기준이다. HTML 옆의 `src`와 `static.files`, 검색 파일도 필요하므로 다른 PC에 옮길 때는 각 `doc` 폴더 전체를 복사한다. 생성물은 Git의 `target/` 제외 규칙을 따르고 문서 원본과 생성 스크립트를 버전 관리한다.

스크립트는 `docs/index.md`도 rustdoc으로 변환해 각 `doc/index.html`에 놓는다. Cargo가 기본으로 만들지 않는 문서 루트의 안내 페이지다. 도움말과 설정 화면의 홈 링크가 이 페이지로 연결된다.

## HTML에서 코드로 이동하기

1. 라이브러리 첫 화면의 전체 해설을 읽는다. 우측의 문서 목차로 특정 절에 이동한다.
2. 함수·모듈 이름을 눌러 해당 API의 설명과 예제를 읽는다.
3. 검색창에서 `SessionGate`, `ArmPatterns`, `interpolate_pose`를 찾는다.
4. 항목의 Source 링크를 누르면 실제 Rust 소스의 해당 위치가 열린다.
5. 실행부 HTML에서 `device_task`, `rx_task`, `application::Application`을 탐색한다. 비공개 항목은 잠금 표시가 붙는다.

호스트용 라이브러리 HTML에 `main.rs`의 태스크가 없는 것은 정상이다. `application.rs`는 바이너리 내부 모듈이고 `picotool_reset::State/register`는 임베디드 대상에만 포함된다. 태스크는 Embassy 매크로로 확장되어 표시될 수 있다.

## Cargo 명령을 직접 실행하기

다음은 패키지 디렉터리에서 사용하는 명령이다. 기본 타깃이 임베디드이므로 PC 문서·테스트에는 `--target`을 명시한다.

```powershell
# 순수 로직과 전체 해설.
cargo doc --locked --offline --lib --target x86_64-pc-windows-msvc --no-deps --target-dir target/learning-docs/library --open

# 임베디드 실행부. 드라이버와 태스크의 비공개 항목도 문서화한다.
cargo rustdoc --locked --offline --bin pico2-device-bench --target thumbv8m.main-none-eabihf --target-dir target/learning-docs/device -- --document-private-items

# 실제로 실행 가능한 문서 예제와 기존 호스트 로직 검사.
cargo test --locked --offline --lib --target x86_64-pc-windows-msvc
cargo test --locked --offline --doc --target x86_64-pc-windows-msvc
```

Linux에서는 호스트 부분의 `x86_64-pc-windows-msvc`를 `rustc -vV`의 host 값으로 바꾼다. 임베디드 실행부의 타깃은 그대로 유지한다.

실행부에는 rustdoc 옵션을 직접 전달하는 `cargo rustdoc --bin`을 사용한다. 이 패키지의 lib와 bin은 같은 Rust crate 이름 `pico2_device_bench`를 사용한다. Cargo 1.90은 바이너리를 문서화할 때 의존하는 라이브러리도 문서화하여 `output filename collision` 경고를 낸다. 경고를 숨기거나 실행 바이너리 이름을 바꾸지는 않았다. 실행부 폴더의 최종 index가 `RP2350 실행부와 내부 API`이며 `device_task`와 Application 페이지가 있는지 확인했다.

라이브러리 해설은 별도 출력 폴더에 생성하므로 실행부 생성에 덮어써지지 않는다. 두 결과가 같은 crate 이름으로 표시되더라도 서로 다른 문서다. `doc = false`로 기본 문서 대상을 감추거나 실제 바이너리 이름을 바꾸는 설정은 추가하지 않았다.

## 주석을 갱신하는 방법

`//!`는 모듈 전체의 설명, `///`는 바로 다음 항목의 API 설명이다. `#![doc = include_str!(...)]`는 외부 Markdown을 crate 설명으로 포함한다. 소스에 API 설명과 단위, 호출 조건, 반환값을 쓰고 큰 흐름은 해설 Markdown에서 다룬다.

이번 예제는 포즈 보간, 중복 명령 방지, SW3 프레임, SW4 복귀, ROM serial 변환을 PC에서 실행한다. 실제 USB, I2C, 서보를 열지 않는다. 장치 명령의 예시는 실행되는 Rust 코드 블록으로 만들지 않았다.

스크립트는 rustdoc 내부 링크와 bare URL 오류를 빌드 실패로 처리한다. 문서에 함수를 연결할 때는 해당 대상에서 실제로 존재하는 항목을 사용한다. 펌웨어의 실제 동작 변경은 호스트 단위 테스트와 임베디드 빌드, 실물 확인을 별도로 진행한다.

공식 설명은 [Cargo doc](https://doc.rust-lang.org/cargo/commands/cargo-doc.html), [doc 속성](https://doc.rust-lang.org/rustdoc/write-documentation/the-doc-attribute.html), [rustdoc 명령 옵션](https://doc.rust-lang.org/rustdoc/command-line-arguments.html)에서 확인할 수 있다.

## 2026년 10월 26일 생성 검증

Rust 1.90으로 두 HTML 생성을 완료했다. rustdoc 내부 링크와 bare URL 검사를 통과했으며, 기존 호스트 단위 테스트 24개와 실행 가능한 문서 예제 5개가 통과했다. 생성된 라이브러리 49페이지와 실행부 83페이지에서 로컬 링크 대상 949개를 검사했고 누락된 파일 경로는 없었다. 검색 파일, 스타일 자산, 주요 API와 Source 대상 파일도 확인했다.

Cargo의 동일 이름 lib·bin 충돌 경고는 실행부 생성에 남아 있다. 최종 index의 제목과 실제 태스크·Application 페이지를 확인했다. 내장 브라우저는 로컬 `file:` 주소를 정책상 차단해 화면을 시각적으로 검수하지 못했다. HTML의 본문과 경로 검사는 파일 수준에서 수행했다.

실행 기록은 저장소 루트의 `tmp/firmware-docs-2026-10-26`에 있다. `build-docs-final.log`, `host-tests.log`, `doc-tests.log`, `html-check.json`이 각각 생성·단위 테스트·문서 예제·HTML 경로 검사 결과다. `tmp`와 `target`은 로컬 생성물이며 Git에는 포함하지 않는다.
