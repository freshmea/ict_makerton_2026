#!/usr/bin/env python3
"""Reversible Wi-Fi power policy and bounded persistent diagnostics for this Nano.

Never reloads the Wi-Fi driver or restarts NetworkManager over SSH.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

STATE = Path('/var/lib/300seconds/dashboard-network/baseline.json')
MODULE = Path('/etc/modprobe.d/99-300seconds-dashboard-wifi.conf')
JOURNAL = Path('/etc/systemd/journald.conf.d/99-300seconds-dashboard.conf')


def command(*args):
    return subprocess.check_output(args, universal_newlines=True, stderr=subprocess.STDOUT).strip()


def profile():
    for row in command('nmcli', '-t', '-f', 'UUID,DEVICE', 'connection', 'show', '--active').splitlines():
        uuid, device = row.split(':', 1)
        if device == 'wlan0': return uuid
    raise RuntimeError('No active wlan0 profile; no network settings were changed.')


def previous_file(path):
    return {'hex': path.read_bytes().hex(), 'mode': path.stat().st_mode & 0o777} if path.exists() else None


def write_file(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data)
    path.chmod(0o644)


def restore_file(path, saved):
    if saved is None:
        if path.exists(): path.unlink()
    else:
        path.write_bytes(bytes.fromhex(saved['hex']))
        path.chmod(saved['mode'])


def status():
    values = {}
    for name in ('rtw_power_mgnt', 'rtw_ips_mode', 'rtw_enusbss'):
        path = Path('/sys/module/r8188eu/parameters') / name
        values[name] = path.read_text().strip() if path.exists() else None
    wifi = Path('/sys/class/net/wlan0/device').resolve().parent
    power = wifi / 'power/control'
    values['usb_power_control'] = power.read_text().strip() if power.exists() else None
    try:
        uuid = profile()
        values['networkmanager_powersave'] = command('nmcli', '-g', '802-11-wireless.powersave', 'connection', 'show', uuid)
    except (RuntimeError, subprocess.CalledProcessError) as error: values['network_error'] = str(error)
    values.update({'driver_config': MODULE.read_text() if MODULE.exists() else None,
                   'journal_config': JOURNAL.read_text() if JOURNAL.exists() else None,
                   'uptime_seconds': float(Path('/proc/uptime').read_text().split()[0]),
                   'timestamp_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())})
    return values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['status', 'apply', 'restore'])
    action = parser.parse_args().action
    if action != 'status' and os.geteuid() != 0: parser.error('Use sudo for apply/restore.')
    if action == 'apply':
        usb = Path('/sys/class/net/wlan0/device').resolve().parent
        if not (usb / 'idVendor').exists() or (usb / 'idVendor').read_text().strip() != '0bda' or (usb / 'idProduct').read_text().strip() != '8179':
            raise RuntimeError('Expected RTL8188EUS USB 0bda:8179 on wlan0; refusing to modify another adapter.')
        uuid = profile()
        if not STATE.exists():
            baseline = {'uuid': uuid, 'powersave': command('nmcli', '-g', '802-11-wireless.powersave', 'connection', 'show', uuid).split()[0],
                        'module': previous_file(MODULE), 'journal': previous_file(JOURNAL)}
            STATE.parent.mkdir(parents=True, exist_ok=True)
            STATE.write_text(json.dumps(baseline, indent=2)); STATE.chmod(0o600)
        command('nmcli', 'connection', 'modify', 'uuid', uuid, '802-11-wireless.powersave', '2')
        supported = [name for name in ('rtw_power_mgnt', 'rtw_ips_mode', 'rtw_enusbss') if (Path('/sys/module/r8188eu/parameters') / name).exists()]
        write_file(MODULE, '# Applies on next driver load; no live module reload over SSH.\noptions r8188eu ' + ' '.join(name + '=0' for name in supported) + '\n')
        write_file(JOURNAL, '[Journal]\nStorage=persistent\nSystemMaxUse=16M\nSystemMaxFileSize=4M\nRuntimeMaxUse=8M\nMaxRetentionSec=2day\nSyncIntervalSec=30s\nRateLimitIntervalSec=30s\nRateLimitBurst=200\n')
        Path('/var/log/journal').mkdir(exist_ok=True)
        command('systemd-tmpfiles', '--create', '--prefix', '/var/log/journal')
        command('systemctl', 'restart', 'systemd-journald')
        command('journalctl', '--flush')
    elif action == 'restore':
        saved = json.loads(STATE.read_text())
        command('nmcli', 'connection', 'modify', 'uuid', saved['uuid'], '802-11-wireless.powersave', saved['powersave'])
        restore_file(MODULE, saved['module'])
        if saved['journal'] is None:
            # Keep collected files for diagnosis, but stop persistent writes.
            write_file(JOURNAL, '# Restored volatile logging; previous diagnostic files are retained.\n[Journal]\nStorage=volatile\nRuntimeMaxUse=8M\n')
        else:
            restore_file(JOURNAL, saved['journal'])
        command('systemctl', 'restart', 'systemd-journald')
    print(json.dumps(status(), ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
