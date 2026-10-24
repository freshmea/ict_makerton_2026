#!/usr/bin/env bash
# Run on the Nano: bash enable-dashboard.sh [local IPv4 address]
set -Eeuo pipefail

if [[ ${1:-} == -h || ${1:-} == --help ]]; then
    echo 'Usage: bash enable-dashboard.sh [local IPv4 address]'
    echo 'Update the LAN address, enable boot autostart, and restart the dashboard.'
    exit 0
fi
if (( $# > 1 )); then
    echo 'Usage: bash enable-dashboard.sh [local IPv4 address]' >&2
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

# Route lookup reads the local routing table; it does not send internet traffic.
bind=${1:-$(ip -4 route get 1.1.1.1 | awk '{for (i=1; i<=NF; i++) if ($i == "src") {print $(i+1); exit}}')}
if [[ -z $bind ]]; then
    echo 'No LAN IPv4 address found. Run: bash enable-dashboard.sh <Nano IPv4 address>' >&2
    exit 1
fi

python3 - "$env_file" "$bind" <<'PY'
from datetime import datetime, timezone
import ipaddress
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile

path = Path(sys.argv[1])
address = ipaddress.IPv4Address(sys.argv[2])
assigned = re.findall(r'\binet ([0-9.]+)/', subprocess.check_output(['ip', '-4', '-o', 'address', 'show'], text=True))
if address.is_loopback or address.is_unspecified or address.is_multicast or str(address) not in assigned:
    raise SystemExit('Choose a non-loopback IPv4 address assigned to this Nano.')

original = path.read_text(encoding='utf-8')
pattern = r'^DASHBOARD_BIND=[^\r\n]*'
matches = re.findall(pattern, original, flags=re.M)
if len(matches) > 1:
    raise SystemExit('Multiple DASHBOARD_BIND settings found; fix the environment file first.')
setting = 'DASHBOARD_BIND=' + str(address)
updated = re.sub(pattern, setting, original, flags=re.M) if matches else original.rstrip('\n') + '\n' + setting + '\n'
if updated != original:
    backup = path.with_name(path.name + '.bak-network-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    shutil.copy2(path, backup)
    metadata = path.stat()
    fd, temporary = tempfile.mkstemp(prefix='.dashboard.env.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            os.fchown(output.fileno(), metadata.st_uid, metadata.st_gid)
            os.fchmod(output.fileno(), stat.S_IMODE(metadata.st_mode))
            output.write(updated)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print('Previous configuration saved:', backup)
print('Dashboard address:', address)
PY

systemctl enable "$service"
if ! systemctl restart "$service"; then
    journalctl -u "$service" -n 30 --no-pager >&2
    exit 1
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
