#!/usr/bin/env bash
# Run as the developer, never as root. Dependencies are installed separately.
set -Eeuo pipefail
# shellcheck source=firmware/use-linux-tools.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/use-linux-tools.sh"
[[ $EUID -ne 0 ]] || { echo 'Run as your regular development user.' >&2; exit 1; }
for tool in git cmake make g++ pkg-config rustup python3 fuser; do
    command -v "$tool" >/dev/null || { echo "Missing dependency: $tool" >&2; exit 1; }
done
pkg-config --exists libusb-1.0 || { echo 'Install libusb-1.0-0-dev first.' >&2; exit 1; }
rustup toolchain install 1.90.0 --profile minimal
rustup target add thumbv8m.main-none-eabihf --toolchain 1.90.0
mkdir -p "$PICO_TOOL_HOME"
checkout() {
    local url=$1 revision=$2 directory=$3
    if [[ ! -d "$directory/.git" ]]; then
        [[ ! -e "$directory" ]] || { echo "Refusing existing non-Git directory: $directory" >&2; exit 1; }
        git init "$directory"
        git -C "$directory" remote add origin "$url"
    fi
    [[ $(git -C "$directory" remote get-url origin) == "$url" ]] || { echo 'Unexpected tool source URL.' >&2; exit 1; }
    [[ -z $(git -C "$directory" status --porcelain) ]] || { echo "Modified tool source: $directory" >&2; exit 1; }
    if ! git -C "$directory" cat-file -e "$revision^{commit}" 2>/dev/null; then
        git -C "$directory" fetch --depth 1 origin "$revision"
    fi
    git -C "$directory" checkout --detach "$revision"
}
checkout https://github.com/raspberrypi/picotool.git 2041936441b48a3cc53ae3da9e805229fe8f4e18 "$PICO_TOOL_HOME/source"
checkout https://github.com/raspberrypi/pico-sdk.git a1438dff1d38bd9c65dbd693f0e5db4b9ae91779 "$PICO_TOOL_HOME/sdk"
cmake -S "$PICO_TOOL_HOME/source" -B "$PICO_TOOL_HOME/build" \
    -DPICO_SDK_PATH="$PICO_TOOL_HOME/sdk" -DCMAKE_INSTALL_PREFIX="$PICO_TOOL_HOME/install" \
    -DUSE_PRECOMPILED=ON -DPICOTOOL_NO_LIBUSB=OFF -DCMAKE_BUILD_TYPE=Release
cmake --build "$PICO_TOOL_HOME/build" --parallel "${PICO_BUILD_JOBS:-2}"
cmake --install "$PICO_TOOL_HOME/build"
python3 -B "$PICO_REPO/firmware/pico_linux.py" record-tool
echo 'Linux tools ready. Next: bash firmware/build-pico-device.sh'
