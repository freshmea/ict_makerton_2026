#!/usr/bin/env python3
"""Attempt one real Argus frame for a chosen sensor. Missing frames are failures."""
import argparse
import datetime
import glob
import json
import os
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('sensor_id', type=int, choices=[0, 1])
parser.add_argument('output_dir')
args = parser.parse_args()
out = Path(args.output_dir)
out.mkdir(parents=True, exist_ok=True)
os.umask(0o077)
result = {'at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'sensor_id': args.sensor_id, 'uid': os.getuid(), 'video_nodes': glob.glob('/dev/video*'),
          'frames_received': 0}
pipeline = None
try:
    import gi
    gi.require_version('Gst', '1.0')
    from gi.repository import Gst
    Gst.init(None)
    description = ('nvarguscamerasrc sensor-id={} num-buffers=1 ! '
                   'video/x-raw(memory:NVMM),width=1280,height=720,framerate=30/1,format=NV12 ! '
                   'nvvidconv ! video/x-raw,format=BGRx,width=640,height=480 ! '
                   'videoconvert ! video/x-raw,format=RGB ! '
                   'appsink name=frame max-buffers=1 drop=true sync=false').format(args.sensor_id)
    result['pipeline'] = description
    pipeline = Gst.parse_launch(description)
    result['set_playing_result'] = str(pipeline.set_state(Gst.State.PLAYING))
    sample = pipeline.get_by_name('frame').emit('try-pull-sample', 10 * Gst.SECOND)
    if sample is not None:
        caps = sample.get_caps().get_structure(0)
        width, height = caps.get_value('width'), caps.get_value('height')
        buffer = sample.get_buffer()
        data = buffer.extract_dup(0, buffer.get_size())
        path = out / ('sensor-{}-frame.ppm'.format(args.sensor_id))
        path.write_bytes('P6\n{} {}\n255\n'.format(width, height).encode('ascii') + data)
        result.update(frames_received=1, width=width, height=height, frame_bytes=len(data), frame_path=str(path))
    else:
        result['error'] = 'No real frame received within 10 seconds.'
    message = pipeline.get_bus().timed_pop_filtered(0, Gst.MessageType.ERROR)
    if message:
        error, debug = message.parse_error()
        result.update(gstreamer_error=str(error), gstreamer_debug=debug)
except Exception as e:
    result['error'] = str(e)
finally:
    if pipeline is not None:
        pipeline.set_state(Gst.State.NULL)
    (out / ('sensor-{}-result.json'.format(args.sensor_id))).write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
if result['frames_received'] != 1:
    raise SystemExit(1)
