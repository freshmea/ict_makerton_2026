#!/usr/bin/env python3
"""Disable this board's unused ROS sources/key/cron/service without uninstalling.

ROS stays disabled across both GUI modes. Restore is a separate explicit action.
"""
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import sys
import time

from jetson_mode import file_snapshot, restore_file, run, save_json, unit_info, now

STATE = Path('/var/lib/300seconds/ros-disabled')
BASELINE = STATE / 'baseline.json'
FLAG = STATE / 'disabled'
KEY = Path('/usr/share/keyrings/ros-archive-keyring.gpg')
KEY_FPR = 'C1CF6E31E6BADE8868B172B4F42ED6FBAB17C654'
DROPIN = Path('/etc/systemd/system/ros_init.service.d/90-300seconds-no-ros.conf')
ROS_LINE = re.compile(r'packages\.ros\.org|repo\.ros2\.org|/opt/ros/|\bros2\s+(launch|run|daemon)\b|\bros(core|launch|master)\b|colcon_ws/.*/(?:local_)?setup\.')


def comment_ros(text):
    return ''.join('# 300seconds ROS disabled: ' + line
                   if line.strip() and not line.lstrip().startswith('#') and ROS_LINE.search(line)
                   else line for line in text.splitlines(keepends=True))


def ros_pids():
    found = []
    for path in Path('/proc').iterdir():
        if not path.name.isdigit() or int(path.name) == os.getpid():
            continue
        try:
            argv = (path / 'cmdline').read_bytes().replace(b'\x00', b' ').decode('utf-8', 'replace')
            exe = str((path / 'exe').resolve())
            if exe.startswith(('/opt/ros/', '/home/jetson/colcon_ws/install/')) or (
                not any(x in argv for x in ('sudo ', 'bash -c ', 'sshd:', 'ros_control.py')) and
                ('/opt/ros/' in argv or '_ros2_daemon' in argv or
                 re.search(r'(^|[/ ])ros(core|master|launch)( |$)', argv) or
                 'ros2 launch digitalphoto digitalphoto.launch.py' in argv)
            ):
                found.append({'pid': int(path.name), 'command': argv.strip()})
        except (OSError, ValueError):
            pass
    return found


def snapshot():
    paths = [DROPIN, KEY]
    paths += sorted(Path('/etc/apt/sources.list.d').glob('*.list'))
    paths += [Path('/etc/apt/sources.list'), Path('/home/jetson/.bashrc'), Path('/home/jetson/.profile')]
    # Retain only files that will be edited, plus the named key/override.
    paths = [p for p in paths if p in (DROPIN, KEY) or (p.is_file() and comment_ros(p.read_text()) != p.read_text())]
    crons = {}
    for user in ('root', 'jetson'):
        p = run('crontab', '-u', user, '-l', check=False)
        if p.returncode == 0 and comment_ros(p.stdout) != p.stdout:
            crons[user] = p.stdout
    data = {'created_at_utc': now(), 'files': [file_snapshot(p) for p in paths],
            'crontabs': crons, 'unit': unit_info('ros_init.service')}
    save_json(BASELINE, data)
    return data


def set_cron(user, text):
    import subprocess
    p = subprocess.run(['crontab', '-u', user, '-'], input=text,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    if p.returncode:
        raise RuntimeError('crontab update failed: ' + p.stdout)


def disable(data):
    FLAG.write_text(now() + '\n')
    for user in data['crontabs']:
        current = run('crontab', '-u', user, '-l', check=False)
        if current.returncode:
            raise RuntimeError('Cannot read current crontab for: ' + user)
        set_cron(user, comment_ros(current.stdout))
        print('Disabled ROS cron entries for:', user, flush=True)
    for item in data['files']:
        path = Path(item['path'])
        if path not in (DROPIN, KEY) and path.is_file():
            path.write_text(comment_ros(path.read_text()))
            print('Disabled ROS lines:', path, flush=True)
    if KEY.exists():
        key_info = run('gpg', '--batch', '--show-keys', '--with-colons', str(KEY)).stdout
        primary_fprs = [line.split(':')[9] for line in key_info.splitlines() if line.startswith('fpr:')]
        if primary_fprs != [KEY_FPR] or not any(line.startswith('pub:e:') for line in key_info.splitlines()):
            raise RuntimeError('Unexpected ROS key contents; refusing to remove a shared/non-expired key.')
        KEY.unlink()  # Full public-key bytes and permissions are retained in baseline.json.
        print('Expired ROS signing key removed from active path:', KEY_FPR, flush=True)
    if data['unit'].get('LoadState') == 'loaded':
        DROPIN.parent.mkdir(parents=True, exist_ok=True)
        DROPIN.write_text('[Unit]\nConditionPathExists=!{}\n'.format(FLAG))
        if data['unit'].get('UnitFileState') == 'enabled':
            run('systemctl', 'disable', 'ros_init.service')
        run('systemctl', 'daemon-reload')
        run('systemctl', 'stop', 'ros_init.service')
    stopped = ros_pids()
    for process in stopped:
        try:
            os.kill(process['pid'], signal.SIGTERM)
        except ProcessLookupError:
            pass
    if stopped:
        time.sleep(2)
    remaining = ros_pids()
    save_json(STATE / 'last-result.json', {'disabled_at_utc': now(), 'terminated': stopped, 'remaining': remaining})
    if remaining:
        raise RuntimeError('Some ROS processes remain: ' + json.dumps(remaining))
    print('ROS sources/key/cron/service disabled; zero matching ROS processes.')


def restore(data):
    # Avoid overwriting user edits made since disablement.
    import base64
    for item in data['files']:
        path = Path(item['path'])
        if path == KEY:
            if path.exists() and path.read_bytes() != base64.b64decode(item['data']):
                raise RuntimeError('ROS key changed since disablement; refusing to overwrite it.')
            continue
        if path == DROPIN:
            continue
        original = base64.b64decode(item['data']).decode('utf-8')
        if path.read_text() not in (original, comment_ros(original)):
            raise RuntimeError('File changed since ROS disablement; restore manually: ' + str(path))
    for user, text in data['crontabs'].items():
        current = run('crontab', '-u', user, '-l', check=False).stdout
        if current not in (text, comment_ros(text)):
            raise RuntimeError('Crontab changed since ROS disablement; restore manually: ' + user)
    for item in data['files']:
        restore_file(item)
    for user, text in data['crontabs'].items():
        set_cron(user, text)
    if FLAG.exists():
        FLAG.unlink()
    run('systemctl', 'daemon-reload')
    if data['unit'].get('UnitFileState') == 'enabled':
        run('systemctl', 'enable', 'ros_init.service')
    if data['unit'].get('ActiveState') == 'active':
        run('systemctl', 'start', 'ros_init.service')
    print('ROS baseline restored, including the OLD EXPIRED key and original cron. Refresh its key before apt use.')


def main():
    if os.geteuid() != 0 or len(sys.argv) != 2 or sys.argv[1] not in ('disable', 'restore'):
        raise SystemExit('Use sudo disable-ros.sh or sudo restore-ros.sh')
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    STATE.chmod(0o700)
    with (STATE / 'lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if BASELINE.exists():
            data = json.loads(BASELINE.read_text())
        elif sys.argv[1] == 'disable':
            data = snapshot()
        else:
            raise SystemExit('No ROS baseline exists.')
        if sys.argv[1] == 'disable':
            disable(data)
        else:
            restore(data)


if __name__ == '__main__':
    main()
