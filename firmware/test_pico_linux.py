#!/usr/bin/env python3
"""Updater safety checks. No USB hardware is opened or written."""
import json
import io
from contextlib import redirect_stdout
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import pico_linux as pico


def block(number, address):
    data = bytearray(512)
    struct.pack_into('<8I', data, 0, 0x0a324655, 0x9e5d5157, 0x2000,
                     address, 256, number, 2, 0xe48bff59)
    struct.pack_into('<I', data, 508, 0x0ab16f30)
    return data


class UpdaterSafety(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.image = Path(self.temp.name) / 'firmware.uf2'
        self.original = block(0, 0x10000000) + block(1, 0x10000100)
        self.image.write_bytes(self.original)
        self.info = pico.validate_uf2(self.image, metadata=False)
        self.image.with_name('build-info.json').write_text(json.dumps(self.info))

    def test_valid_image_and_manifest(self):
        self.assertEqual(pico.validate_uf2(self.image), self.info)

    def test_payload_change_rejected_by_hash(self):
        self.original[40] ^= 1
        self.image.write_bytes(self.original)
        with self.assertRaisesRegex(ValueError, 'build-info'):
            pico.validate_uf2(self.image)

    def test_rp2040_image_rejected(self):
        struct.pack_into('<I', self.original, 28, 0xe48bff56)
        self.image.write_bytes(self.original)
        with self.assertRaisesRegex(ValueError, 'RP2350'):
            pico.validate_uf2(self.image, metadata=False)

    def test_out_of_flash_rejected(self):
        struct.pack_into('<I', self.original, 12, 0x10400000)
        self.image.write_bytes(self.original)
        with self.assertRaisesRegex(ValueError, '4 MiB'):
            pico.validate_uf2(self.image, metadata=False)

    def test_duplicate_block_rejected(self):
        struct.pack_into('<I', self.original, 512 + 20, 0)
        self.image.write_bytes(self.original)
        with self.assertRaisesRegex(ValueError, 'numbering'):
            pico.validate_uf2(self.image, metadata=False)

    def test_overlapping_flash_rejected(self):
        struct.pack_into('<I', self.original, 512 + 12, 0x10000080)
        self.image.write_bytes(self.original)
        with self.assertRaisesRegex(ValueError, 'Overlapping'):
            pico.validate_uf2(self.image, metadata=False)

    def test_multiple_roms_rejected(self):
        with patch.object(pico, 'roms', return_value=[{'pid': '000f'}] * 2):
            with self.assertRaisesRegex(RuntimeError, 'exactly one'):
                pico.one_rom()

    def test_other_board_serial_rejected(self):
        with patch.object(pico, 'roms', return_value=[{'pid': '000f', 'serial': 'other'}]):
            with self.assertRaisesRegex(RuntimeError, 'serial differs'):
                pico.one_rom('selected')

    def test_bootsel_permission_rejected(self):
        with patch.object(pico, 'roms', return_value=[{'pid': '000f', 'serial': 'chip', 'read_write': False}]):
            with self.assertRaisesRegex(RuntimeError, 'permission denied'):
                pico.one_rom('chip')

    def test_stale_linux_host_rejected_before_usb_inventory(self):
        host = Path(self.temp.name) / 'host'
        host.write_bytes(b'changed native host')
        host.chmod(0o755)
        with patch.object(pico, 'HOST', host), patch.object(pico, 'tool_path'), \
                patch.object(pico.os, 'geteuid', return_value=1000), patch.object(pico, 'inventory') as devices:
            with self.assertRaisesRegex(RuntimeError, 'host differs'):
                pico.flash(['--check', '--image', str(self.image)])
            devices.assert_not_called()

    def test_check_mode_never_runs_a_device_command(self):
        host = Path(self.temp.name) / 'host'
        host.write_bytes(b'native host')
        host.chmod(0o755)
        self.info['host_sha256'] = pico.digest(host)
        self.image.with_name('build-info.json').write_text(json.dumps(self.info))
        output = io.StringIO()
        with patch.object(pico, 'HOST', host), patch.object(pico, 'tool_path'), \
                patch.object(pico.os, 'geteuid', return_value=1000), patch.object(pico, 'inventory', return_value=[]), \
                patch.object(pico, 'run') as command, redirect_stdout(output):
            pico.flash(['--check', '--image', str(self.image)])
            command.assert_not_called()
        result = json.loads(output.getvalue())
        self.assertTrue(result['environment_ready'])
        self.assertFalse(result['flash_written'])


if __name__ == '__main__':
    unittest.main()
