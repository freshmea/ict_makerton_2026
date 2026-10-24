#!/usr/bin/env python3
"""Linux RP2350 build metadata and guarded USB updater (Python standard library).

Check mode enumerates sysfs only: no CDC commands, USB resets or flash writes.
Only the integrated binary protocol may request a software BOOTSEL transition.
"""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import time

REPO = Path(__file__).resolve().parent.parent
TOOL_HOME = REPO / '.local-tools/linux/picotool/2.3.1'
IMAGE = REPO / 'firmware/pico2-device-bench/dist/linux/pico2-device-bench.uf2'
HOST = REPO / 'tools/pico-device-bench/target/release/pico-device-bench'
TARGET = 'thumbv8m.main-none-eabihf'
FAMILY = '0xe48bff59'


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_hashes():
    hashes = {}
    for directory in ('firmware/pico2-device-bench', 'tools/pico-device-bench', 'crates/pico-device-protocol'):
        root = REPO / directory
        for path in sorted(root.rglob('*')):
            parts = path.relative_to(root).parts
            if path.is_file() and (parts[0] in ('src', '.cargo') or
                    path.relative_to(root).as_posix() in ('Cargo.toml', 'Cargo.lock', 'build.rs', 'memory.x')):
                hashes[path.relative_to(REPO).as_posix()] = digest(path)
    return hashes


def save(path, data):
    Path(path).write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


def run(args, timeout=90, log=None):
    result = subprocess.run([str(x) for x in args], stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, encoding='utf-8', errors='replace',
                            timeout=timeout)
    if log:
        with log.open('a', encoding='utf-8') as stream:
            stream.write('$ ' + ' '.join(str(x) for x in args) + '\n' + result.stdout + '\n')
    if result.returncode:
        raise RuntimeError('Command failed (%d): %s\n%s' %
                           (result.returncode, args[0], result.stdout))
    return result.stdout


def tool_path(record=False):
    binary = TOOL_HOME / 'install/bin/picotool'
    if not binary.is_file():
        raise RuntimeError('Run bash firmware/setup-linux.sh first.')
    if not record:
        info = json.loads((TOOL_HOME / 'install-info.json').read_text())
        if (info.get('sha256') != digest(binary) or info.get('version') != '2.3.1'
                or not info.get('file_info_smoke_verified')):
            raise RuntimeError('Installed picotool hash/version differs from setup manifest.')
    version = run([binary, 'version'])
    if not re.search(r'picotool v?2\.3\.1\b', version, re.I) or 'without USB support' in version:
        raise RuntimeError('Require picotool 2.3.1 with USB support: ' + version)
    if record:
        # Version alone missed a formatter crash. Exercise file-info without USB.
        sample = TOOL_HOME / 'debug/xip_ram_perms/xip_ram_perms.elf'
        smoke = run([binary, 'info', '-a', sample])
        info = {'at_utc': now(), 'version': '2.3.1', 'sha256': digest(binary),
                'picotool_revision': run(['git', '-C', TOOL_HOME / 'source', 'rev-parse', 'HEAD']).strip(),
                'sdk_revision': run(['git', '-C', TOOL_HOME / 'sdk', 'rev-parse', 'HEAD']).strip(),
                'architecture': os.uname().machine, 'version_output': version.strip(),
                'build_type': 'Debug', 'file_info_smoke_verified': True,
                'file_info_smoke_output': smoke.strip()}
        save(TOOL_HOME / 'install-info.json', info)
    return binary


