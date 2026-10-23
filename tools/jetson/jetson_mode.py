#!/usr/bin/env python3
"""Reversible, board-local project/desktop policy; invoked by the shell wrappers.

The first baseline is retained. Only policy-owned overrides and the symlinks of
selected units are restored; unrelated systemd configuration is never replaced.
"""
import base64
import datetime
import fcntl
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

STATE = Path('/var/lib/300seconds/jetson-mode')
BASELINE = STATE / 'baseline.json'
FLAG = STATE / 'project.enabled'
OVERRIDE = '90-300seconds-project.conf'
MODULE_POLICY = Path('/etc/modprobe.d/90-300seconds-project.conf')
PRINTER_LOAD = Path('/etc/modules-load.d/cups-filters.conf')
PACKAGEKIT_HOOK = Path('/etc/apt/apt.conf.d/20packagekit')
COMMON_UNITS = [
    'cups.socket', 'cups.path', 'avahi-daemon.socket', 'gpsd.socket',
    'cups-browsed.service', 'cups.service', 'avahi-daemon.service',
    'bluetooth.service', 'blueman-mechanism.service', 'ModemManager.service',
    'gpsd.service', 'colord.service', 'packagekit.service',
    'whoopsie.service', 'kerneloops.service', 'teamviewerd.service',
    'switcheroo-control.service', 'geoclue.service',
    'spice-vdagent.service', 'spice-vdagentd.service',
    'nvweston.service', 'nvmemwarning.service',
]
DOCKER_UNITS = ['docker.socket', 'docker.service', 'containerd.service']
SNAP_UNITS = ['snapd.socket', 'snapd.snap-repair.timer',
              'snapd.snap-repair.service', 'snapd.service']


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def run(*args, check=True, timeout=45):
    p = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       universal_newlines=True, timeout=timeout)
    if check and p.returncode:
        raise RuntimeError('{}: {}'.format(' '.join(args), p.stdout.strip()))
    return p


def unit_info(name):
    output = run('systemctl', 'show', name, '--no-pager',
                 '-p', 'Id', '-p', 'LoadState', '-p', 'ActiveState',
                 '-p', 'UnitFileState', '-p', 'FragmentPath', check=False).stdout
    return dict(line.split('=', 1) for line in output.splitlines() if '=' in line)


def save_json(path, data):
    temporary = path.with_suffix('.tmp')
    with temporary.open('w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    temporary.replace(path)


def file_snapshot(path):
    if path.is_symlink():
        return {'path': str(path), 'kind': 'link', 'target': os.readlink(path)}
    if path.exists():
        s = path.stat()
        if not stat.S_ISREG(s.st_mode):
            raise RuntimeError('Refusing non-regular config: ' + str(path))
        return {'path': str(path), 'kind': 'file', 'mode': stat.S_IMODE(s.st_mode),
                'uid': s.st_uid, 'gid': s.st_gid,
                'data': base64.b64encode(path.read_bytes()).decode('ascii')}
    return {'path': str(path), 'kind': 'absent'}


def restore_file(item):
    path = Path(item['path'])
    if item['kind'] == 'absent':
        if path.exists() or path.is_symlink():
            path.unlink()
    elif item['kind'] == 'link':
        if path.is_symlink() and os.readlink(path) == item['target']:
            return
        if path.exists() or path.is_symlink():
            path.unlink()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(item['target'])
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + '.300seconds-tmp')
        temporary.write_bytes(base64.b64decode(item['data']))
        os.chown(str(temporary), item['uid'], item['gid'])
        temporary.chmod(item['mode'])
        temporary.replace(path)


def selected_links(units):
    fragments = {str(Path(u['FragmentPath']).resolve()) for u in units}
    links = []
    for root in ('/etc/systemd/system', '/run/systemd/system'):
        for directory, subdirs, files in os.walk(root, followlinks=False):
            for name in subdirs + files:
                path = Path(directory) / name
                if path.is_symlink() and str(path.resolve()) in fragments:
                    links.append({'path': str(path), 'target': os.readlink(path)})
    return sorted(links, key=lambda x: x['path'])


