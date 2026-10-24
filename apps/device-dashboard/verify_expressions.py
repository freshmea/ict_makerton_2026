"""Read the catalog, or explicitly exercise all presets via the existing HTTP API."""
import argparse
import json
from pathlib import Path
import time
import urllib.error
import urllib.request


def verify(host, run=False, matrix_only=False):
    base = host.rstrip('/')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    token = None

    def request(path, body=None):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['X-CSRF-Token'] = token
        req = urllib.request.Request(base+path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
        try:
            with opener.open(req, timeout=8) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            raise RuntimeError('HTTP {}: {}'.format(error.code, error.read().decode(errors='replace')))

    catalog = request('/api/pico/expressions')
    assert catalog['count'] == len(catalog['presets']) == 50
    record = {'catalog_count': catalog['count'], 'presets': [], 'errors': [], 'run_requested': run,
              'matrix_only': matrix_only, 'other_fault_bits_observed': []}
    if not run:
        return record
    token = request('/api/session')['csrf_token']
    initial = request('/api/status')
    last_applied = (initial['pico'].get('last_applied') or {}).get('request_seq', -1)
    try:
        request('/api/pico/command', {'cmd': 'stop'})
        for index, item in enumerate(catalog['presets']):
            result = request('/api/pico/expression', {'preset_id': item['id'], 'seconds': 3})
            assert result['ok'] and result['ack_code'] == 'Ok'
            deadline = time.monotonic()+2
            confirmed = False
            while time.monotonic() < deadline:
                state = request('/api/status')
                pico, expression = state['pico'], state['eye_expression']
                event = pico.get('last_applied') or {}
                if event.get('kind') == 3 and event.get('request_seq', -1) > last_applied and expression['preset_id'] == item['id']:
                    last_applied = event['request_seq']
                    confirmed = True
                    break
                time.sleep(.04)
            assert confirmed, 'No new Applied event for '+item['id']
            faults = pico['device']['faults']
            assert (faults & ~1 == 0 if matrix_only else faults == 0) and pico['device']['oe_high'] is True
            if faults and faults not in record['other_fault_bits_observed']:
                record['other_fault_bits_observed'].append(faults)
            record['presets'].append({'id': item['id'], 'name': item['name'], 'ack': 'Ok',
                                      'applied_seq': last_applied, 'faults': faults, 'oe_high': True})
            print(json.dumps({'preset': index+1, 'id': item['id'], 'applied_seq': last_applied}), flush=True)
            time.sleep(.08)
        request('/api/pico/command', {'cmd': 'stop'})
        request('/api/pico/expression', {'preset_id': 'love', 'seconds': 3})
        frames = set()
        start = time.monotonic()
        while time.monotonic()-start < 6:
            state = request('/api/status')
            expression = state['eye_expression']
            if expression['active']:
                frames.add(expression['frame_index'])
            elif expression.get('last') and expression['last'].get('result') == 'completed' and state['pico'].get('outputs', {}).get('armed') is False:
                break
            time.sleep(.1)
        record['auto_off'] = {'state': expression, 'frames_seen': sorted(frames), 'pico': state['pico']}
        assert not expression['active'] and expression['last']['result'] == 'completed' and len(frames) >= 2
        assert state['pico']['outputs']['armed'] is False and state['pico']['device']['oe_high'] is True
        request('/api/pico/expression', {'preset_id': 'dizzy', 'seconds': 10})
        time.sleep(.75)
        record['stop'] = request('/api/pico/command', {'cmd': 'stop'})
        deadline = time.monotonic()+2
        while time.monotonic() < deadline:
            after = request('/api/status')
            if not after['eye_expression']['active'] and (after['pico'].get('outputs') or {}).get('armed') is False:
                break
            time.sleep(.05)
        sequence = (after['pico'].get('last_applied') or {}).get('request_seq')
        time.sleep(.9)
        final = request('/api/status')
        assert not final['eye_expression']['active'] and final['pico']['outputs']['armed'] is False
        assert (final['pico'].get('last_applied') or {}).get('request_seq') == sequence
        record['stop_no_replay'] = True
        record['final'] = final
        record['health'] = request('/api/health')
        record['all_50_applied'] = len(record['presets']) == 50
    except Exception as error:
        record['errors'].append(str(error))
    finally:
        try:
            record['final_stop'] = request('/api/pico/command', {'cmd': 'stop'})
        except Exception as error:
            record['errors'].append('Stop: '+str(error))
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True, help='For example http://192.168.184.76:8000')
    parser.add_argument('--run', action='store_true', help='Send all 50 eye presets, test auto-off and Stop; servos stay disabled')
    parser.add_argument('--matrix-only', action='store_true', help='Report existing PCA I2C fault bit 1 separately; still reject matrix/unknown faults and require OE HIGH')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = verify(args.host, args.run, args.matrix_only)
    if args.output:
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'catalog_count': result['catalog_count'], 'all_50_applied': result.get('all_50_applied'),
                      'auto_off_frames': result.get('auto_off', {}).get('frames_seen'),
                      'stop_no_replay': result.get('stop_no_replay'),
                      'other_fault_bits_observed': result['other_fault_bits_observed'], 'errors': result['errors']}), flush=True)
    return 1 if result['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
