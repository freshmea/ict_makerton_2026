"""Artwork integrity and playback cancellation; never opens real hardware."""
import asyncio
import threading
import time
import unittest
from collections import Counter

from eye_expressions import BY_ID, CATALOG, EyePlayer


class Events:
    def add(self, *args):
        pass


class FakePico:
    def __init__(self, late_arm=False):
        self.connected, self.session, self.running = True, 'session-one', None
        self.armed = False
        self.commands = []
        self.lock = threading.Lock()
        self.late_arm = late_arm
        self.arm_waiting, self.release_arm = threading.Event(), threading.Event()

    def snapshot(self):
        return {'connected': self.connected, 'session': self.session, 'device': {'running': self.running}}

    def command(self, value):
        if value['cmd'] == 'arm' and self.late_arm:
            self.arm_waiting.set()
            if not self.release_arm.wait(2):
                raise RuntimeError('test timed out waiting for Stop')
        with self.lock:
            self.commands.append(value)
            if value['cmd'] == 'arm':
                if self.armed:
                    return {'ok': False, 'error': 'Busy'}
                self.armed = True
            elif value['cmd'] == 'stop':
                self.armed = False
                if self.arm_waiting.is_set():
                    self.release_arm.set()
            elif value['cmd'] == 'eyes' and not self.armed:
                return {'ok': False, 'error': 'NoSession'}
        return {'ok': True, 'ack_code': 'Ok'}


class ArtworkTests(unittest.TestCase):
    def test_winks_use_robot_eye_names_and_cross_eyes_converge_in_front_view(self):
        closed = [0,0,0,126,0,0,0,0]
        left = BY_ID['wink-left']['frames'][0]
        right = BY_ID['wink-right']['frames'][0]
        self.assertEqual(left['left'], closed)
        self.assertNotEqual(left['right'], closed)
        self.assertEqual(right['right'], closed)
        self.assertNotEqual(right['left'], closed)
        cross = BY_ID['cross-eyed']['frames'][0]
        self.assertEqual(cross['left'], BY_ID['look-right']['frames'][0]['left'])
        self.assertEqual(cross['right'], BY_ID['look-left']['frames'][0]['right'])

    def test_exactly_fifty_distinct_presets_with_ten_groups(self):
        self.assertEqual(len(CATALOG), 50)
        self.assertEqual(len(BY_ID), 50)
        self.assertEqual(sorted(Counter(p['group'] for p in CATALOG).values()), [5]*10)
        pairs = {(tuple(p['frames'][0]['left']), tuple(p['frames'][0]['right'])) for p in CATALOG}
        self.assertEqual(len(pairs), 50)

    def test_all_animation_frames_fit_two_upright_eight_by_eight_matrices(self):
        for item in CATALOG:
            self.assertTrue(item['name'] and item['description'])
            self.assertLessEqual(len(item['frames']), 8)
            for frame in item['frames']:
                self.assertGreaterEqual(frame['ms'], 100)
                for side in ('left', 'right'):
                    self.assertEqual(len(frame[side]), 8)
                    self.assertTrue(all(type(row) is int and 0 <= row <= 255 for row in frame[side]))


class PlaybackTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.pico = FakePico()
        self.player = EyePlayer(self.pico, Events())

    async def asyncTearDown(self):
        await self.player.close()

    async def test_loading_catalog_and_constructing_player_never_arms_outputs(self):
        self.assertFalse(self.player.snapshot()['active'])
        self.assertEqual(self.pico.commands, [])

    async def test_playback_arms_only_eyes_and_turns_off_at_deadline(self):
        await self.player.start('love', 3)
        self.assertFalse(self.pico.commands[1]['config']['servo_enabled'])
        self.assertTrue(self.pico.commands[1]['config']['matrix_installed'])
        self.assertEqual([c['cmd'] for c in self.pico.commands], ['stop', 'arm', 'eyes'])
        self.player.active['until'] = time.monotonic() - .1
        await asyncio.wait_for(asyncio.gather(*tuple(self.player.tasks)), 1)
        self.assertEqual(self.pico.commands[-1]['cmd'], 'stop')
        self.assertFalse(self.pico.armed)
        self.assertEqual(self.player.snapshot()['last']['result'], 'completed')

    async def test_stop_preempts_late_arm_and_fences_it_without_sending_eyes(self):
        self.pico.late_arm = True
        starting = asyncio.create_task(self.player.start('neutral', 3))
        deadline = time.monotonic() + 1
        while not self.pico.arm_waiting.is_set() and time.monotonic() < deadline:
            await asyncio.sleep(.005)
        self.assertTrue(self.pico.arm_waiting.is_set())
        await self.player.stop()
        with self.assertRaises(RuntimeError):
            await starting
        self.assertFalse(self.pico.armed)
        self.assertNotIn('eyes', [c['cmd'] for c in self.pico.commands])
        self.assertEqual(self.pico.commands[-1]['cmd'], 'stop')

    async def test_stop_prevents_any_later_animation_frame(self):
        await self.player.start('love', 3)
        self.player.active['since'] -= .7
        await asyncio.sleep(.12)
        self.assertGreaterEqual(sum(c['cmd'] == 'eyes' for c in self.pico.commands), 2)
        await self.player.stop()
        count = len(self.pico.commands)
        await asyncio.sleep(.15)
        self.assertEqual(len(self.pico.commands), count)
        self.assertFalse(self.pico.armed)

    async def test_new_usb_session_never_receives_old_animation_or_cleanup(self):
        await self.player.start('neutral', 3)
        self.pico.session = 'session-two'
        self.pico.armed = False  # A new Hello already stops the MCU.
        await asyncio.sleep(.15)
        self.assertFalse(self.player.snapshot()['active'])
        self.assertIsNotNone(self.player.snapshot()['error'])
        self.assertEqual([c['cmd'] for c in self.pico.commands], ['stop', 'arm', 'eyes'])

    async def test_replacing_a_preset_clears_firmware_active_before_new_arm(self):
        await self.player.start('neutral', 3)
        await self.player.start('love', 3)
        self.assertEqual([c['cmd'] for c in self.pico.commands], ['stop', 'arm', 'eyes']*2)
        self.assertEqual(self.player.snapshot()['preset_id'], 'love')

    async def test_diagnostic_stops_expression_before_starting(self):
        await self.player.start('neutral', 3)
        await self.player.command({'cmd': 'test', 'module': 'matrix'})
        self.assertEqual([c['cmd'] for c in self.pico.commands][-2:], ['stop', 'test'])
        count = len(self.pico.commands)
        await asyncio.sleep(.15)
        self.assertEqual(len(self.pico.commands), count)

    async def test_invalid_preset_or_busy_diagnostic_never_arms(self):
        with self.assertRaises(ValueError):
            await self.player.start('unknown', 3)
        with self.assertRaises(ValueError):
            await self.player.start('neutral', 60)
        self.pico.running = 'Servos'
        with self.assertRaises(RuntimeError):
            await self.player.start('neutral', 3)
        self.assertEqual(self.pico.commands, [])


if __name__ == '__main__':
    unittest.main()
