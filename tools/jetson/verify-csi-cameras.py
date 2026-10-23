#!/usr/bin/env python3
"""Receive real CSI frames as a normal user; save unaltered RGB frames as PNG.

Tests sensor 0, sensor 1, then concurrent streams. No display server is needed.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import struct
import time
import zlib

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstVideo', '1.0')
from gi.repository import Gst, GstVideo


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def png_chunk(name, data):
    return struct.pack('!I', len(data)) + name + data + struct.pack('!I', zlib.crc32(name + data) & 0xffffffff)


def save_png(path, sample):
    caps = sample.get_caps()
    video = GstVideo.VideoInfo()
    if not video.from_caps(caps):
        raise RuntimeError('Cannot read frame layout.')
    layout = caps.get_structure(0)
    width, height = layout.get_value('width'), layout.get_value('height')
    if layout.get_value('format') != 'RGB':
        raise RuntimeError('Expected RGB frame.')
    buffer = sample.get_buffer()
    data = buffer.extract_dup(0, buffer.get_size())
    stride, offset = int(video.stride[0]), int(video.offset[0])
    if len(data) < offset + stride * (height - 1) + width * 3:
        raise RuntimeError('Truncated frame buffer.')
    # Row filter 0, no rotation, resizing, annotations or synthetic pixels.
    scanlines = b''.join(b'\0' + data[offset + y * stride:offset + y * stride + width * 3]
                         for y in range(height))
    encoded = (b'\x89PNG\r\n\x1a\n' +
               png_chunk(b'IHDR', struct.pack('!2I5B', width, height, 8, 2, 0, 0, 0)) +
               png_chunk(b'IDAT', zlib.compress(scanlines, 3)) + png_chunk(b'IEND', b''))
    path.write_bytes(encoded)
    values = data[offset:offset + stride * height:97]
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return {'path': str(path), 'width': width, 'height': height,
            'sha256': hashlib.sha256(encoded).hexdigest(), 'bytes': len(encoded),
            'sampled_channel_mean': round(mean, 3), 'sampled_channel_stddev': round(variance ** .5, 3)}


def scenario(name, sensors, frames, output):
    description = ' '.join(
        'nvarguscamerasrc sensor-id={0} ! '
        'video/x-raw(memory:NVMM),width=1280,height=720,framerate=30/1,format=NV12 ! '
        'nvvidconv ! video/x-raw,format=BGRx,width=1280,height=720 ! '
        'videoconvert ! video/x-raw,format=RGB ! '
        'appsink name=frame{0} max-buffers=4 drop=true sync=false'.format(sensor)
        for sensor in sensors)
    result = {'name': name, 'at_utc': now(), 'sensors': sensors, 'pipeline': description,
              'requested_frames_each': frames, 'streams': {}, 'passed': False}
    pipeline = None
    last_samples = {}
    try:
        pipeline = Gst.parse_launch(description)
        sinks = {sensor: pipeline.get_by_name('frame' + str(sensor)) for sensor in sensors}
        for sensor in sensors:
            result['streams'][str(sensor)] = {'frames_received': 0, 'pts_ns': [],
                                              'first_monotonic': None, 'last_monotonic': None}
        state = pipeline.set_state(Gst.State.PLAYING)
        result['set_playing_result'] = str(state)
        if state == Gst.StateChangeReturn.FAILURE:
            raise RuntimeError('GStreamer refused PLAYING state.')
        deadline = time.monotonic() + 40
        bus = pipeline.get_bus()
        while any(s['frames_received'] < frames for s in result['streams'].values()):
            error = bus.pop_filtered(Gst.MessageType.ERROR)
            if error:
                reason, debug = error.parse_error()
                raise RuntimeError(str(reason) + ': ' + str(debug))
            if time.monotonic() > deadline:
                raise RuntimeError('Frame capture timed out after 40 seconds.')
            for sensor, sink in sinks.items():
                stream = result['streams'][str(sensor)]
                if stream['frames_received'] >= frames:
                    continue
                sample = sink.emit('try-pull-sample', Gst.SECOND)
                if sample is None:
                    continue
                stamp = time.monotonic()
                stream['frames_received'] += 1
                stream['first_monotonic'] = stream['first_monotonic'] or stamp
                stream['last_monotonic'] = stamp
                stream['pts_ns'].append(int(sample.get_buffer().pts))
                last_samples[sensor] = sample
        for sensor in sensors:
            stream = result['streams'][str(sensor)]
            pts = stream['pts_ns']
            stream['pts_strictly_increasing'] = all(a < b < Gst.CLOCK_TIME_NONE for a, b in zip(pts, pts[1:]))
            stream['fps_from_pts'] = round((len(pts) - 1) * 1e9 / (pts[-1] - pts[0]), 3)
            stream['pts_gaps_over_50ms'] = sum(b - a > 50_000_000 for a, b in zip(pts, pts[1:]))
            stream['image'] = save_png(output / ('%s-sensor-%d.png' % (name, sensor)), last_samples[sensor])
        streams = list(result['streams'].values())
        result['observed_stream_overlap_seconds'] = max(0, round(
            min(s['last_monotonic'] for s in streams) - max(s['first_monotonic'] for s in streams), 3))
        result['passed'] = all(s['frames_received'] == frames and s['pts_strictly_increasing'] for s in streams)
        if len(sensors) > 1:
            result['passed'] = result['passed'] and result['observed_stream_overlap_seconds'] > 0
    except Exception as error:
        result['error'] = str(error)
    finally:
        if pipeline is not None:
            pipeline.set_state(Gst.State.NULL)
            pipeline.get_state(5 * Gst.SECOND)
        last_samples.clear()
    print(json.dumps(result, indent=2), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output_dir', type=Path)
    parser.add_argument('--frames', type=int, default=90)
    args = parser.parse_args()
    if not 30 <= args.frames <= 300:
        parser.error('--frames must be 30..300')
    if os.geteuid() == 0:
        parser.error('Run as camerad or another non-root user with video/render access.')
    os.umask(0o077)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    Gst.init(None)
    result = {'at_utc': now(), 'uid': os.getuid(), 'gid': os.getgid(), 'groups': os.getgroups(),
              'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
              'display': os.environ.get('DISPLAY'), 'scenarios': [], 'passed': False}
    for name, sensors in [('single-0', [0]), ('single-1', [1]), ('dual', [0, 1])]:
        print('Starting ' + name, flush=True)
        result['scenarios'].append(scenario(name, sensors, args.frames, args.output_dir))
    result['passed'] = all(s['passed'] for s in result['scenarios'])
    result['finished_utc'] = now()
    (args.output_dir / 'capture-results.json').write_text(json.dumps(result, indent=2) + '\n')
    print('All scenarios passed: ' + str(result['passed']), flush=True)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
