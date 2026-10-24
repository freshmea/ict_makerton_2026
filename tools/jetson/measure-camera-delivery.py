#!/usr/bin/env python3
"""Read-only dashboard delivery probe; run on Nano and a viewer to compare.

Uses no third-party packages and ignores HTTP proxy environment variables for
the explicitly supplied LAN URL. Never changes camera profiles or services.
MJPEG fps counts complete received frames, not settings or ffmpeg decode speed.
This does not measure exposure-to-display latency or browser rendering.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import time
from urllib.request import build_opener, ProxyHandler, Request


def distribution(values):
    if not values:
        return None
    ordered = sorted(values)
    return {'n': len(values), 'mean': round(statistics.mean(values), 2),
            'median': round(statistics.median(values), 2),
            'p95': round(ordered[min(len(ordered) - 1, int((len(ordered) - 1) * .95 + .5))], 2),
            'max': round(ordered[-1], 2)}


def open_url(url):
    return build_opener(ProxyHandler({})).open(
        Request(url, headers={'Cache-Control': 'no-cache'}), timeout=4)


def fetch(url):
    start = time.monotonic()
    with open_url(url) as response:
        headers_ms = (time.monotonic() - start) * 1000
        body = response.read()
    return body, {'headers_ms': round(headers_ms, 2),
                  'total_ms': round((time.monotonic() - start) * 1000, 2), 'bytes': len(body)}


def telemetry(base, deadline):
    result = {'samples': [], 'errors': []}
    while time.monotonic() < deadline:
        started = time.monotonic()
        try:
            _, health_timing = fetch(base + '/api/health')
            body, status_timing = fetch(base + '/api/status')
            state = json.loads(body)
            cameras = dict(state['cameras'])
            cameras.pop('pipeline', None)
            result['samples'].append({'at_utc': datetime.now(timezone.utc).isoformat(),
                                      'health': health_timing, 'status': status_timing,
                                      'system': state['system'], 'cameras': cameras})
        except Exception as error:
            result['errors'].append(str(error))
        time.sleep(max(0, min(.75 - (time.monotonic() - started), deadline - time.monotonic())))
    result['health_total_ms'] = distribution([s['health']['total_ms'] for s in result['samples']])
    result['status_total_ms'] = distribution([s['status']['total_ms'] for s in result['samples']])
    result['cpu_percent'] = distribution([s['system']['cpu_percent'] for s in result['samples']])
    return result


def stream(base, sensor, deadline):
    start = time.monotonic()
    stamps, sizes, hashes = [], [], []
    error = None
    try:
        with open_url(base + '/api/cameras/%d/stream.mjpg' % sensor) as response:
            while time.monotonic() < deadline:
                boundary = response.readline(4096)
                if not boundary:
                    break
                if boundary.strip() != b'--frame':
                    continue
                headers = {}
                while True:
                    line = response.readline(4096)
                    if not line or line == b'\r\n':
                        break
                    key, _, value = line.decode('ascii').partition(':')
                    headers[key.lower()] = value.strip()
                size = int(headers['content-length'])
                if not 0 < size < 4 * 1024 * 1024:
                    raise ValueError('Invalid frame size: %d' % size)
                frame = response.read(size)
                if len(frame) != size:
                    raise IOError('Incomplete frame')
                stamps.append(time.monotonic())
                sizes.append(size)
                hashes.append(hashlib.sha256(frame).hexdigest())
    except Exception as exc:
        error = str(exc)
    duration = stamps[-1] - stamps[0] if len(stamps) > 1 else 0
    return {'sensor_id': sensor, 'frames': len(stamps), 'error': error,
            'first_frame_ms': round((stamps[0] - start) * 1000, 2) if stamps else None,
            'received_fps': round((len(stamps) - 1) / duration, 2) if duration else 0,
            'receive_interval_ms': distribution([(b - a) * 1000 for a, b in zip(stamps, stamps[1:])]),
            'jpeg_bytes': distribution(sizes),
            'payload_mbps': round(sum(sizes[1:]) * 8 / duration / 1e6, 3) if duration else 0,
            'identical_adjacent_payloads': sum(a == b for a, b in zip(hashes, hashes[1:])),
            'elapsed_seconds': round(time.monotonic() - start, 3),
            'frame_arrival_offsets_ms': [round((stamp - start) * 1000, 2) for stamp in stamps]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True, help='e.g. http://192.168.184.76:8000')
    parser.add_argument('--seconds', type=float, default=12, help='seconds per phase (default: 12)')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--phases', nargs='+', choices=['baseline', 'single', 'dual'],
                        default=['baseline', 'single', 'dual'])
    args = parser.parse_args()
    if not 2 <= args.seconds <= 60:
        parser.error('--seconds must be between 2 and 60')
    result = {'at_utc': datetime.now(timezone.utc).isoformat(), 'url': args.url,
              'seconds_per_phase': args.seconds,
              'limitations': ['Additional probe clients coexist with existing viewers.',
                              'No browser paint or exposure-to-display measurement.',
                              'Local and LAN probes must use the same serving interface.'], 'phases': []}
    for name in args.phases:
        deadline = time.monotonic() + args.seconds
        sensors = [] if name == 'baseline' else [0] if name == 'single' else [0, 1]
        with ThreadPoolExecutor(max_workers=3) as pool:
            status = pool.submit(telemetry, args.url.rstrip('/'), deadline)
            streams = [pool.submit(stream, args.url.rstrip('/'), sensor, deadline) for sensor in sensors]
            phase = {'name': name, 'telemetry': status.result(), 'streams': [s.result() for s in streams]}
        result['phases'].append(phase)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'phase': name, 'health_ms': phase['telemetry']['health_total_ms'],
                          'status_ms': phase['telemetry']['status_total_ms'],
                          'cpu_percent': phase['telemetry']['cpu_percent'],
                          'streams': [{k: v for k, v in s.items() if k != 'frame_arrival_offsets_ms'}
                                      for s in phase['streams']]}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
