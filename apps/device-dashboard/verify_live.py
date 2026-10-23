#!/usr/bin/env python3
"""Read hardware/API and decode both RTSP feeds. Only optional speaker tone/Stop mutate.

Run with the dashboard venv; JSON evidence goes to --output.
"""
import argparse
import concurrent.futures
import io
import json
from pathlib import Path
import threading
import time
import urllib.request
import urllib.error
import wave


def request(base, path, body=None, token=None, origin=None):
    headers = {'Content-Type': 'application/json'}
    if token: headers['X-CSRF-Token'] = token
    if origin: headers['Origin'] = origin
    req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=35) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


def decode_rtsp(host, sensor, frames=90):
    import gi
    gi.require_version('Gst', '1.0')
    from gi.repository import Gst
    Gst.init(None)
    pipeline = Gst.parse_launch(
        'rtspsrc location=rtsp://%s:8554/cam%d protocols=tcp latency=100 ! '
        'rtph264depay ! h264parse ! avdec_h264 ! video/x-raw,format=I420 ! '
        'appsink name=decoded max-buffers=2 drop=true sync=false' % (host, sensor))
    sink = pipeline.get_by_name('decoded')
    count, size, caps, points = 0, 0, None, []
    first = time.monotonic()
    deadline = first + 20
    pipeline.set_state(Gst.State.PLAYING)
    try:
        while time.monotonic() < deadline and count < frames:
            sample = sink.emit('try-pull-sample', Gst.SECOND)
            if sample:
                count += 1; size += sample.get_buffer().get_size()
                caps = sample.get_caps().to_string()
                points.append((time.monotonic(), sample.get_buffer().pts))
            message = pipeline.get_bus().pop_filtered(Gst.MessageType.ERROR)
            if message: raise RuntimeError(str(message.parse_error()))
    finally:
        pipeline.set_state(Gst.State.NULL)
        pipeline.get_state(3 * Gst.SECOND)
    duration = (points[-1][1] - points[0][1]) / 1e9 if len(points) > 1 else 0
    return {'sensor_id': sensor, 'frames_decoded': count, 'bytes_decoded': size, 'caps': caps,
            'pts_fps': round((count - 1) / duration, 2) if duration else 0,
            'first_frame_seconds': round(points[0][0] - first, 2) if points else None,
            'ok': count >= frames}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='192.168.219.127')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--profile', choices=['360p30', '720p30', '720p60', '1080p30'])
    parser.add_argument('--speaker-stop', action='store_true')
    args = parser.parse_args()
    base = 'http://%s:8000' % args.host
    code, data = request(base, '/api/session'); assert code == 200
    token = json.loads(data)['csrf_token']
    checks = {}
    checks['missing_csrf_rejected'] = request(base, '/api/pico/command', {'cmd': 'status'})[0] == 403
    checks['cross_origin_rejected'] = request(base, '/api/pico/command', {'cmd': 'status'}, token, 'http://example.invalid')[0] == 403
    checks['unknown_command_rejected'] = request(base, '/api/pico/command', {'cmd': 'shell'}, token)[0] == 422
    checks['unknown_profile_rejected'] = request(base, '/api/cameras/profile', {'profile': '4k'}, token)[0] == 422
    checks['unknown_camera_rejected'] = request(base, '/api/cameras/9/snapshot.jpg')[0] == 404
    if args.profile:
        code, data = request(base, '/api/cameras/profile', {'profile': args.profile}, token)
        assert code == 200, (code, data)
    time.sleep(5)
    readings = []
    for _ in range(12):
        code, data = request(base, '/api/status'); assert code == 200
        readings.append(json.loads(data)); time.sleep(.5)
    decoded = []
    # Sequential clients avoid software decoding both 1080p feeds loading the Nano.
    for sensor in (0, 1): decoded.append(decode_rtsp(args.host, sensor))
    code, audio = request(base, '/api/audio/recent.wav')
    if code == 200:
        with wave.open(io.BytesIO(audio)) as reader:
            checks['microphone_pcm'] = {'rate': reader.getframerate(), 'channels': reader.getnchannels(), 'frames': reader.getnframes()}
    if args.speaker_stop:
        code, data = request(base, '/api/audio/play', {'action': 'tone'}, token)
        checks['speaker'] = {'http': code, 'response': json.loads(data)}
        code, data = request(base, '/api/pico/command', {'cmd': 'stop'}, token)
        checks['stop'] = {'http': code, 'response': json.loads(data)}
    code, data = request(base, '/api/pico/command', {'cmd': 'status'}, token)
    checks['usb_status'] = {'http': code, 'response': json.loads(data)}
    result = {'timestamp_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'checks': checks,
              'readings': readings, 'rtsp_decode': decoded}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({'checks': checks, 'rtsp_decode': decoded, 'profile': readings[-1]['cameras']['profile']}, ensure_ascii=False))
    assert all(d['ok'] for d in decoded), 'RTSP decode incomplete'
    assert readings[-1]['pico']['connected'] and readings[-1]['cameras']['ready'] and readings[-1]['audio']['connected']
    assert all(v is True for k, v in checks.items() if k.endswith('rejected'))


if __name__ == '__main__': main()
