#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
case ${1:-} in
    pico) role=pico; account=pico; groups='robot-device dialout' ;;
    audio) role=audio; account=audiod; groups=audio ;;
    camera) role=camera; account=camerad; groups='video render' ;;
    *) echo 'Usage: check-device-access.sh {pico|audio|camera}' >&2; exit 1 ;;
esac
# Transient unit only; no [Install], reboot startup, or persistent daemon.
exec systemd-run --unit="300seconds-access-$role-$$" --wait --collect --pipe \
    --property="User=$account" --property="Group=$account" \
    --property="SupplementaryGroups=$groups" --property=NoNewPrivileges=yes \
    --property=PrivateDevices=no --property=PrivateTmp=no \
    /usr/bin/python3 -B "$SCRIPT_DIR/probe-device-access.py" "$role"
