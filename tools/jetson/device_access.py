#!/usr/bin/env python3
"""Board-specific least-privilege access for Pico, USB audio and CSI/GPU.

No world-writable device nodes, driver replacement, flashing or auto-start units.
The first file/group/account inventory is retained in a root-only directory.
"""
import json
import os
from pathlib import Path
import re
import sys

from jetson_mode import file_snapshot, run, save_json, now

STATE = Path('/var/lib/300seconds/device-access')
RULE = Path('/etc/udev/rules.d/99-z-300seconds-devices.rules')
ALSA = Path('/etc/alsa/conf.d/99-300seconds-usb.conf')
ACCOUNTS = {'pico': ['robot-device', 'dialout'],
            'audiod': ['audio'], 'camerad': ['video', 'render'],
            'jetson': ['audio', 'video', 'render', 'dialout', 'robot-device']}

RULE_TEXT = '''# 300seconds: specific Pico firmwares, not all serial/USB devices.
# Integrated binary firmware and legacy NeoPixel firmware have different aliases.
SUBSYSTEM=="tty", ATTRS{idVendor}=="c0de", ATTRS{idProduct}=="cafc", GROUP="robot-device", MODE="0660", TAG+="uaccess", SYMLINK+="pico-device"
SUBSYSTEM=="tty", ATTRS{idVendor}=="c0de", ATTRS{idProduct}=="caff", GROUP="robot-device", MODE="0660", TAG+="uaccess", SYMLINK+="pico-neopixel"
SUBSYSTEM=="usb", ENV{DEVTYPE}=="usb_device", ATTR{idVendor}=="c0de", ATTR{idProduct}=="caf[cf]", GROUP="robot-device", MODE="0660"
# RP2350 ROM BOOTSEL only; do not grant access to unrelated Raspberry Pi USBs.
SUBSYSTEM=="usb", ENV{DEVTYPE}=="usb_device", ATTR{idVendor}=="2e8a", ATTR{idProduct}=="000f", GROUP="robot-device", MODE="0660", TAG+="uaccess"
# Keep standard audio/video groups so existing desktop clients retain access.
SUBSYSTEM=="sound", ATTRS{idVendor}=="0d8c", ATTRS{idProduct}=="0014", GROUP="audio", MODE="0660", TAG+="uaccess"
SUBSYSTEM=="video4linux", KERNEL=="video[0-9]*", GROUP="video", MODE="0660", TAG+="uaccess"
SUBSYSTEM=="media", KERNEL=="media[0-9]*", GROUP="video", MODE="0660"
'''


def audio_card():
    matches = []
    for card in sorted(Path('/sys/class/sound').glob('card[0-9]*')):
        for parent in [card.resolve()] + list(card.resolve().parents):
            if (parent / 'idVendor').is_file() and (parent / 'idProduct').is_file():
                if (parent / 'idVendor').read_text().strip() == '0d8c' and (parent / 'idProduct').read_text().strip() == '0014':
                    matches.append({'card': card.name, 'alsa_id': (card / 'id').read_text().strip()})
                break
    if len(matches) != 1:
        raise RuntimeError('Expected exactly one C-Media 0d8c:0014 audio card: ' + json.dumps(matches))
    if not re.fullmatch(r'[A-Za-z0-9_]+', matches[0]['alsa_id']):
        raise RuntimeError('Unexpected ALSA card ID.')
    return matches[0]


def main():
    if os.geteuid() != 0 or sys.argv[1:] != ['configure']:
        raise SystemExit('Use sudo configure-device-access.sh')
    card = audio_card()  # Refuse guessed global-default changes when no adapter exists.
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    STATE.chmod(0o700)
    if not (STATE / 'baseline.json').exists():
        baseline = {'at_utc': now(), 'files': [file_snapshot(RULE), file_snapshot(ALSA)],
                    'accounts': {name: run('id', name, check=False).stdout for name in ACCOUNTS},
                    'groups': {name: run('getent', 'group', name, check=False).stdout
                               for name in ['audio', 'video', 'render', 'dialout', 'robot-device']}}
        save_json(STATE / 'baseline.json', baseline)
    if run('getent', 'group', 'robot-device', check=False).returncode:
        run('groupadd', '--system', 'robot-device')
    for user, groups in ACCOUNTS.items():
        if run('id', '-u', user, check=False).returncode:
            if user == 'jetson':
                raise RuntimeError('Expected existing jetson user.')
            run('useradd', '--system', '--user-group', '--no-create-home',
                '--home-dir', '/nonexistent', '--shell', '/usr/sbin/nologin', user)
        available = [g for g in groups if run('getent', 'group', g, check=False).returncode == 0]
        run('usermod', '--append', '--groups', ','.join(available), user)
        if user != 'jetson':
            home = Path('/var/lib/300seconds') / user
            home.mkdir(mode=0o700, exist_ok=True)
            run('chown', user + ':' + user, str(home))
            home.chmod(0o700)
            run('usermod', '--home', str(home), user)
            # ALSA's PulseAudio config hook can inspect HOME even for explicit
            # hardware PCMs. A writable home avoids warnings; no daemon is spawned.
            pulse = home / '.config/pulse'
            pulse.mkdir(parents=True, exist_ok=True, mode=0o700)
            client = pulse / 'client.conf'
            if not client.exists():
                client.write_text('autospawn = no\n', encoding='ascii')
            for p in (home / '.config', pulse, client):
                run('chown', user + ':' + user, str(p))
            client.chmod(0o600)
    RULE.write_text(RULE_TEXT, encoding='ascii')
    RULE.chmod(0o644)
    ALSA.parent.mkdir(parents=True, exist_ok=True)
    # Explicit named PCMs bypass the desktop PulseAudio default; one audiod owns
    # the USB device. CARD name survives ALSA card-number changes.
    ALSA.write_text('''# 300seconds USB audio; global/default PCM is unchanged.
pcm.robot_capture {
    type plug
    slave { pcm "hw:CARD=%s,DEV=0" format S16_LE rate 48000 channels 1 }
}
pcm.robot_playback {
    type plug
    slave { pcm "hw:CARD=%s,DEV=0" format S16_LE rate 48000 channels 2 }
}
ctl.robot_usb { type hw card "%s" }
''' % (card['alsa_id'], card['alsa_id'], card['alsa_id']), encoding='ascii')
    ALSA.chmod(0o644)
    run('udevadm', 'control', '--reload-rules')
    # change events update permissions/links; no USB reset/rebind or device open.
    for subsystem in ('tty', 'sound', 'video4linux', 'media'):
        args = ['udevadm', 'trigger', '--action=change', '--subsystem-match=' + subsystem]
        if subsystem == 'tty':
            args.append('--sysname-match=ttyACM*')
        run(*args)
    run('udevadm', 'trigger', '--action=change', '--subsystem-match=usb', '--attr-match=idVendor=c0de')
    run('udevadm', 'trigger', '--action=change', '--subsystem-match=usb', '--attr-match=idVendor=2e8a', '--attr-match=idProduct=000f')
    run('udevadm', 'settle', '--timeout=15')
    result = {'at_utc': now(), 'audio_card': card,
              'accounts': {user: run('id', user).stdout.strip() for user in ACCOUNTS},
              'rules': str(RULE), 'alsa_config': str(ALSA),
              'baseline': str(STATE / 'baseline.json')}
    save_json(STATE / 'last-result.json', result)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
