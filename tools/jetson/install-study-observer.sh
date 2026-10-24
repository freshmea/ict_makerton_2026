#!/usr/bin/env bash
# Install only the analysis worker; no camera owner or actuator is started here.
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Run with sudo bash tools/jetson/install-study-observer.sh'; exit 1; }
source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
getent group boarddash >/dev/null || { echo 'Install the dashboard first'; exit 1; }
id studyobserver >/dev/null 2>&1 || useradd --system --user-group --home-dir /nonexistent --shell /usr/sbin/nologin studyobserver
install -d -o studyobserver -g boarddash -m 0750 /var/lib/300seconds-observer
install -d -o root -g root -m 0755 /opt/300seconds/jetson /etc/300seconds
for name in jev-study-observer.py openai-study-observer.py study_window.py study_observer_service.py learning_provider.py live_education.py; do
    install -o root -g root -m 0755 "$source_dir/$name" "/opt/300seconds/jetson/$name"
done
install -d -o root -g root -m 0755 /opt/300seconds/jetson/prompts
for name in mentor-original-20261024.txt mentor-education.txt mentor-manifest.json; do
    install -o root -g root -m 0644 "$source_dir/prompts/$name" "/opt/300seconds/jetson/prompts/$name"
done
python3 - "$source_dir" <<'PY'
import importlib.util, json, os, pwd, grp
from pathlib import Path
import sys
spec=importlib.util.spec_from_file_location('observer',Path(sys.argv[1])/'jev-study-observer.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
keys={}
for path in ['/etc/300seconds/ai.env','/etc/300seconds/jev-observer.env']:
    values=module.load_config(Path(path))
    for key in ['OPENAI_API_KEY','OPENCODE_API_KEY']:
        if values.get(key): keys[key]=values[key]
for value in keys.values():
    if not value.isascii() or any(c.isspace() for c in value): raise SystemExit('Invalid API key format; values not printed')
target=Path('/etc/300seconds/study-observer.env')
temporary=target.with_suffix('.env.new')
if temporary.exists(): raise SystemExit('Temporary credential file exists; inspect it before continuing')
fd=os.open(str(temporary),os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as stream:
    for name in ['OPENAI_API_KEY','OPENCODE_API_KEY']:
        stream.write(name+'='+json.dumps(keys.get(name,''))+'\n')
os.replace(str(temporary),str(target))
state=Path('/var/lib/300seconds-observer')
uid=pwd.getpwnam('studyobserver').pw_uid;gid=grp.getgrnam('boarddash').gr_gid
budget=state/'openai-budget.json';old=Path('/var/lib/300seconds/openai-observer-budget.json')
migrated=False
if not budget.exists() and old.exists():
    data=json.loads(old.read_text())
    if not isinstance(data.get('attempts'),list):raise SystemExit('Old budget invalid; refusing to reset')
    module.save_result(budget,data);migrated=True
quota=state/'provider-state.json'
if not quota.exists():
    module.save_result(quota,{'jev_blocked_until':float(os.environ.get('OBSERVER_INITIAL_JEV_COOLDOWN','0'))})
for path in [budget,quota]:
    if path.exists():os.chown(str(path),uid,gid);os.chmod(str(path),0o600)
print(json.dumps({'credentials_configured':{k:bool(keys.get(k)) for k in ['OPENAI_API_KEY','OPENCODE_API_KEY']},'old_budget_preserved':True,'budget_migrated':migrated}))
PY
install -o root -g root -m 0644 "$source_dir/300seconds-observer.service" /etc/systemd/system/300seconds-observer.service
systemctl daemon-reload
systemctl enable 300seconds-observer.service
systemctl restart 300seconds-observer.service
systemctl --no-pager --full status 300seconds-observer.service
