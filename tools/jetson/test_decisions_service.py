import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

import study_observer_service as service


class OperationalTests(unittest.IsolatedAsyncioTestCase):
    async def test_decisions_provider_error_remains_a_visible_error(self):
        with tempfile.TemporaryDirectory() as folder:
            old=Mock(status=lambda:{'attempts':0,'max_attempts':5,'cooldown_until_unix':0})
            manager=service.Manager({'OPENAI_API_KEY':'test'},state=Path(folder),runtime=Path(folder),budget=old)
            with patch.object(service.window,'capture',return_value=([{}]*20,'generation')), \
                    patch.object(service.window,'analyze',side_effect=service.window.openai.Error('openai_http_429')):
                await manager.start('decisions',0)
                await manager.task
            self.assertEqual(manager.job['phase'],'failed')
            self.assertEqual(manager.job['error_code'],'openai_http_429')

    async def test_decisions_twenty_frames_are_available_when_old_five_tests_are_exhausted(self):
        with tempfile.TemporaryDirectory() as folder:
            old=Mock(status=lambda:{'attempts':5,'max_attempts':5,'cooldown_until_unix':0})
            manager=service.Manager({'OPENAI_API_KEY':'test'},state=Path(folder),runtime=Path(folder),budget=old)
            self.assertFalse(manager.providers()['openai']['available'])
            self.assertTrue(manager.providers()['decisions']['available'])
            with patch.object(service.window,'capture',return_value=([{}]*20,'test-generation')) as capture, \
                    patch.object(service.window,'analyze',return_value={'status':'ok','model':'test'}) as analyze, \
                    patch.object(service.window.jev,'metadata',return_value=[]):
                state=await manager.start('decisions',1)
                self.assertEqual(state['job']['total'],20)
                await manager.task
            self.assertIs(capture.call_args.args[-1],True)
            self.assertIs(analyze.call_args.args[-1],manager.decisions_budget)
            self.assertEqual(manager.job['phase'],'completed')
            self.assertEqual(manager.job['result']['frames_per_camera'],10)
            self.assertEqual(manager.job['result']['cameras'],[{'sensor_id':1,'role':'face'},{'sensor_id':0,'role':'study_area'}])