def validate_uf2(path, metadata=True):
    data = path.read_bytes()
    if not data or len(data) % 512:
        raise ValueError('Invalid UF2 size.')
    blocks = len(data) // 512
    seen, ranges = set(), []
    for offset in range(0, len(data), 512):
        m0, m1, flags, address, size, number, count, family = struct.unpack_from('<8I', data, offset)
        end, = struct.unpack_from('<I', data, offset + 508)
        if (m0, m1, end) != (0x0a324655, 0x9e5d5157, 0x0ab16f30):
            raise ValueError('UF2 magic mismatch.')
        if flags != 0x2000 or family != 0xe48bff59:
            raise ValueError('Require flash-only RP2350 Arm Secure UF2 blocks.')
        if not 0 < size <= 476 or address < 0x10000000 or address + size > 0x10400000:
            raise ValueError('UF2 payload outside Pico 2 4 MiB flash.')
        if count != blocks or number >= blocks or number in seen:
            raise ValueError('UF2 block numbering mismatch.')
        seen.add(number)
        ranges.append((address, address + size))
    ordered = sorted(ranges)
    if any(a[1] > b[0] for a, b in zip(ordered, ordered[1:])):
        raise ValueError('Overlapping UF2 flash payloads.')
    info = {'target': TARGET, 'family': FAMILY, 'blocks': blocks, 'bytes': len(data),
            'sha256': hashlib.sha256(data).hexdigest()}
    if metadata:
        manifest = json.loads(path.with_name('build-info.json').read_text(encoding='utf-8-sig'))
        if any(str(manifest.get(key)).lower() != str(value).lower() for key, value in info.items()):
            raise ValueError('UF2 differs from build-info.json. Rebuild before flashing.')
    return info


def inventory():
    devices = []
    for path in sorted(Path('/sys/bus/usb/devices').glob('*')):
        try:
            vid = (path / 'idVendor').read_text().strip()
            pid = (path / 'idProduct').read_text().strip()
            if vid not in ('c0de', '2e8a'):
                continue
            bus = int((path / 'busnum').read_text())
            address = int((path / 'devnum').read_text())
            node = Path('/dev/bus/usb/%03d/%03d' % (bus, address))
            serial = (path / 'serial').read_text().strip() if (path / 'serial').exists() else ''
            devices.append({'sysfs': str(path.resolve()), 'vid': vid, 'pid': pid,
                            'serial': serial, 'bus': bus, 'address': address,
                            'usb_node': str(node), 'read_write': os.access(node, os.R_OK | os.W_OK)})
        except FileNotFoundError:
            continue  # Device disconnected during snapshot; never infer a flash target.
    return devices


def roms():
    return [d for d in inventory() if d['vid'] == '2e8a' and d['pid'] in ('0003', '000f')]


def one_rom(expected_serial=None):
    devices = roms()
    if len(devices) != 1 or devices[0]['pid'] != '000f':
        raise RuntimeError('Require exactly one RP2350 BOOTSEL device (2e8a:000f).')
    device = devices[0]
    if expected_serial and device['serial'].lower() != expected_serial.lower():
        raise RuntimeError('BOOTSEL serial differs from the selected application device.')
    if not device['read_write']:
        raise RuntimeError('BOOTSEL USB permission denied. Install rules and reconnect/login.')
    return device


def selection(device):
    return ['--bus', str(device['bus']), '--address', str(device['address']),
            '--vid', '0x2e8a', '--pid', '0x000f']


def same_rom(device):
    if one_rom(device['serial']) != device:
        raise RuntimeError('USB inventory changed; refusing to continue with a different target.')


def cdc_device(port):
    path = Path(port).resolve(strict=True)
    if not re.fullmatch(r'ttyACM[0-9]+', path.name):
        raise RuntimeError('Use an explicit Pico ttyACM or stable udev alias.')
    parent = (Path('/sys/class/tty') / path.name / 'device').resolve()
    for candidate in (parent,) + tuple(parent.parents):
        if (candidate / 'idVendor').exists():
            vid = (candidate / 'idVendor').read_text().strip()
            pid = (candidate / 'idProduct').read_text().strip()
            if (vid, pid) != ('c0de', 'cafc'):
                raise RuntimeError('Current device is %s:%s, not the integrated c0de:cafc variant required by --port. No CDC bytes sent. A different variant may support picotool USB reset; BOOTSEL-button necessity is not inferred from VID/PID.' % (vid, pid))
            device = [d for d in inventory() if d['sysfs'] == str(candidate)]
            if len(device) != 1:
                raise RuntimeError('Selected CDC device disappeared.')
            return device[0]
    raise RuntimeError('No USB parent for selected CDC port.')


