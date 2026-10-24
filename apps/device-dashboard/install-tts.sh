#!/usr/bin/env bash
# Synthesis service only; no playback, camera, Pico or runtime target starts.
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run with sudo bash apps/device-dashboard/install-tts.sh'; exit 1; }
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
test -x /opt/300seconds/runtime/nano-runtime
test -f /opt/300seconds/dashboard/app/tts_worker.py
python3 - <<'PY'
import json, os, pwd, shlex, tempfile
from pathlib import Path
values = {}
for source in ['/etc/300seconds/runtime.env', '/etc/300seconds/ai.env']:
    if not Path(source).exists(): continue
    for line in Path(source).read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('#') or '=' not in line: continue
        key, value = line.split('=', 1)
        if key in ('TYPECAST_API_KEY', 'NANO_ALLOW_CLOUD') or key.startswith(('NANO_TYPECAST_', 'NANO_TTS_')):
            parts = shlex.split(value)
            values[key] = parts[0] if parts else ''
if not values.get('TYPECAST_API_KEY'): raise SystemExit('TYPECAST_API_KEY missing; value not printed')
# Share the existing runtime character ledger; never reset or bypass budgets.
ledger = Path('/var/lib/300seconds-runtime/tts-usage.json')
if values.get('NANO_TTS_USAGE_FILE', str(ledger)) != str(ledger):
    raise SystemExit('Custom TTS ledger path requires matching service ReadWritePaths')
account = pwd.getpwnam('boarddash')
ledger.parent.mkdir(mode=0o750, exist_ok=True)
os.chown(str(ledger.parent), account.pw_uid, account.pw_gid)
if not ledger.exists():
    fd = os.open(str(ledger), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    os.chown(str(ledger), account.pw_uid, account.pw_gid)
target = Path('/etc/300seconds/tts.env')
fd, name = tempfile.mkstemp(prefix='tts-env-', dir=str(target.parent))
try:
    with os.fdopen(fd, 'w') as stream:
        for key, value in sorted(values.items()): stream.write(key + '=' + json.dumps(value) + '\n')
    os.replace(name, str(target))
finally:
    if os.path.exists(name): os.unlink(name)
print(json.dumps({'typecast_configured': True, 'shared_ledger': str(ledger), 'dashboard_receives_keys': False}))
PY
install -m 0644 "$source_dir/300seconds-tts.service" /etc/systemd/system/300seconds-tts.service
systemctl daemon-reload
systemctl enable --now 300seconds-tts.service
systemctl restart 300seconds-tts.service
