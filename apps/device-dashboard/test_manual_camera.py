import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from learning import Learning
from learning_store import Store
from test_learning import CaptureTests, result


class ManualCameraTests(CaptureTests):
    def test_saved_and_environment_enable_are_ignored_on_restart(self):
        self.manager.store.set_setting('collection_enabled', True)
        with patch.dict(os.environ, {'LEARNING_AUTOSTART': '1'}):
            restored = Learning(self.cameras, Mock(), Mock(), Mock(), self.root / 'db')
        self.assertFalse(restored.enabled)

    def test_announcement_then_exactly_one_batch_while_disabled(self):
        feedback = Mock()
        self.manager.button_audio = feedback
        calls = []
        feedback.announce_camera.side_effect = lambda: calls.append('voice')
        async def describe(command):
            calls.append(command['op'])
            self.manager.running = False
            return result()
        async def scenario():
            await self.manager.camera_request({'index': 5})
            await self.manager.camera_request({'index': 5})
            self.assertEqual(self.manager.queue.qsize(), 1)
            with patch('learning.rpc', describe):
                await self.manager.analysis_loop()
        self.loop.run_until_complete(scenario())
        self.assertEqual(calls, ['voice', 'describe'])
        self.assertFalse(self.manager.enabled)
        self.assertFalse(self.manager.manual_busy)

    def test_failed_voice_or_changed_session_cannot_queue_analysis(self):
        feedback = Mock()
        self.manager.button_audio = feedback
        feedback.announce_camera.side_effect = RuntimeError('speaker absent')
        with self.assertRaises(RuntimeError):
            self.loop.run_until_complete(self.manager.camera_request({}))
        self.assertTrue(self.manager.queue.empty())
        self.assertFalse(self.manager.manual_busy)
        feedback.announce_camera.side_effect = None
        feedback.live_request_valid.return_value = False
        self.loop.run_until_complete(self.manager.camera_request({}))
        self.assertTrue(self.manager.queue.empty())
        self.assertFalse(self.manager.manual_busy)

    def test_unavailable_camera_does_not_queue_api_request(self):
        self.manager.button_audio = Mock()
        self.cameras.snapshot.side_effect = lambda: {'worker_alive': False, 'cameras': []}
        self.loop.run_until_complete(self.manager.camera_request({}))
        self.assertTrue(self.manager.queue.empty())
        self.assertFalse(self.manager.manual_busy)