def make_baseline():
    names = list(COMMON_UNITS)
    decisions = []
    # A running container workload blocks the entire Docker/containerd group.
    if unit_info('docker.service').get('ActiveState') == 'active':
        docker = run('docker', 'ps', '-aq', check=False)
        if docker.returncode == 0 and not docker.stdout.strip():
            names += DOCKER_UNITS
            decisions.append('Docker selected: zero existing containers.')
        else:
            decisions.append('Docker preserved: containers exist or inventory failed.')
    else:
        names += DOCKER_UNITS
    snap = run('snap', 'services', check=False) if Path('/usr/bin/snap').exists() else None
    if snap is None or (snap.returncode == 0 and
                        ('There are no services' in snap.stdout or not snap.stdout.strip())):
        names += SNAP_UNITS
        decisions.append('Snap selected: no installed snap services.')
    else:
        decisions.append('Snap preserved: service inventory is non-empty or failed.')
    display = Path('/etc/systemd/system/display-manager.service')
    if display.is_symlink():
        names.append(display.resolve().name)
    units, seen = [], set()
    for name in names:
        info = unit_info(name)
        if info.get('LoadState') != 'loaded' or info['Id'] in seen:
            continue
        seen.add(info['Id'])
        units.append(info)
    configs = [MODULE_POLICY, PRINTER_LOAD, PACKAGEKIT_HOOK]
    configs += [Path('/etc/systemd/system') / (u['Id'] + '.d') / OVERRIDE for u in units]
    snapshot = {
        'schema_version': 1, 'created_at_utc': now(),
        'hostname': run('hostname').stdout.strip(),
        'kernel': run('uname', '-r').stdout.strip(),
        'default_target': run('systemctl', 'get-default').stdout.strip(),
        'units': units, 'links': selected_links(units),
        'files': [file_snapshot(p) for p in configs],
        'bnep_loaded': Path('/sys/module/bnep').exists(),
        'decisions': decisions,
        'memory_before': run('free', '-b').stdout,
    }
    save_json(BASELINE, snapshot)
    return snapshot


def check_new_workloads(snapshot):
    ids = {u['Id'] for u in snapshot['units']}
    if 'docker.service' in ids and unit_info('docker.service').get('ActiveState') == 'active':
        p = run('docker', 'ps', '-aq', check=False)
        if p.returncode or p.stdout.strip():
            raise RuntimeError('Docker containers now exist: refusing to stop their runtime.')
    if 'snapd.service' in ids and Path('/usr/bin/snap').exists():
        p = run('snap', 'services', check=False)
        if p.returncode or (p.stdout.strip() and 'There are no services' not in p.stdout):
            raise RuntimeError('Snap services now exist or inventory failed; refusing to stop Snap.')


def restore(snapshot):
    errors = []
    # Restore only these named files, never the complete systemd directory.
    for item in snapshot['files']:
        restore_file(item)
    if FLAG.exists():
        FLAG.unlink()
    for link in snapshot['links']:
        path = Path(link['path'])
        if path.is_symlink() and os.readlink(path) == link['target']:
            continue
        if path.exists() or path.is_symlink():
            raise RuntimeError('Conflicting systemd link; retained: ' + str(path))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(link['target'])
    run('systemctl', 'daemon-reload')
    run('systemctl', 'set-default', snapshot['default_target'])
    if snapshot['bnep_loaded'] and not Path('/sys/module/bnep').exists():
        p = run('modprobe', 'bnep', check=False)
        if p.returncode:
            errors.append('bnep restore: ' + p.stdout)
    # Restore active services before the display manager, sockets first.
    display_name = Path('/etc/systemd/system/display-manager.service').resolve().name
    active = [u['Id'] for u in snapshot['units'] if u['ActiveState'] == 'active']
    active.sort(key=lambda name: (name == display_name, not name.endswith(('.socket', '.timer'))))
    for name in active:
        p = run('systemctl', 'start', name, check=False, timeout=90)
        if p.returncode:
            errors.append(name + ': ' + p.stdout)
    if errors:
        save_json(STATE / 'last-result.json', {'mode': 'restore-incomplete', 'at_utc': now(), 'errors': errors})
        raise RuntimeError('\n'.join(errors))
    save_json(STATE / 'last-result.json', {'mode': 'desktop', 'at_utc': now(), 'errors': []})
    print('Desktop baseline restored; GUI applications/logged-in sessions are not recreated.')


