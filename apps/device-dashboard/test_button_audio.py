"""Fresh firmware events, bounded queues, cached assets, gentle tones and Live coexistence."""
import io
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch
import wave

import numpy as np

from button_audio import ButtonAudio, beep, pitch, wav, live_tone, RATE
from build_button_audio import prepare
from hardware import Audio, EventLog, Pico


def pcm(data):
    with wave.open(io.BytesIO(data), 'rb') as reader:
        return np.frombuffer(reader.readframes(reader.getnframes()), dtype='<i2')


class ButtonTests(unittest.TestCase):
    def setUp(self):
        self.state = {'connected': True, 'session': 'usb-a', 'device': {'uptime_ms': 1000}}
        self.pico = Mock(snapshot=lambda: self.state)
        self.audio = Mock()
        self.events = EventLog()
        self.feedback = ButtonAudio(self.pico, self.audio, self.events)
        self.feedback.running = True
        self.seq = 0

    def event(self, index=1, kind='Pressed', count=0, **overrides):
        self.seq += 1
        packet = {'session': self.state['session'], 'host_unix_ms': time.time() * 1000,
                  'touch': dict(index=index, kind=kind, interval_count=count,
                                event_seq=self.seq, uptime_ms=1000, pressed=kind != 'Released')}
        packet.update(overrides)
        self.feedback.on_touch(packet)
        return packet

    def test_all_six_presses_then_each_count_use_firmware_events(self):
        for index in range(1, 7):
            self.event(index)
            self.event(index, 'Interval', 1)
            self.event(index, 'WindowClosed', 1)
            self.event(index, 'Interval', 2)
        self.assertEqual(self.feedback.counters['press_events'], 6)
        self.assertEqual(self.feedback.counters['count_events'], 12)
        self.assertEqual([x[2] for x in self.feedback.queues['label']], list(range(1, 7)))

    def test_release_and_fresh_press_reset_pitch(self):
        self.event(3); self.event(3, kind='Interval', count=9)
        self.event(3, kind='Released', count=9)
        self.event(3, kind='Interval', count=10)  # never beep on an unpaired hold
        self.event(3); self.event(3, kind='Interval', count=1)
        self.assertEqual([x[3] for x in self.feedback.queues['beep']], [9, 1])

    def test_repeated_counts_and_duplicate_packets_never_replay(self):
        packet = self.event()
        self.feedback.on_touch(packet)
        self.event(kind='Interval', count=1)
        self.event(kind='Interval', count=1)
        self.event(kind='Interval', count=0)
        self.assertEqual(self.feedback.counters['press_events'], 1)
        self.assertEqual(self.feedback.counters['count_events'], 1)

    def test_stale_buffer_disconnected_and_other_session_are_rejected(self):
        self.event(host_unix_ms=(time.time() - 4) * 1000)
        self.event(session='old-usb')
        self.state['device']['uptime_ms'] = 10000
        self.event()
        self.state['connected'] = False
        self.event()
        self.assertEqual(self.feedback.counters['press_events'], 0)
        self.assertEqual(self.feedback.counters['rejected'], 4)

    def test_reconnect_clears_pending_and_does_not_sound_an_existing_hold(self):
        self.event(2)
        self.state['session'] = 'usb-b'
        self.event(kind='Interval', count=5)
        self.assertFalse(self.feedback.queues['label'])
        self.assertFalse(self.feedback.queues['beep'])
        self.event(2)
        self.assertEqual(len(self.feedback.queues['label']), 1)

    def test_uint32_event_sequence_wrap(self):
        self.seq = 0xfffffffe
        self.event()
        self.seq = -1
        self.event(index=2)
        self.assertEqual(self.feedback.counters['press_events'], 2)

    def test_usb_reader_delivers_every_touch_without_snapshot_polling_loss(self):
        pico = Pico(self.events)
        feedback = ButtonAudio(pico, self.audio, self.events)
        feedback.running = True
        packets = [dict(event='status', session='usb-a', status={'uptime_ms': 1000})]
        sequence = 0
        for index in range(1, 7):
            for kind, count in [('Pressed', 0), ('Interval', 1), ('Interval', 2), ('Released', 2)]:
                sequence += 1
                packets.append(dict(event='touch', session='usb-a', host_unix_ms=time.time() * 1000,
                                    touch=dict(index=index, kind=kind, event_seq=sequence,
                                               interval_count=count, uptime_ms=1000,
                                               pressed=kind != 'Released')))
        process = Mock(stdout=io.StringIO('\n'.join(json.dumps(p) for p in packets)),
                       poll=lambda: None, wait=lambda: 0)
        pico.process = process
        remove = pico.subscribe_touch(feedback.on_touch)
        pico.read(process)
        remove()
        self.assertEqual(feedback.counters['press_events'], 6)
        self.assertEqual(feedback.counters['count_events'], 12)

    def test_queues_bounded_and_expired_feedback_dropped(self):
        for _ in range(30): self.event(2)
        self.assertEqual(len(self.feedback.queues['label']), 12)
        self.assertEqual(self.feedback.counters['dropped'], 18)
        self.feedback.queues['label'].clear()
        self.feedback.queues['label'].append((time.monotonic() - 4, 'usb-a', 1, 0))
        self.assertIsNone(self.feedback.take('label'))
        self.assertEqual(self.feedback.counters['dropped'], 19)

    def test_loader_checks_mp3_and_decoded_cache_hashes(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            manifest = {'buttons': {}, 'extras': {}}
            for index in range(1, 7):
                values = {'mp3': b'encoded-mp3-fixture', 'wav': beep([1])}
                manifest['buttons'][str(index)] = {'text': '일번' if index == 1 else '번호'}
                for ext, data in values.items():
                    (directory / ('button-%d.%s' % (index, ext))).write_bytes(data)
                    manifest['buttons'][str(index)][ext + '_sha256'] = hashlib.sha256(data).hexdigest()
            for stem, text in [('live-start', '라이브 대화 시작'), ('live-end', '라이브 대화 끝')]:
                item = {'text': text}
                for ext, data in values.items():
                    (directory / (stem + '.' + ext)).write_bytes(data)
                    item[ext + '_sha256'] = hashlib.sha256(data).hexdigest()
                manifest['extras'][stem] = item
            (directory / 'manifest.json').write_text(json.dumps(manifest))
            self.feedback.directory = directory
            self.feedback.load()
            self.assertEqual(len(self.feedback.assets), 6)
            (directory / 'button-3.mp3').write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError, 'checksum'): self.feedback.load()

    def test_sw1_short_press_queues_number_but_does_not_request_live(self):
        for _ in range(6):
            self.event()
            for count in range(1, 4): self.event(kind='Interval', count=count)
            self.event(kind='Released', count=3)
            self.assertIsNone(self.feedback.take_live_request())
        self.assertEqual(len(self.feedback.queues['label']), 6)
        self.assertEqual(self.feedback.counters['live_hold_requests'], 0)

    def start_feedback(self):
        self.feedback.assets = {i: wav(b'\x01\x00' * 100) for i in range(1, 7)}
        with patch.object(self.feedback, 'load'):
            self.feedback.start()
        self.addCleanup(self.feedback.close)

    def wait_counter(self, key, count):
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            if self.feedback.snapshot()[key] == count:
                return
            time.sleep(.005)
        self.fail(str(self.feedback.snapshot()))

    def test_sw1_number_is_immediate_and_fourth_beep_finishes_before_live_request(self):
        fourth, release = threading.Event(), threading.Event()
        calls = []
        def playback(data):
            calls.append(data)
            if len(calls) == 5:  # number, then ticks 1..4
                fourth.set()
                release.wait(2)
        self.audio.play_feedback.side_effect = playback
        self.start_feedback()
        self.addCleanup(release.set)
        self.event()
        self.wait_counter('labels_played', 1)
        self.assertEqual(calls[0], self.feedback.assets[1])
        self.assertIsNone(self.feedback.take_live_request())
        for count in range(1, 4):
            self.event(kind='Interval', count=count)
            self.wait_counter('beeps_played', count)
            self.assertIsNone(self.feedback.take_live_request())
        self.event(kind='WindowClosed', count=3)
        self.event(kind='Interval', count=4)
        self.assertTrue(fourth.wait(1))
        self.assertIsNone(self.feedback.take_live_request())
        release.set()
        self.wait_counter('beeps_played', 4)
        self.assertIsNotNone(self.feedback.take_live_request())
        for count in range(5, 50): self.event(kind='Interval', count=count)
        self.assertIsNone(self.feedback.take_live_request())
        self.assertEqual(self.feedback.snapshot()['beeps_played'], 4)
        self.event(kind='Released', count=49)
        self.event()
        self.wait_counter('labels_played', 2)
        for count in range(1, 5):
            self.event(kind='Interval', count=count)
            self.wait_counter('beeps_played', 4 + count)
        self.assertIsNotNone(self.feedback.take_live_request())
        self.assertEqual(self.feedback.counters['live_hold_requests'], 2)

    def test_sw1_missing_tick_or_failed_beep_does_not_request_live(self):
        self.start_feedback()
        self.event()
        self.wait_counter('labels_played', 1)
        # Missing tick 1 cannot count as four audible ticks.
        for played, count in enumerate(range(2, 5), 1):
            self.event(kind='Interval', count=count)
            self.wait_counter('beeps_played', played)
        self.assertIsNone(self.feedback.take_live_request())

        self.event(kind='Released', count=4)
        self.event()
        self.wait_counter('labels_played', 2)
        for count in range(1, 4):
            self.event(kind='Interval', count=count)
            self.wait_counter('beeps_played', count + 3)
        self.audio.play_feedback.side_effect = RuntimeError('speaker unavailable')
        self.event(kind='Interval', count=4)
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline and self.feedback.snapshot()['error'] is None:
            time.sleep(.005)
        self.assertIsNotNone(self.feedback.snapshot()['error'])
        self.assertIsNone(self.feedback.take_live_request())

    def test_sw5_long_hold_requests_once_and_release_allows_another(self):
        self.start_feedback()
        for press in range(2):
            self.event(5)
            self.wait_counter('labels_played', press + 1)
            for count in range(1, 5):
                self.event(5, kind='Interval', count=count)
                self.wait_counter('beeps_played', press * 4 + count)
                if count < 4:
                    self.assertIsNone(self.feedback.take_camera_request())
            self.assertIsNotNone(self.feedback.take_camera_request())
            self.event(5, kind='Interval', count=8)
            self.assertIsNone(self.feedback.take_camera_request())
            self.assertIsNone(self.feedback.take_live_request())
            self.assertIsNone(self.feedback.take_study_request())
            self.event(5, kind='Released', count=8)

    def test_sw2_number_then_four_beeps_requests_study_independently_of_live(self):
        self.start_feedback()
        self.event(2)
        self.wait_counter('labels_played', 1)
        for count in range(1,5):
            self.event(2,kind='Interval',count=count)
            self.wait_counter('beeps_played',count)
            if count<4:self.assertIsNone(self.feedback.take_study_request())
        self.assertIsNotNone(self.feedback.take_study_request())
        self.assertIsNone(self.feedback.take_live_request())
        self.event(2,kind='Interval',count=8)
        self.assertIsNone(self.feedback.take_study_request())
        self.assertEqual(self.feedback.snapshot()['beeps_played'],4)

    def test_sw1_existing_hold_or_disconnected_request_cannot_start(self):
        self.event(kind='Interval', count=4)
        self.assertIsNone(self.feedback.take_live_request())
        self.event(); self.event(kind='Interval', count=4)
        self.state['connected'] = False
        self.assertIsNone(self.feedback.take_live_request())
        self.state.update(connected=True, session='usb-new')
        self.event(kind='Interval', count=8)
        self.assertIsNone(self.feedback.take_live_request())

    def test_live_announcement_finishes_voice_then_long_beep(self):
        voice = beep([1])
        self.feedback.live_assets = {'start': voice, 'end': voice}
        for action in ('start', 'end'):
            self.audio.play_feedback.reset_mock()
            self.feedback.announce_live(action)
            calls = self.audio.play_feedback.call_args_list
            self.assertEqual(calls[0].args[0], voice)
            self.assertEqual(len(pcm(calls[1].args[0])), int(.6 * RATE))
            self.assertIsNone(self.feedback.announcing)

    def test_worker_subscribes_without_browser_and_unsubscribes_on_close(self):
        done = threading.Event()
        self.audio.play_feedback.side_effect = lambda _: done.set()
        self.feedback.assets = {i: beep([i]) for i in range(1, 7)}
        with patch.object(self.feedback, 'load'):
            self.feedback.start()
            try:
                callback = self.pico.subscribe_touch.call_args.args[0]
                self.seq += 1
                callback(dict(session='usb-a', host_unix_ms=time.time() * 1000,
                              touch=dict(index=3, kind='Pressed', event_seq=self.seq, uptime_ms=1000)))
                self.assertTrue(done.wait(1))
            finally:
                self.feedback.close()
        self.pico.subscribe_touch.return_value.assert_called_once()
        self.assertFalse(any(t.is_alive() for t in self.feedback.threads))


