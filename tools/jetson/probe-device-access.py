#!/usr/bin/env python3
"""Open selected device nodes without transmitting data; run as a service user."""
import argparse
import glob
import grp
import json
import os
from pathlib import Path
import stat

parser = argparse.ArgumentParser()
parser.add_argument('role', choices=['pico', 'audio', 'camera'])
args = parser.parse_args()
if args.role == 'pico':
    paths = glob.glob('/dev/pico-device') + glob.glob('/dev/pico-neopixel')
    for alias in list(paths):
        tty = Path(alias).resolve().name
        for parent in (Path('/sys/class/tty') / tty).resolve().parents:
            if (parent / 'idVendor').is_file() and (parent / 'idVendor').read_text().strip() == 'c0de':
                paths.append('/dev/bus/usb/{:03d}/{:03d}'.format(int((parent / 'busnum').read_text()), int((parent / 'devnum').read_text())))
                break
elif args.role == 'audio':
    from device_access import audio_card
    number = audio_card()['card'][4:]
    paths = ['/dev/snd/controlC' + number, '/dev/snd/pcmC' + number + 'D0c', '/dev/snd/pcmC' + number + 'D0p']
else:
    paths = glob.glob('/dev/video*') + glob.glob('/dev/media*')
    paths += [p for p in ['/dev/nvmap', '/dev/nvhost-vi', '/dev/nvhost-isp', '/dev/nvhost-vic', '/dev/nvhost-gpu'] if os.path.exists(p)]
result = {'role': args.role, 'uid': os.getuid(), 'groups': [grp.getgrgid(g).gr_name for g in os.getgroups()], 'devices': []}
if args.role == 'camera':
    result['video_nodes'] = glob.glob('/dev/video*')
for path in paths:
    s = os.stat(path)
    item = {'path': path, 'mode': oct(stat.S_IMODE(s.st_mode)), 'group': grp.getgrgid(s.st_gid).gr_name}
    try:
        fd = os.open(path, os.O_RDWR | os.O_NONBLOCK | os.O_NOCTTY)
        os.close(fd)
        item['open_rw'] = True
    except OSError as e:
        item.update(open_rw=False, errno=e.errno, error=e.strerror)
    result['devices'].append(item)
print(json.dumps(result, indent=2))
if not paths or any(not d['open_rw'] for d in result['devices']):
    raise SystemExit(1)
