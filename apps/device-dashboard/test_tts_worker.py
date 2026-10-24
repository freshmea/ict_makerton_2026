"""Synthesis boundary checks; no provider requests or audio devices."""
import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

import tts_worker


class WorkerTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_text_is_rejected_before_provider_start(self):
        with patch('tts_worker.asyncio.create_subprocess_exec') as start:
            for value in ('', ' ', '가' * 241, '🙂' * 121, 'a\0b', None):
                with self.assertRaises(ValueError): await tts_worker.synthesize(value)
            start.assert_not_called()

    async def test_timeout_kills_provider_and_removes_private_temp_files(self):
        process = Mock(returncode=None)
        process.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
        process.wait = AsyncMock()
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(tts_worker, 'SOCKET', Path(folder) / 'tts.sock'), \
                    patch('tts_worker.asyncio.create_subprocess_exec', AsyncMock(return_value=process)):
                with self.assertRaises(asyncio.TimeoutError): await tts_worker.synthesize('안녕')
            self.assertEqual(list(Path(folder).iterdir()), [])
        process.kill.assert_called_once()
        process.wait.assert_awaited_once()

    async def test_provider_failure_is_sanitized_and_files_are_removed(self):
        process = Mock(returncode=1)
        process.communicate = AsyncMock(return_value=(b'private details HTTP 429', None))
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(tts_worker, 'SOCKET', Path(folder) / 'tts.sock'), \
                    patch('tts_worker.asyncio.create_subprocess_exec', AsyncMock(return_value=process)) as start:
                with self.assertRaisesRegex(RuntimeError, '동시 요청 한도'):
                    await tts_worker.synthesize('문장; $(literal)')
                self.assertEqual(start.call_args.args[-1], '문장; $(literal)')
            self.assertEqual(list(Path(folder).iterdir()), [])
        process.kill.assert_not_called()

    async def test_network_failures_show_the_stage_and_no_fixed_cooldown(self):
        for code, label in [('dns', 'DNS'), ('connect', '서버 연결'), ('timeout', '시간 초과'),
                            ('tls', 'TLS'), ('connection_lost', '연결 끊김')]:
            message = tts_worker.provider_error('Typecast transport %s; curl_exit=28' % code)
            self.assertIn(label, message)
            self.assertIn('고정 대기 없이', message)


if __name__ == '__main__':
    unittest.main()
