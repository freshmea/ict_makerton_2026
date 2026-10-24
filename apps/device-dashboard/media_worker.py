#!/usr/bin/env python3
"""One CSI owner, NVMM/H.264 capture, bounded preview, shared RTSP feeds.

Run in its own process so native multimedia failures do not take down the API.
The runtime directory is tmpfs; camera/audio data never accumulates on the SD.
"""
import argparse
from collections import deque
import json
import os
from pathlib import Path
import signal
import threading
import time

import gi
gi.require_version('Gst', '1.0')
gi.require_version('GstRtspServer', '1.0')
from gi.repository import Gst, GstRtspServer, GLib

PROFILES = json.loads(Path(__file__).with_name('profiles.json').read_text())
# Camera 1 is mounted upside down in the assembled enclosure.
CAMERA_ROTATIONS = {0: 180, 1: 0}


def atomic_write(path, data):
    temporary = path.with_suffix(path.suffix + '.new')
    temporary.write_bytes(data)
    temporary.replace(path)


class CameraWorker:
    def __init__(self, args):
        self.args = args
        self.profile = PROFILES[args.profile]
        self.loop = GLib.MainLoop()
        self.pipeline = None
        self.lock = threading.RLock()
        self.error = None
        self.started = time.monotonic()
        self.feeds = {0: [], 1: []}
        self.stats = {i: {'frames': 0, 'encoded_frames': 0, 'preview_frames': 0,
                          'points': deque(maxlen=360), 'encoded_points': deque(maxlen=360),
                          'preview_points': deque(maxlen=120), 'last_frame': None,
                          'last_preview': None, 'jpeg_bytes': 0} for i in (0, 1)}

    def pipeline_description(self):
        p = self.profile
        branches = []
        for sensor in (0, 1):
            flip = 2 if CAMERA_ROTATIONS[sensor] == 180 else 0
            if self.args.encoder == 'omxh264enc':
                encoder = ('omxh264enc name=encoder%d bitrate=%d control-rate=2 '
                           'preset-level=0 iframeinterval=%d insert-sps-pps=true' %
                           (sensor, p['bitrate'], p['fps']))
            else:
                encoder = ('nvv4l2h264enc name=encoder%d bitrate=%d control-rate=1 preset-level=1 '
                           'maxperf-enable=true iframeinterval=%d idrinterval=%d insert-sps-pps=true' %
                           (sensor, p['bitrate'], p['fps'], p['fps']))
            branches.append(
                'nvarguscamerasrc name=source{0} sensor-id={0} sensor-mode={mode} ! '
                'video/x-raw(memory:NVMM),format=NV12,width={cw},height={ch},framerate={fps}/1 ! '
                'tee name=t{0} '
                't{0}. ! queue leaky=downstream max-size-buffers=1 max-size-bytes=0 max-size-time=0 ! '
                'nvvidconv name=rotate_h264{0} flip-method={flip} ! video/x-raw(memory:NVMM),format=NV12,width={w},height={h} ! '
                '{encoder} ! '
                'h264parse ! video/x-h264,stream-format=byte-stream,alignment=au ! '
                'appsink name=h264{0} emit-signals=true max-buffers=2 drop=true sync=false '
                't{0}. ! queue leaky=downstream max-size-buffers=1 max-size-bytes=0 max-size-time=0 ! '
                'nvvidconv name=rotate_jpeg{0} flip-method={flip} ! video/x-raw,format=I420,width=640,height=360 ! '
                'videorate drop-only=true ! video/x-raw,framerate=15/1 ! '
                'jpegenc quality=72 ! appsink name=jpeg{0} emit-signals=true max-buffers=1 drop=true sync=false'
                .format(sensor, mode=p['sensor_mode'], cw=p['capture_width'], ch=p['capture_height'],
                        fps=p['fps'], w=p['width'], h=p['height'], encoder=encoder, flip=flip))
        return ' '.join(branches)

    def source_probe(self, pad, info, sensor):
        buffer = info.get_buffer()
        if buffer is not None:
            stamp = time.monotonic()
            with self.lock:
                state = self.stats[sensor]
                state['frames'] += 1
                state['last_frame'] = stamp
                state['points'].append((stamp, int(buffer.pts), int(buffer.get_size())))
        return Gst.PadProbeReturn.OK

    def jpeg_sample(self, sink, sensor):
        sample = sink.emit('pull-sample')
        if sample is None:
            return Gst.FlowReturn.ERROR
        buffer = sample.get_buffer()
        data = buffer.extract_dup(0, buffer.get_size())
        atomic_write(self.args.runtime / ('cam%d.jpg' % sensor), data)
        stamp = time.monotonic()
        with self.lock:
            state = self.stats[sensor]
            state['preview_frames'] += 1
            state['last_preview'] = stamp
            state['jpeg_bytes'] = len(data)
            state['preview_points'].append((stamp, int(buffer.pts), len(data)))
        return Gst.FlowReturn.OK

    def h264_sample(self, sink, sensor):
        sample = sink.emit('pull-sample')
        if sample is None:
            return Gst.FlowReturn.ERROR
        buffer = sample.get_buffer()
        data = buffer.extract_dup(0, buffer.get_size())
        stamp = time.monotonic()
        with self.lock:
            self.stats[sensor]['encoded_frames'] += 1
            self.stats[sensor]['encoded_points'].append((stamp, int(buffer.pts), len(data)))
            targets = list(self.feeds[sensor])
        for target in targets:
            if not target['want_data']:
                continue
            if target['base'] is None:
                target['base'] = int(buffer.pts)
            output = Gst.Buffer.new_allocate(None, len(data), None)
            output.fill(0, data)
            output.pts = output.dts = max(0, int(buffer.pts) - target['base'])
            output.duration = Gst.SECOND // self.profile['fps']
            if target['source'].emit('push-buffer', output) != Gst.FlowReturn.OK:
                target['want_data'] = False
        return Gst.FlowReturn.OK

    def configure_media(self, factory, media, sensor):
        source = media.get_element().get_by_name('encoded')
        target = {'source': source, 'base': None, 'want_data': False}
        source.connect('need-data', lambda *_: target.update(want_data=True))
        source.connect('enough-data', lambda *_: target.update(want_data=False))
        with self.lock:
            self.feeds[sensor].append(target)
        def unprepared(*_):
            with self.lock:
                if target in self.feeds[sensor]:
                    self.feeds[sensor].remove(target)
        media.connect('unprepared', unprepared)

    def start_rtsp(self):
        self.server = GstRtspServer.RTSPServer()
        self.server.set_address(self.args.bind)
        self.server.set_service(str(self.args.rtsp_port))
        mounts = self.server.get_mount_points()
        for sensor in (0, 1):
            factory = GstRtspServer.RTSPMediaFactory()
            factory.set_shared(True)
            factory.set_latency(0)
            factory.set_launch(
                '( appsrc name=encoded is-live=true format=time block=false max-bytes=262144 '
                'caps="video/x-h264,stream-format=byte-stream,alignment=au,framerate=%d/1" ! '
                'queue leaky=downstream max-size-buffers=2 max-size-bytes=0 max-size-time=0 ! '
                'h264parse ! rtph264pay name=pay0 pt=96 config-interval=1 )' % self.profile['fps'])
            factory.connect('media-configure', self.configure_media, sensor)
            mounts.add_factory('/cam%d' % sensor, factory)
        if self.server.attach(None) == 0:
            raise RuntimeError('RTSP port could not be bound.')

    @staticmethod
    def rates(points):
        values = list(points)
        if len(values) < 2:
            return 0.0, 0.0
        recent = [v for v in values if v[0] >= values[-1][0] - 3]
        if len(recent) < 2:
            return 0.0, 0.0
        duration = (recent[-1][1] - recent[0][1]) / 1e9
        fps = (len(recent) - 1) / duration if duration > 0 else 0
        mbps = sum(v[2] for v in recent[1:]) * 8 / max(duration, .001) / 1e6
        return round(fps, 2), round(mbps, 3)

    @staticmethod
    def delivery_rate(points):
        values = list(points)
        recent = [v for v in values if v[0] >= time.monotonic() - 3]
        if len(recent) < 2:
            return 0.0
        return round((len(recent) - 1) / max(.001, recent[-1][0] - recent[0][0]), 2)

    def publish(self):
        stamp = time.monotonic()
        cameras = []
        with self.lock:
            for sensor, state in self.stats.items():
                fps, _ = self.rates(state['points'])
                encoded_fps, mbps = self.rates(state['encoded_points'])
                preview_fps, _ = self.rates(state['preview_points'])
                age = round((stamp - state['last_frame']) * 1000) if state['last_frame'] else None
                preview_age = round((stamp - state['last_preview']) * 1000) if state['last_preview'] else None
                encoded_age = round((stamp - state['encoded_points'][-1][0]) * 1000) if state['encoded_points'] else None
                cameras.append({'sensor_id': sensor, 'node': '/dev/video%d' % sensor,
                                'rotation_degrees': CAMERA_ROTATIONS[sensor],
                                'ready': all(a is not None and a < 2000 for a in (age, preview_age, encoded_age)),
                                'frames': state['frames'], 'encoded_frames': state['encoded_frames'],
                                'preview_frames': state['preview_frames'], 'fps': fps,
                                'encoded_fps': encoded_fps, 'preview_fps': preview_fps,
                                'capture_delivery_fps': self.delivery_rate(state['points']),
                                'encoded_delivery_fps': self.delivery_rate(state['encoded_points']),
                                'preview_delivery_fps': self.delivery_rate(state['preview_points']),
                                'encoder_pts_lag_ms': round((state['points'][-1][1] - state['encoded_points'][-1][1]) / 1e6, 1)
                                    if state['points'] and state['encoded_points'] else None,
                                'encoded_mbps': mbps, 'age_ms': age, 'jpeg_bytes': state['jpeg_bytes'],
                                'preview_age_ms': preview_age, 'encoded_age_ms': encoded_age,
                                'rtsp_feeds': len(self.feeds[sensor])})
        result = {'run_id': self.args.run_id, 'profile': self.args.profile, 'settings': self.profile,
                  'preview': {'width': 640, 'height': 360, 'fps': 15, 'quality': 72},
                  'encoder': self.args.encoder, 'preview_encoder': 'jpegenc',
                  'uptime_seconds': round(stamp - self.started, 1), 'updated_monotonic': stamp,
                  'error': self.error, 'cameras': cameras, 'pipeline': self.description,
                  'uid': os.getuid(), 'rtsp_port': self.args.rtsp_port}
        atomic_write(self.args.runtime / 'camera-state.json', json.dumps(result).encode())
        return True

    def on_message(self, bus, message):
        if message.type == Gst.MessageType.ERROR:
            error, debug = message.parse_error()
            self.error = str(error) + ' ' + str(debug)
            print(self.error, flush=True)
            self.publish()
            self.loop.quit()

    def run(self):
        Gst.init(None)
        self.args.runtime.mkdir(parents=True, exist_ok=True)
        self.description = self.pipeline_description()
        self.pipeline = Gst.parse_launch(self.description)
        for sensor in (0, 1):
            self.pipeline.get_by_name('source%d' % sensor).get_static_pad('src').add_probe(
                Gst.PadProbeType.BUFFER, self.source_probe, sensor)
            self.pipeline.get_by_name('jpeg%d' % sensor).connect('new-sample', self.jpeg_sample, sensor)
            self.pipeline.get_by_name('h264%d' % sensor).connect('new-sample', self.h264_sample, sensor)
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect('message', self.on_message)
        self.start_rtsp()
        GLib.timeout_add(250, self.publish)
        for sig in (signal.SIGTERM, signal.SIGINT):
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, lambda: self.loop.quit())
        try:
            if self.pipeline.set_state(Gst.State.PLAYING) == Gst.StateChangeReturn.FAILURE:
                raise RuntimeError('Capture failed to enter PLAYING.')
            self.loop.run()
        finally:
            self.pipeline.set_state(Gst.State.NULL)
            self.pipeline.get_state(5 * Gst.SECOND)
        return 1 if self.error else 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--profile', choices=PROFILES, default='720p30')
    parser.add_argument('--run-id', default='manual')
    parser.add_argument('--encoder', choices=['omxh264enc', 'nvv4l2h264enc'], default='omxh264enc')
    parser.add_argument('--bind', default='192.168.219.127')
    parser.add_argument('--rtsp-port', type=int, default=8554)
    raise SystemExit(CameraWorker(parser.parse_args()).run())
