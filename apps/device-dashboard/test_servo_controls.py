import asyncio
import copy
import unittest
import os
import tempfile
from unittest.mock import AsyncMock, Mock, patch

from servo_controls import ServoControls


class Pico:
    def __init__(self):
        self.state = {'connected': True, 'session': 'session-a',
                      'capabilities': {'single_servo': True},
                      'device': {'faults': 0, 'running': None,
                                 'config': {'servo_min_us': 1000, 'servo_max_us': 2000}},
                      'last_applied': None}
        self.stop = Mock()

    def snapshot(self): return copy.deepcopy(self.state)


class ServoTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.reference_dir=tempfile.TemporaryDirectory()
        self.addCleanup(self.reference_dir.cleanup)
        reference_env=patch.dict(os.environ,{'SERVO_REFERENCE_PATH':self.reference_dir.name+'/targets.json'})
        reference_env.start();self.addCleanup(reference_env.stop)
        self.pico = Pico()
        self.commands = []

        async def command(value):
            self.commands.append(value)
            if value['cmd'] == 'servo':
                self.pico.state['last_applied'] = {'request_seq': 99, 'kind': 4}
            return {'ok': True, 'ack_request_seq': 99}

        self.eyes = Mock(command=AsyncMock(side_effect=command), stop=AsyncMock(return_value={'ok': True}))
        self.control = ServoControls(self.pico, self.eyes, Mock())

    async def asyncTearDown(self): await self.control.close()

    async def test_fault_and_old_firmware_reject_before_any_arm(self):
        for faults, support in [(1, True), (0, False)]:
            self.pico.state['device']['faults'] = faults
            self.pico.state['capabilities']['single_servo'] = support
            with self.assertRaises(RuntimeError): await self.control.enable()
        self.eyes.command.assert_not_called()
        self.eyes.stop.assert_not_called()

    async def test_enable_does_not_move_and_move_targets_only_selected_channel(self):
        result = await self.control.enable()
        self.assertEqual(self.commands, [])
        moved = await self.control.move(result['control_id'], 2, 123)
        self.assertEqual(self.commands[-1], {'cmd': 'servo', 'channel': 1, 'target_cdeg': 12300, 'move_ms': 500})
        self.assertEqual([c['cmd'] for c in self.commands], ['arm', 'servo'])
        self.assertEqual(moved['state']['commanded_degrees'], [None, 123, None, None, None, None])
        self.assertEqual(self.commands[0]['config']['min_us'], [1000]*6)

    async def test_expired_browser_lease_stops_and_revokes_owner(self):
        await self.control.enable()
        self.control.deadline = 0
        await asyncio.sleep(.25)
        self.assertFalse(self.control.active)
        self.assertIsNone(self.control.owner)
        self.assertGreaterEqual(self.eyes.stop.await_count, 2)

    async def test_changed_usb_session_cannot_receive_old_owner_commands(self):
        result = await self.control.enable()
        self.pico.state['session'] = 'new-session'
        with self.assertRaises(RuntimeError): await self.control.move(result['control_id'], 1, 90)
        self.eyes.command.assert_not_called()
        await asyncio.sleep(.25)
        self.assertFalse(self.control.active)
        self.assertEqual(self.eyes.stop.await_count, 1)  # enable's Stop only; new session untouched

    async def test_stale_telemetry_revokes_live_bridge_instead_of_leaving_pwm_held(self):
        result = await self.control.enable()
        self.pico.state.update(connected=False, bridge_pid=123)
        with self.assertRaises(RuntimeError): self.control.keepalive(result['control_id'])
        await asyncio.sleep(.25)
        self.assertFalse(self.control.active)
        self.pico.stop.assert_called_once()

    async def test_stop_during_arm_prevents_late_servo_motion(self):
        result = await self.control.enable()
        entered, release = asyncio.Event(), asyncio.Event()

        async def slow_arm(value):
            self.commands.append(value)
            entered.set(); await release.wait()
            return {'ok': True, 'ack_request_seq': 99}

        self.eyes.command.side_effect = slow_arm
        moving = asyncio.create_task(self.control.move(result['control_id'], 1, 45))
        await entered.wait(); await self.control.stop(); release.set()
        with self.assertRaises(RuntimeError): await moving
        self.assertEqual([c['cmd'] for c in self.commands], ['arm'])

    async def test_probe_only_initializes_driver_with_outputs_stopped(self):
        self.pico.state['device']['faults'] = 1
        await self.control.probe()
        self.assertEqual(self.commands, [{'cmd': 'servo_probe'}])
        self.assertFalse(self.control.active)

    async def test_unconfirmed_stop_revokes_bridge_keepalive(self):
        self.eyes.stop.side_effect = RuntimeError('Stop ACK missing')
        with self.assertRaises(RuntimeError): await self.control.stop()
        self.pico.stop.assert_called_once()
        self.assertFalse(self.control.active)

    async def test_failed_probe_explains_driver_connection_and_stays_disabled(self):
        self.eyes.command.side_effect = RuntimeError('Device rejected request: Fault')
        with self.assertRaisesRegex(RuntimeError, '주소 0x41'):
            await self.control.probe()
        self.assertFalse(self.control.active)

    async def test_driver_diagnostics_distinguish_nack_timeout_and_ambiguous_addresses(self):
        self.pico.state['device']['faults'] = 1
        self.pico.state['servo_driver'] = {'selected_address': 0, 'probes': [2, 3],
                                           'sda_high': False, 'scl_high': True}
        reason = self.control.snapshot()['reason']
        self.assertIn('0x40 ACK 없음', reason)
        self.assertIn('0x41 시간 초과', reason)
        self.assertIn('SDA LOW / SCL HIGH', reason)
        self.pico.state['servo_driver']['probes'] = [1, 1]
        self.assertIn('주소 두 개', self.control.snapshot()['reason'])

    async def test_idle_diagnostics_do_not_claim_that_a_test_is_running(self):
        self.pico.state['device']['faults'] = 1
        self.assertNotIn('장치 시험', self.control.snapshot()['reason'])
        self.pico.state['device']['running'] = 'Matrix'
        self.assertIn('장치 시험이 진행 중', self.control.snapshot()['reason'])

    async def test_api_validation_and_single_selected_servo(self):
        import app
        from pydantic import ValidationError
        for payload in ({'servo': 0, 'degrees': 90}, {'servo': 7, 'degrees': 90},
                        {'servo': 1, 'degrees': 181}, {'servo': 1, 'degrees': -1},
                        {'servo': True, 'degrees': 90}, {'servo': 1, 'degrees': 90.5},
                        {'servo': 1, 'degrees': 90, 'pin': 0}):
            with self.assertRaises(ValidationError): app.ServoMoveRequest(control_id='x'*24, **payload)
        owner = Mock(move=AsyncMock(return_value={'ok': True}))
        with patch.object(app.app.state, 'servos', owner, create=True):
            result = await app.move_servo(app.ServoMoveRequest(control_id='x'*24, servo=6, degrees=180))
            self.assertTrue(result['ok'])
            owner.move.assert_awaited_once_with('x'*24, 6, 180)


if __name__ == '__main__': unittest.main()