def status(port, log):
    output = run([HOST, '--port', port, 'status'], timeout=20, log=log)
    lines = [line for line in output.splitlines() if line.startswith('STATUS ')]
    if len(lines) != 1:
        raise RuntimeError('Expected one STATUS response from integrated firmware.')
    pairs = [word.split('=', 1) for word in lines[0].split()[1:] if '=' in word]
    values = dict(pairs)
    if len(values) != len(pairs) or any(values.get(k) != v for k, v in
            {'protocol': 'pico-device-v2', 'oe_high': '1', 'bootloader': 'picotool-v1'}.items()):
        raise RuntimeError('Protocol, stopped OE HIGH or bootloader capability not verified: ' + lines[0])
    return values


def wait_for(probe, timeout):
    deadline = time.monotonic() + timeout
    while True:
        result = probe()
        if result:
            return result
        if time.monotonic() >= deadline:
            raise RuntimeError('USB re-enumeration timed out; inspect the result log before retrying.')
        time.sleep(0.4)


def flash(argv):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true', help='validate tools/image and enumerate USB; no device commands')
    mode.add_argument('--port', help='explicit integrated firmware CDC port, e.g. /dev/pico-device')
    mode.add_argument('--bootsel', action='store_true', help='initial install/recovery: already in physical BOOTSEL')
    parser.add_argument('--image', type=Path, default=IMAGE)
    parser.add_argument('--timeout', type=int, default=25)
    args = parser.parse_args(argv)
    if os.geteuid() == 0:
        raise RuntimeError('Run as a normal user with robot-device membership; do not sudo flash.')
    if not 1 <= args.timeout <= 120:
        raise ValueError('--timeout must be 1..120 seconds.')
    binary = tool_path()
    image = args.image.resolve(strict=True)
    image_info = validate_uf2(image)
    if not HOST.is_file() or not os.access(HOST, os.X_OK):
        raise RuntimeError('Build the Linux USB host first: bash firmware/build-pico-device.sh')
    manifest = json.loads(image.with_name('build-info.json').read_text(encoding='utf-8-sig'))
    if manifest.get('host_sha256') != digest(HOST):
        raise RuntimeError('Linux host differs from image build manifest. Run bash firmware/build-pico-device.sh.')
    if args.check:
        print(json.dumps({'at_utc': now(), 'environment_ready': True, 'image': image_info,
                          'devices': inventory(), 'flash_written': False,
                          'note': '--port accepts integrated c0de:cafc CDC only. Other variants may support picotool USB reset; VID/PID does not identify firmware age.'}, indent=2))
        return
    # Prevent two copies of this updater running for this user across checkouts.
    cache = Path.home() / '.cache/300seconds'
    cache.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (cache / 'pico-flash.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        directory = REPO / 'tmp/pico-flash' / datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ-linux')
        directory.mkdir(parents=True, mode=0o700)
        directory.chmod(0o700)
        log = directory / 'commands.log'
        result = {'started_utc': now(), 'image': image_info, 'flash_verified': False,
                  'application_status_verified': False, 'completed': False}
        try:
            # Freeze validated bytes; an editor/rebuild cannot change the image mid-upgrade.
            frozen = directory / 'firmware.uf2'
            shutil.copyfile(image, frozen)
            frozen.chmod(0o400)
            if validate_uf2(frozen, metadata=False) != image_info:
                raise RuntimeError('UF2 changed during staging.')
            expected_serial = None
            if args.port:
                current = cdc_device(args.port)  # Reject legacy before touching CDC.
                expected_serial = current['serial']
                if not expected_serial or roms():
                    raise RuntimeError('Require stable app serial and no other connected BOOTSEL device.')
                # Do not stop an unknown USB owner/service behind its back.
                busy = subprocess.run(['fuser', str(Path(args.port).resolve())], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if busy.returncode != 1 or busy.stderr.strip():
                    raise RuntimeError('Port is busy or owner check failed. Stop the USB bridge/terminal first.')
                result['before_status'] = status(args.port, log)
                output = run([HOST, '--port', args.port, 'bootloader'], timeout=20, log=log)
                if not re.search(r'^OK BOOTLOADER\s*$', output, re.M):
                    raise RuntimeError('STOP/Bootloader Ack was not verified; no flash load requested.')
                wait_for(lambda: bool(roms()), args.timeout)
            device = one_rom(expected_serial)
            result['rom'] = device
            info = run([binary, 'info', '-d'] + selection(device), log=log)
            if not re.search(r'^\s*type:\s+RP2350\b', info, re.M | re.I):
                raise RuntimeError('picotool did not verify RP2350 identity.')
            same_rom(device)
            print('Saving existing 4 MiB flash before writing...', flush=True)
            backup = directory / 'previous-flash.bin'
            run([binary, 'save', '-r', '0x10000000', '0x10400000', backup] + selection(device), log=log)
            if backup.stat().st_size != 4 * 1024 * 1024:
                raise RuntimeError('Full flash backup size mismatch; no load requested.')
            backup.chmod(0o600)
            result['backup'] = {'path': str(backup), 'sha256': digest(backup)}
            same_rom(device)
            print('Loading and verifying RP2350 flash...', flush=True)
            run([binary, 'load', '-v', frozen] + selection(device), log=log)
            same_rom(device)
            run([binary, 'verify', frozen] + selection(device), log=log)
            result['flash_verified'] = True
            run([binary, 'reboot'] + selection(device), log=log)
            def find_app():
                apps = [d for d in inventory() if (d['vid'], d['pid']) == ('c0de', 'cafc')]
                if len(apps) > 1:
                    raise RuntimeError('Multiple integrated Pico devices; refusing to probe arbitrary CDC.')
                if len(apps) == 1 and apps[0]['serial'].lower() == device['serial'].lower():
                    for tty in Path('/sys/class/tty').glob('ttyACM*'):
                        if Path(apps[0]['sysfs']) in (tty / 'device').resolve().parents:
                            port = Path('/dev') / tty.name
                            if os.access(port, os.R_OK | os.W_OK):
                                return str(port)
            port = wait_for(find_app, args.timeout)
            result['status'] = status(port, log)
            result['application_port'] = port
            result['application_status_verified'] = True
            result['completed'] = True
            print('Flash readback and integrated CDC STATUS verified. No actuator test started.')
        except Exception as error:
            result['error'] = str(error)
            raise
        finally:
            result['finished_utc'] = now()
            save(directory / 'flash-result.json', result)
            print('Result: ' + str(directory / 'flash-result.json'), flush=True)


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else ''
    if command == 'record-tool':
        print(tool_path(record=True))
    elif command == 'tool-path':
        print(tool_path())
    elif command == 'record-image':
        info = validate_uf2(IMAGE, metadata=False)
        info.update({'at_utc': now(), 'rust': run(['rustc', '--version']).strip(),
                     'converter': 'picotool 2.3.1', 'picotool_sha256': digest(tool_path()),
                     'host_sha256': digest(HOST),
                     'git_head': run(['git', '-C', REPO, 'rev-parse', 'HEAD']).strip(),
                     'git_dirty': run(['git', '-C', REPO, 'status', '--porcelain', '--untracked-files=normal']).strip() != '',
                     'source_sha256': source_hashes()})
        save(IMAGE.with_name('build-info.json'), info)
        print(json.dumps(info, indent=2))
    elif command == 'flash':
        flash(sys.argv[2:])
    else:
        raise ValueError('Expected record-tool, tool-path, record-image or flash.')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('ERROR: ' + str(error), file=sys.stderr)
        sys.exit(1)
