#!/usr/bin/env bash
set -Eeuo pipefail
# shellcheck source=firmware/use-linux-tools.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/use-linux-tools.sh"
PICOTOOL=$(python3 -B "$PICO_REPO/firmware/pico_linux.py" tool-path)
FW="$PICO_REPO/firmware/pico2-device-bench"
mkdir -p "$FW/dist/linux"
# The crate's .cargo config is found by running in the crate directory.
cd "$FW"
cargo build --release --locked --jobs "${PICO_BUILD_JOBS:-2}" --target thumbv8m.main-none-eabihf
"$PICOTOOL" uf2 convert target/thumbv8m.main-none-eabihf/release/pico2-device-bench \
    -t elf dist/linux/pico2-device-bench.uf2 --family rp2350-arm-s --platform rp2350
"$PICOTOOL" info -a dist/linux/pico2-device-bench.uf2
cd "$PICO_REPO"
cargo build --release --locked --jobs "${PICO_BUILD_JOBS:-2}" --manifest-path tools/pico-device-bench/Cargo.toml
python3 -B "$PICO_REPO/firmware/pico_linux.py" record-image
echo 'Built RP2350 UF2 and native Linux USB host. No flash write performed.'
