"""Audio amplitude, PCM integrity and saved-setting regressions; no devices."""
import asyncio
import io
import json
import math
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
import wave

import numpy as np

from hardware import Audio, EventLog


def tone(peak_dbfs=-24, seconds=3):
    phase = np.arange(round(Audio.RATE * seconds)) * (2 * np.pi * 440 / Audio.RATE)
    return np.rint(np.sin(phase) * 32767 * 10 ** (peak_dbfs / 20)).astype('<i2').tobytes()


class AudioTests(unittest.TestCase):
    def test_tts_boosts_the_played_pcm_and_preserves_microphone_gain(self):
        with patch.dict(os.environ, DASHBOARD_AUDIO_SETTINGS='missing-audio-settings.json'):
            audio = Audio(EventLog())
        source = tone(-24, seconds=.1)
        metadata = {'requested_characters': 2, 'provider': 'typecast'}
        with patch('hardware.synthesize', return_value=(Audio.wav(source), metadata)), \
                patch('hardware.subprocess.run', return_value=Mock(returncode=0, stdout=b'')) as play:
            result = audio.tts('안녕')
        with wave.open(io.BytesIO(play.call_args.kwargs['input']), 'rb') as reader:
            actual = reader.readframes(reader.getnframes())
        self.assertEqual(actual, Audio.process_pcm(source, 6)[0])
        self.assertEqual(audio.gain_db, 12)
        self.assertEqual(play.call_args.kwargs['timeout'], 35)
        self.assertTrue(result['speaker']['last_result']['ok'])

    def test_tts_and_test_tone_cannot_overlap_or_spend_credits_while_busy(self):
        audio = Audio(EventLog())
        audio.play_lock.acquire()
        try:
            with patch('hardware.synthesize') as synthesize:
                with self.assertRaises(RuntimeError): audio.tts('안녕')
                with self.assertRaises(RuntimeError): audio.playback('tone')
                synthesize.assert_not_called()
        finally:
            audio.play_lock.release()

    def test_tts_error_releases_lock_and_reports_failure(self):
        audio = Audio(EventLog())
        with patch('hardware.synthesize', side_effect=RuntimeError('TTS quota')):
            with self.assertRaisesRegex(RuntimeError, 'quota'): audio.tts('안녕')
        self.assertFalse(audio.speaker['last_result']['ok'])
        self.assertFalse(audio.play_lock.locked())

    def test_tts_validation_rejects_empty_long_extra_fields_and_control_characters(self):
        import app
        from pydantic import ValidationError
        for payload in ({'text': ''}, {'text': '   '}, {'text': '가' * 241},
                        {'text': '🙂' * 121}, {'text': 'a\0b'}, {'text': 'hi', 'voice': 'x'}):
            with self.assertRaises(ValidationError): app.TTSRequest(**payload)
        self.assertEqual(app.TTSRequest(text=' 안녕\n하세요 ').text, '안녕\n하세요')

    def test_tts_api_maps_service_errors_and_uses_validated_text(self):
        import app
        from fastapi import HTTPException
        owner = Mock()
        owner.tts.return_value = {'speaker': {'state': 'idle'}}
        with patch.object(app.app.state, 'audio', owner, create=True):
            self.assertEqual(asyncio.run(app.play_tts(app.TTSRequest(text=' 안녕 '))), owner.tts.return_value)
            owner.tts.assert_called_once_with('안녕')
            owner.tts.side_effect = RuntimeError('TTS quota')
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(app.play_tts(app.TTSRequest(text='안녕')))
            self.assertEqual(caught.exception.status_code, 409)

    def test_quiet_voice_gets_requested_gain_in_the_actual_pcm(self):
        source = tone()
        processed, level = Audio.process_pcm(source, 12)
        before = np.frombuffer(source, dtype='<i2').astype(np.float32)
        after = np.frombuffer(processed, dtype='<i2').astype(np.float32)
        self.assertEqual(len(source), len(processed))
        self.assertTrue(np.allclose(after, before * 10 ** (12 / 20), atol=1))
        self.assertAlmostEqual(level['raw_peak_dbfs'], -24, places=1)
        self.assertAlmostEqual(level['peak_dbfs'], -12, places=1)
        self.assertAlmostEqual(level['rms_dbfs'] - level['raw_rms_dbfs'], 12, places=1)
        self.assertFalse(level['limiter_active'])

    def test_loud_voice_is_linearly_limited_without_wrap_or_flat_tops(self):
        source = tone(-6)
        processed, level = Audio.process_pcm(source, 30)
        before = np.frombuffer(source, dtype='<i2').astype(np.float64)
        after = np.frombuffer(processed, dtype='<i2').astype(np.float64)
        ceiling = math.floor(32767 * 10 ** (-1 / 20))
        expected_gain = ceiling / max(abs(before))
        self.assertTrue(np.allclose(after, before * expected_gain, atol=1))
        self.assertLessEqual(max(abs(after)), ceiling)
        self.assertTrue(np.all(after[before > 0] >= 0))
        self.assertTrue(np.all(after[before < 0] <= 0))
        self.assertTrue(level['limiter_active'])
        self.assertAlmostEqual(level['peak_dbfs'], -1, places=1)

    def test_full_scale_and_negative_int16_extreme_remain_safe(self):
        source = np.array([-32768, -20000, 0, 20000, 32767], dtype='<i2').tobytes()
        processed, level = Audio.process_pcm(source, 30)
        output = np.frombuffer(processed, dtype='<i2').astype(np.int32)
        self.assertLessEqual(max(abs(output)), 29204)
        self.assertLess(output[0], 0)
        self.assertGreater(output[-1], 0)
        self.assertLessEqual(level['peak_dbfs'], -1)

    def test_silence_and_empty_buffer_are_finite_and_not_normalized_to_noise(self):
        for source in (b'', bytes(9600)):
            processed, level = Audio.process_pcm(source, 30)
            self.assertEqual(processed, source)
            self.assertEqual(level['rms_dbfs'], -96)
            self.assertEqual(level['peak_dbfs'], -96)
            self.assertFalse(level['limiter_active'])
            json.dumps(level, allow_nan=False)
        quiet = tone(-60)
        _, level = Audio.process_pcm(quiet, 12)
        self.assertLess(level['peak_dbfs'], -47)

    def test_zero_gain_preserves_unlimited_pcm(self):
        source = tone(-12)
        output, level = Audio.process_pcm(source, 0)
        self.assertEqual(output, source)
        self.assertEqual(level['applied_gain_db'], 0)

    def test_invalid_gain_is_rejected(self):
        for gain in (-1, 31, float('nan'), float('inf'), 'invalid'):
            with self.assertRaises(ValueError):
                Audio.process_pcm(tone(seconds=.01), gain)

    def test_wav_meter_and_replay_use_processed_pcm_once(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, DASHBOARD_AUDIO_SETTINGS=str(Path(directory) / 'audio.json')):
                audio = Audio(EventLog())
            raw = tone(-24)
            audio.ring.append(raw)
            audio.last_pcm = time.monotonic()
            state = audio.snapshot()
            with wave.open(io.BytesIO(audio.recording()), 'rb') as reader:
                self.assertEqual((reader.getframerate(), reader.getnchannels(), reader.getsampwidth()),
                                 (48000, 1, 2))
                actual = reader.readframes(reader.getnframes())
            expected, _ = Audio.process_pcm(raw, 12)
            self.assertEqual(actual, expected)
            self.assertEqual(audio.ring[0], raw)
            self.assertAlmostEqual(state['peak_dbfs'], -12, places=1)
            result = Mock(returncode=0, stdout=b'')
            with patch('hardware.subprocess.run', return_value=result) as play:
                audio.playback('replay')
            with wave.open(io.BytesIO(play.call_args.kwargs['input']), 'rb') as reader:
                self.assertEqual(reader.readframes(reader.getnframes()),
                                 Audio.process_pcm(raw[-2 * Audio.RATE * 2:], 12)[0])

    def test_settings_survive_restart_and_failed_save_keeps_previous_gain(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Path(directory) / 'audio.json'
            with patch.dict(os.environ, DASHBOARD_AUDIO_SETTINGS=str(settings)):
                audio = Audio(EventLog())
                self.assertEqual(audio.gain_db, 12)
                audio.set_gain(18)
                self.assertEqual(Audio(EventLog()).gain_db, 18)
                with patch('hardware.write_json', side_effect=OSError('disk full')):
                    with self.assertRaises(OSError):
                        audio.set_gain(24)
                self.assertEqual(audio.gain_db, 18)
                settings.write_text('{"gain_db": 999}')
                self.assertEqual(Audio(EventLog()).gain_db, 12)

    def test_stale_audio_cannot_be_exported(self):
        with patch.dict(os.environ, DASHBOARD_AUDIO_SETTINGS='missing-audio-settings.json'):
            audio = Audio(EventLog())
        audio.ring.append(tone(seconds=.1))
        audio.last_pcm = time.monotonic() - 2
        self.assertFalse(audio.snapshot()['connected'])
        with self.assertRaises(RuntimeError):
            audio.recording()

    def test_settings_api_rejects_invalid_values_and_passes_valid_gain(self):
        import app
        from pydantic import ValidationError
        for payload in ({'gain_db': -1}, {'gain_db': 31}, {'gain_db': float('nan')},
                        {'gain_db': float('inf')}, {'gain_db': 12, 'device': 'other'}):
            with self.assertRaises(ValidationError):
                app.AudioSettingsRequest(**payload)
        owner = Mock()
        owner.set_gain.return_value = {'gain_db': 18}
        with patch.object(app.app.state, 'audio', owner, create=True):
            self.assertEqual(asyncio.run(app.audio_settings(app.AudioSettingsRequest(gain_db=18))),
                             {'gain_db': 18})
        owner.set_gain.assert_called_once_with(18)


if __name__ == '__main__':
    unittest.main()
