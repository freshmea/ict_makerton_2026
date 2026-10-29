"""Bind the dashboard and its camera worker to the current Wi-Fi IPv4 address."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import sys
import time

SERVICE = '300seconds-dashboard.service'
STATE = Path('/run/300seconds-dashboard/network.json')


def select_address(interfaces, routes, wireless):
    defaults = {row['dev']: row.get('metric', 0) for row in sorted(
        routes, key=lambda row: row.get('metric', 0), reverse=True)
        if row.get('dst') == 'default' and row.get('dev') in wireless}
    candidates = []
    for interface in interfaces:
        name = interface['ifname']
        if name not in wireless or interface.get('operstate') != 'UP':
            continue
        for info in interface.get('addr_info', []):
            if info.get('family') != 'inet' or info.get('scope') != 'global':
                continue
            address = ipaddress.IPv4Address(info['local'])
            if address.is_loopback or address.is_unspecified or address.is_multicast or address.is_link_local:
                continue
            candidates.append((name not in defaults, defaults.get(name, 0),
                               name, info.get('secondary', False), str(address)))
    if not candidates:
        return None
    selected = min(candidates)
    return {'interface': selected[2], 'address': selected[4]}


def current_network():
    wireless = {path.name for path in Path('/sys/class/net').iterdir()
                if (path / 'wireless').exists() or (path / 'phy80211').exists()}
    def read(*args):
        return json.loads(subprocess.check_output(['ip', '-j', '-4', *args], text=True))
    return select_address(read('address', 'show'), read('route', 'show', 'default'), wireless)


def refresh():
    active = subprocess.check_output(
        ['systemctl', 'show', SERVICE, '--property=ActiveState', '--value'], text=True).strip()
    if active not in ('active', 'activating', 'reloading', 'failed'):
        return
    network = current_network()
    try:
        previous = json.loads(STATE.read_text())
    except (OSError, ValueError):
        previous = None
    if network == previous and active != 'failed':
        return
    subprocess.run(['systemctl', 'reset-failed', SERVICE], check=True)
    subprocess.run(['systemctl', 'restart', '--no-block', SERVICE], check=True)


def launch():
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text('null\n')
    network = current_network()
    if network is None:
        print('Waiting for a connected Wi-Fi interface with an IPv4 address.', flush=True)
    while network is None:
        time.sleep(2)
        network = current_network()
    STATE.write_text(json.dumps(network) + '\n')
    os.environ['DASHBOARD_BIND'] = network['address']
    print('Dashboard Wi-Fi: {interface} http://{address}:8000'.format(**network), flush=True)
    os.execv(sys.executable, [sys.executable, '-B', '-m', 'uvicorn', 'app:app',
                             '--host', network['address'], '--port', '8000',
                             '--workers', '1', '--no-access-log'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--print-address', action='store_true')
    mode.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    if args.print_address:
        network = current_network()
        print(network['address'] if network else '')
    elif args.refresh:
        refresh()
    else:
        launch()
