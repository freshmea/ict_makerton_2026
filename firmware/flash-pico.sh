#!/usr/bin/env bash
set -Eeuo pipefail
# shellcheck source=firmware/use-linux-tools.sh
source "$(dirname -- "${BASH_SOURCE[0]}")/use-linux-tools.sh"
exec python3 -B "$PICO_REPO/firmware/pico_linux.py" flash "$@"
