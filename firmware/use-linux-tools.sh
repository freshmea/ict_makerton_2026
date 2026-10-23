#!/usr/bin/env bash
# Source from the build/setup wrappers; keep the board's other Rust installs intact.
PICO_REPO=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
if [[ -f "$HOME/.local/share/300seconds/rust/env.sh" ]]; then
    # shellcheck source=/dev/null
    source "$HOME/.local/share/300seconds/rust/env.sh"
fi
export RUSTUP_TOOLCHAIN=1.90.0
PICO_TOOL_HOME="$PICO_REPO/.local-tools/linux/picotool/2.3.1"
export PICO_REPO PICO_TOOL_HOME
