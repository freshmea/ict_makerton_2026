import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import wifi_network as wifi


def interface(name, address, state='UP'):
    return {'ifname': name, 'operstate': state, 'addr_info': [
        {'family': 'inet', 'scope': 'global', 'local': address}]}


class WifiNetworkTests(unittest.TestCase):
    def test_wifi_selected_over_ethernet_and_old_ip(self):
        rows = [interface('eth0', '10.0.0.2'), interface('wlan0', '192.168.219.127')]
        self.assertEqual(wifi.select_address(rows, [], {'wlan0'}),
                         {'interface': 'wlan0', 'address': '192.168.219.127'})
        rows[1] = interface('wlan0', '192.168.184.22')
        self.assertEqual(wifi.select_address(rows, [], {'wlan0'})['address'], '192.168.184.22')

    def test_missing_down_or_link_local_wifi_waits(self):
        for rows in ([], [interface('wlan0', '10.0.0.2', 'DOWN')],
                     [interface('wlan0', '169.254.1.2')], [interface('eth0', '10.0.0.2')]):
            self.assertIsNone(wifi.select_address(rows, [], {'wlan0'}))

    def test_wifi_default_route_metric_wins(self):
        rows = [interface('wlan0', '10.0.0.2'), interface('wlan1', '10.1.0.2')]
        routes = [{'dst': 'default', 'dev': 'wlan0', 'metric': 600},
                  {'dst': 'default', 'dev': 'wlan1', 'metric': 100}]
        self.assertEqual(wifi.select_address(rows, routes, {'wlan0', 'wlan1'})['interface'], 'wlan1')

    def test_network_events_restart_only_when_needed(self):
        old = {'interface': 'wlan0', 'address': '10.0.0.2'}
        new = {'interface': 'wlan0', 'address': '10.1.0.2'}
        for active, current, expected in [('active', old, 0), ('active', new, 2),
                                          ('active', None, 2), ('inactive', new, 0),
                                          ('failed', old, 2)]:
            with self.subTest(active=active, current=current), tempfile.TemporaryDirectory() as folder:
                state = Path(folder) / 'network.json'
                state.write_text(json.dumps(old))
                with patch.object(wifi, 'STATE', state), patch.object(wifi, 'current_network', return_value=current), \
                     patch.object(wifi.subprocess, 'check_output', return_value=active), \
                     patch.object(wifi.subprocess, 'run') as run:
                    wifi.refresh()
                    self.assertEqual(run.call_count, expected)
                    if expected:
                        self.assertEqual(run.call_args.args[0],
                                         ['systemctl', 'restart', '--no-block', wifi.SERVICE])

    def test_start_waits_for_wifi_and_replaces_stale_bind(self):
        network = {'interface': 'wlan0', 'address': '10.1.0.2'}
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / 'network.json'
            with patch.object(wifi, 'STATE', state), \
                 patch.object(wifi, 'current_network', side_effect=[None, network]), \
                 patch.object(wifi.time, 'sleep'), patch.object(wifi.os, 'execv') as execute, \
                 patch.dict(wifi.os.environ, {'DASHBOARD_BIND': '192.168.184.76'}):
                wifi.launch()
                self.assertEqual(wifi.os.environ['DASHBOARD_BIND'], '10.1.0.2')
                self.assertIn('10.1.0.2', execute.call_args.args[1])
                self.assertEqual(json.loads(state.read_text()), network)


if __name__ == '__main__':
    unittest.main()
