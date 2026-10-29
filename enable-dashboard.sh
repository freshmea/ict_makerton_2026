#!/usr/bin/env bash
# Run on the Nano: bash enable-dashboard.sh (Wi-Fi address is automatic)
set -Eeuo pipefail

if [[ ${1:-} == -h || ${1:-} == --help ]]; then
    echo 'Usage: bash enable-dashboard.sh'
    echo 'Detect connected Wi-Fi, enable boot autostart, and restart the dashboard.'
    exit 0
fi
if (( $# > 0 )); then
    echo 'Usage: bash enable-dashboard.sh' >&2
    exit 2
fi
if (( EUID != 0 )); then
    exec sudo -- bash "$0" "$@"
fi

service=300seconds-dashboard.service
env_file=/etc/300seconds/dashboard.env
for command in systemctl ip python3 pgrep; do
    command -v "$command" >/dev/null || { echo "Required command not found: $command" >&2; exit 1; }
done
if [[ $(systemctl show "$service" --property=LoadState --value) != loaded || ! -f $env_file ]]; then
    echo 'Install the Nano dashboard first: sudo bash apps/device-dashboard/install.sh' >&2
    exit 1
fi

runtime_units=$(systemctl list-units --type=service --state=active --no-legend --plain '300seconds-runtime@*.service')
if systemctl is-active --quiet 300seconds-runtime.target || [[ -n $runtime_units ]] || pgrep -x nano-runtime >/dev/null; then
    echo 'The Rust runtime is using the devices. Stop it before starting the dashboard:' >&2
    echo "sudo systemctl stop 300seconds-runtime.target '300seconds-runtime@*.service'" >&2
    exit 1
fi

network=/opt/300seconds/dashboard/app/wifi_network.py
if [[ ! -f $network ]]; then
    echo 'Install the current dashboard Wi-Fi launcher first.' >&2
    exit 1
fi

systemctl enable "$service"
systemctl reset-failed "$service"
if ! systemctl restart "$service"; then
    journalctl -u "$service" -n 30 --no-pager >&2
    exit 1
fi

bind=$(python3 "$network" --print-address)
if [[ -z $bind ]]; then
    echo 'Dashboard enabled; waiting for Wi-Fi. It will start when Wi-Fi receives an IPv4 address.'
    exit 0
fi

if ! python3 - "$bind" <<'PY'
import json
import sys
import time
import urllib.request

url = 'http://' + sys.argv[1] + ':8000'
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
deadline = time.monotonic() + 30
error = 'API not ready'
while time.monotonic() < deadline:
    try:
        with opener.open(url + '/api/health', timeout=2) as response:
            health = json.load(response)
        if health.get('api') == 'ok':
            print('Dashboard enabled (boot autostart on):', url)
            print('Device health:', json.dumps(health, ensure_ascii=False))
            break
        error = repr(health)
    except (OSError, ValueError) as exc:
        error = str(exc)
    time.sleep(1)
else:
    raise SystemExit('Dashboard did not become ready: ' + error)
PY
then
    journalctl -u "$service" -n 30 --no-pager >&2
    exit 1
fi
systemctl is-active --quiet "$service"
