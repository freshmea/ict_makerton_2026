"""Regression checks for stale telemetry; no real devices are opened."""
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
import asyncio
from unittest.mock import Mock, patch
from hardware import Cameras, EventLog, Pico


class TelemetryTests(unittest.TestCase):
    def test_missing_matrix_is_rejected_before_usb_command(self):
        import app
        from fastapi import HTTPException
        owner = Mock()
        with patch.object(app.app.state, 'pico', owner, create=True), patch.dict(app.INSTALLATION, matrix_connected=False):
            for module in ('matrix', 'all'):
                with self.assertRaises(HTTPException) as caught:
                    asyncio.run(app.pico_command(app.PicoRequest(cmd='test', module=module)))
                self.assertEqual(caught.exception.status_code, 409)
            owner.command.assert_not_called()

    def test_pico_old_sample_is_never_connected(self):
        pico = Pico(EventLog())
        pico.process = Mock(); pico.process.poll.return_value = None
        pico.received = time.monotonic() - 2
        self.assertFalse(pico.snapshot()['connected'])
        pico.received = time.monotonic()
        self.assertTrue(pico.snapshot()['connected'])
        pico.process.poll.return_value = 1
        self.assertFalse(pico.snapshot()['connected'])

    def test_camera_previous_generation_is_never_live(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict(os.environ, DASHBOARD_SETTINGS=str(root / 'settings.json')):
                cameras = Cameras(root, EventLog())
            cameras.run_id = 'new'
            cameras.process = Mock(); cameras.process.poll.return_value = None
            payload = {'run_id': 'old', 'updated_monotonic': time.monotonic(), 'cameras': [{'ready': True}, {'ready': True}]}
            (root / 'camera-state.json').write_text(json.dumps(payload))
            self.assertFalse(cameras.snapshot()['ready'])
            payload['run_id'] = 'new'; payload['updated_monotonic'] = time.monotonic() - 3
            (root / 'camera-state.json').write_text(json.dumps(payload))
            self.assertFalse(cameras.snapshot()['ready'])
            self.assertTrue(all(not c['ready'] for c in cameras.snapshot()['cameras']))
            payload['updated_monotonic'] = time.monotonic()
            (root / 'camera-state.json').write_text(json.dumps(payload))
            self.assertTrue(cameras.snapshot()['ready'])


if __name__ == '__main__': unittest.main()
