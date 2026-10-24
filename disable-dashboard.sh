#!/usr/bin/env bash
# Run on the Nano: bash disable-dashboard.sh
set -Eeuo pipefail

if [[ ${1:-} == -h || ${1:-} == --help ]]; then
    echo 'Usage: bash disable-dashboard.sh'
    echo 'Stop the dashboard and disable boot autostart.'
    exit 0
fi
if (( $# != 0 )); then
    echo 'Usage: bash disable-dashboard.sh' >&2
    exit 2
fi
if (( EUID != 0 )); then
    exec sudo -- bash "$0" "$@"
fi

service=300seconds-dashboard.service
systemctl disable --now "$service"
if systemctl is-active --quiet "$service" || systemctl is-enabled --quiet "$service"; then
    echo 'Dashboard shutdown or autostart disable failed.' >&2
    exit 1
fi
echo 'Dashboard stopped (boot autostart off).'
