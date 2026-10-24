"""Regression checks for stale telemetry; no real devices are opened."""
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
import asyncio
from unittest.mock import AsyncMock, Mock, patch
from hardware import Cameras, EventLog, Pico


class TelemetryTests(unittest.TestCase):
    def test_servo_diagnostics_are_forwarded_without_starting_outputs(self):
        pico = Pico(EventLog())
        diagnostic = {'selected_address': 0, 'probes': [2, 3], 'sda_high': False, 'scl_high': True}
        process = Mock(stdout=iter([json.dumps({'event': 'servo_driver', 'status': diagnostic})]))
        pico.read(process)
        self.assertEqual(pico.snapshot()['servo_driver'], diagnostic)
        self.assertFalse(pico.snapshot()['connected'])
        self.assertIsNone(pico.snapshot()['outputs'])

    def test_expression_rejects_absent_matrix_and_unknown_preset_before_usb(self):
        import app
        from fastapi import HTTPException
        owner = Mock(start=AsyncMock())
        with patch.object(app.app.state, 'eyes', owner, create=True):
            with patch.dict(app.INSTALLATION, matrix_connected=False):
                with self.assertRaises(HTTPException) as caught:
                    asyncio.run(app.show_expression(app.EyeRequest(preset_id='neutral')))
                self.assertEqual(caught.exception.status_code, 409)
            with patch.dict(app.INSTALLATION, matrix_connected=True):
                with self.assertRaises(HTTPException) as caught:
                    asyncio.run(app.show_expression(app.EyeRequest(preset_id='not-a-preset')))
                self.assertEqual(caught.exception.status_code, 404)
            owner.start.assert_not_called()

    def test_expression_api_uses_catalog_id_and_bounded_duration(self):
        import app
        from pydantic import ValidationError
        for payload in ({'preset_id': 'neutral', 'seconds': 60},
                        {'preset_id': 'neutral', 'left': [255]*8}):
            with self.assertRaises(ValidationError):
                app.EyeRequest(**payload)
        owner = Mock(start=AsyncMock(return_value={'ok': True}))
        with patch.object(app.app.state, 'eyes', owner, create=True), patch.dict(app.INSTALLATION, matrix_connected=True):
            self.assertEqual(asyncio.run(app.show_expression(app.EyeRequest(preset_id='love', seconds=5))), {'ok': True})
            owner.start.assert_awaited_once_with('love', 5)

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
