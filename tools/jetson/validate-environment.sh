#!/usr/bin/env bash
# Synthetic/native checks only. No camera, microphone or actuator is opened.
set -Eeuo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
BUILD_DIR=$(mktemp -d /tmp/300seconds-native.XXXXXX)
trap 'rm -f -- "$BUILD_DIR/validate-native"; rmdir -- "$BUILD_DIR"' EXIT
# pkg-config deliberately supplies separate compiler/linker arguments.
# shellcheck disable=SC2046
cc -Wall -Wextra -Werror "$SCRIPT_DIR/validate-native.c" -o "$BUILD_DIR/validate-native" \
    $(pkg-config --cflags --libs alsa gstreamer-1.0 libudev openssl sqlite3)
"$BUILD_DIR/validate-native"
gst-launch-1.0 -q audiotestsrc num-buffers=8 ! audioconvert ! audioresample ! \
    webrtcdsp echo-cancel=false ! fakesink
echo 'Synthetic WebRTC DSP pipeline reached EOS; hardware audio/AEC is untested.'
# This generated file lives on the target board.
# shellcheck disable=SC1090,SC1091
source "$HOME/.local/share/300seconds/rust/env.sh"
rustc -Vv
cargo --version