class ToneTests(unittest.TestCase):
    def test_pitch_rises_gently_then_caps_and_wave_fades_without_clipping(self):
        for count in range(1, 39): self.assertLess(pitch(count), pitch(count + 1))
        self.assertEqual(pitch(39), pitch(100000))
        for count in (1, 12, 39, 100000):
            samples = pcm(beep([count]))
            self.assertEqual(len(samples), round(.08 * RATE))
            self.assertEqual(samples[0], 0)
            self.assertLess(abs(samples[-1]), 2)
            self.assertLessEqual(max(abs(samples)), 2068)  # -24 dBFS
            frequency = np.argmax(abs(np.fft.rfft(samples))) * RATE / len(samples)
            self.assertAlmostEqual(frequency, pitch(count), delta=14)

    def test_simultaneous_beeps_stay_at_same_gentle_peak(self):
        self.assertLessEqual(max(abs(pcm(beep([1, 3, 6, 12, 24, 39])))), 2068)

    def test_speech_trims_silence_and_normalizes_without_microphone_gain(self):
        tone = np.sin(np.arange(RATE // 3) * 2 * np.pi * 300 / RATE) * 1000
        data = wav(bytes(RATE * 2) + tone.astype('<i2').tobytes() + bytes(RATE * 2))
        result = pcm(prepare(data))
        self.assertLess(len(result), RATE // 2)
        self.assertAlmostEqual(max(abs(result)), 32767 * 10 ** (-9 / 20), delta=2)

    def test_cached_feedback_works_while_live_holds_speaker_lock(self):
        audio = Audio(EventLog())
        audio.play_lock.acquire()
        audio.speaker = {'state': 'live', 'kind': 'gpt-live'}
        try:
            with patch('hardware.synthesize') as synthesis, patch('hardware.subprocess.run',
                    return_value=Mock(returncode=0, stdout=b'')) as play:
                audio.play_feedback(beep([1]))
                synthesis.assert_not_called()
                self.assertTrue(audio.feedback_active())
                self.assertTrue(audio.play_lock.locked())
                self.assertEqual(audio.speaker['state'], 'live')
                self.assertIn('robot_playback', play.call_args.args[0])
        finally:
            audio.play_lock.release()