def project(snapshot):
    if FLAG.exists():
        print('Project mode already active; baseline unchanged.')
        return
    check_new_workloads(snapshot)
    FLAG.write_text(now() + '\n', encoding='ascii')
    for unit in snapshot['units']:
        dropin = Path('/etc/systemd/system') / (unit['Id'] + '.d') / OVERRIDE
        dropin.parent.mkdir(parents=True, exist_ok=True)
        dropin.write_text('[Unit]\nConditionPathExists=!{}\n'.format(FLAG), encoding='ascii')
    MODULE_POLICY.write_text(
        '# 300seconds project mode: unused Bluetooth PAN only.\n'
        'blacklist bnep\ninstall bnep /bin/false\n', encoding='ascii')
    if PRINTER_LOAD.exists():
        PRINTER_LOAD.write_text('# Printer module auto-load paused by 300seconds project mode.\n', encoding='ascii')
    if PACKAGEKIT_HOOK.exists():
        PACKAGEKIT_HOOK.write_text('// PackageKit APT notifications paused by 300seconds project mode.\n', encoding='ascii')
    run('systemctl', 'daemon-reload')
    # Socket/timer activation must stop before its corresponding daemon.
    units = sorted(snapshot['units'], key=lambda u: not u['Id'].endswith(('.socket', '.timer', '.path')))
    for unit in units:
        name, original = unit['Id'], unit.get('UnitFileState', '')
        if original in ('enabled', 'enabled-runtime', 'linked', 'linked-runtime'):
            args = ['systemctl', 'disable']
            if original.endswith('-runtime'):
                args.append('--runtime')
            run(*(args + [name]))
        run('systemctl', 'stop', name)
        print('Stopped/guarded:', name, flush=True)
    unload = run('modprobe', '-r', 'bnep', check=False)
    run('systemctl', 'set-default', 'multi-user.target')
    for name in ('ssh.service', 'NetworkManager.service', 'automagic-fan.service', 'nvargus-daemon.service'):
        if unit_info(name).get('ActiveState') != 'active':
            raise RuntimeError('Required service lost: ' + name)
    if not Path('/sys/module/nvgpu').exists():
        raise RuntimeError('GPU kernel module is missing.')
    result = {'mode': 'project', 'at_utc': now(), 'bnep_loaded': Path('/sys/module/bnep').exists(),
              'bnep_unload_exit': unload.returncode, 'bnep_unload_output': unload.stdout,
              'memory_after': run('free', '-b').stdout}
    save_json(STATE / 'last-result.json', result)
    print(json.dumps(result, indent=2))


def status(snapshot):
    data = {'project_flag': FLAG.exists(), 'default_target': run('systemctl', 'get-default').stdout.strip(),
            'bnep_loaded': Path('/sys/module/bnep').exists(), 'memory': run('free', '-b').stdout,
            'baseline': str(BASELINE), 'decisions': snapshot.get('decisions', []),
            'units': [unit_info(u['Id']) for u in snapshot.get('units', [])]}
    print(json.dumps(data, indent=2))


def main():
    if os.geteuid() != 0:
        raise SystemExit('Run the shell wrapper with sudo.')
    if len(sys.argv) != 2 or sys.argv[1] not in ('project', 'desktop', 'status'):
        raise SystemExit('Usage: jetson-mode.sh {project|desktop|status}')
    if not Path('/etc/nv_tegra_release').exists():
        raise SystemExit('Expected a Jetson board.')
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    STATE.chmod(0o700)
    with (STATE / 'lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        command = sys.argv[1]
        if BASELINE.exists():
            snapshot = json.loads(BASELINE.read_text(encoding='utf-8'))
            # Upgrade an earlier baseline before this policy started managing
            # PackageKit's notification hook. Other captured values stay intact.
            if str(PACKAGEKIT_HOOK) not in {f['path'] for f in snapshot['files']}:
                snapshot['files'].append(file_snapshot(PACKAGEKIT_HOOK))
                save_json(BASELINE, snapshot)
        elif command == 'project':
            snapshot = make_baseline()
        elif command == 'status':
            status({})
            return
        else:
            raise SystemExit('No baseline exists. Nothing has been changed by this tool.')
        if command == 'project':
            try:
                project(snapshot)
            except Exception:
                if FLAG.exists():
                    print('Apply failed; restoring the baseline.', file=sys.stderr)
                    restore(snapshot)
                raise
        elif command == 'desktop':
            restore(snapshot)
        else:
            status(snapshot)


if __name__ == '__main__':
    main()
