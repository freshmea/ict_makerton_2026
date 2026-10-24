import asyncio
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock,AsyncMock,patch

from study_reaction import StudyReaction,choose


class Servos:
    def __init__(self):
        self.active=False;self.gate=asyncio.Lock();self.moves=[];self.stops=0
    def snapshot(self):return {'ready':True,'reason':''}
    async def enable(self):self.active=True;return {'control_id':'test-owner'}
    def keepalive(self,owner):
        if not self.active:raise RuntimeError('expired')
    async def move(self,owner,servo,degrees):self.moves.append((servo,degrees));return {'ok':True}
    async def stop(self,owner=None):self.active=False;self.stops+=1


class ReactionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.pico=Mock(snapshot=lambda:{'connected':True,'session':'pico-a','outputs':{'commanded_cdeg':[9000]*6}})
        self.audio=Mock(play_lock=threading.Lock())
        self.eyes=Mock(stop=AsyncMock(return_value={'ok':True}),command=AsyncMock(return_value={'ok':True}),external_until=0)
        self.servos=Servos()
        self.live=Mock(active=False,state={'phase':'idle'})
        self.controller=StudyReaction(self.pico,self.audio,self.eyes,self.servos,self.live,Mock(),Mock(),self.temp.name)
        self.controller.speech.prepare=Mock(return_value=b'wav-fixture')
        async def played(token,data,report):report['speech']='played'
        self.controller.play_voice=AsyncMock(side_effect=played)

    async def asyncTearDown(self):
        await self.controller.close();self.temp.cleanup()

    async def test_four_servos_return_and_led_speech_are_applied(self):
        await self.controller.react(0,{'observed_is_away':False,'focus_score':8})
        report=self.controller.state['reaction']
        self.assertEqual(report['kind'],'engaged')
        self.assertEqual(self.servos.moves,[(servo,angle) for servo in range(1,5) for angle in (94,90)])
        self.assertEqual(len(report['servos']),4)
        self.assertEqual(report['speech'],'played')
        self.assertEqual(report['led'],'applied')
        self.assertEqual(self.servos.stops,1)
        self.assertFalse(self.audio.play_lock.locked())

    async def test_manual_control_is_never_stopped_or_rearmed(self):
        self.servos.active=True
        await self.controller.react(0,{'observed_is_away':False,'focus_score':8})
        self.eyes.command.assert_not_awaited();self.eyes.stop.assert_not_awaited()
        self.assertEqual(self.servos.stops,0)
        self.assertTrue(self.servos.active)

    async def test_rejected_led_command_is_not_reported_as_applied_and_stops_motors(self):
        self.eyes.command.return_value={'ok':False,'error':'driver error'}
        with self.assertRaisesRegex(RuntimeError,'driver error'):
            await self.controller.react(0,{'observed_is_away':True})
        self.assertEqual(self.controller.state['reaction']['led'],'pending')
        self.assertEqual(self.servos.moves,[(1,94)])
        self.assertEqual(self.servos.stops,1)

    async def test_stopped_zero_telemetry_uses_last_acknowledged_target_or_neutral(self):
        self.pico.snapshot=lambda:{'connected':True,'session':'pico-a',
                                   'outputs':{'armed':False,'commanded_cdeg':[0]*6}}
        self.servos.snapshot=lambda:{'ready':True,'commanded_degrees':[30,None,120,None,None,None]}
        await self.controller.react(0,{'observed_is_away':True})
        self.assertEqual(self.servos.moves,[(1,34),(1,30),(2,94),(2,90),(3,124),(3,120),(4,94),(4,90)])

    async def test_cancel_during_motion_stops_and_prevents_later_moves(self):
        entered=asyncio.Event()
        async def blocked(*args):entered.set();await asyncio.sleep(60)
        self.servos.move=blocked
        self.controller.task=asyncio.create_task(self.controller.react(0,{'observed_is_away':True}))
        await asyncio.wait_for(entered.wait(),1)
        await self.controller.abort(cancel_remote=False)
        self.assertEqual(self.servos.stops,1)
        self.assertFalse(self.audio.play_lock.locked())
        self.eyes.command.assert_not_awaited()

    async def test_one_rpc_start_then_one_reaction_report(self):
        job={'id':'a'*32,'phase':'capturing'}
        replies=[{'job':job},{'job':dict(job,phase='completed',result={'observed_is_away':False,'focus_score':8})}]
        with patch('study_reaction.rpc',AsyncMock(side_effect=replies)) as rpc:
            await self.controller.start(0)
            await self.controller.task
        self.assertEqual(sum(call.args[0]['op']=='start' for call in rpc.call_args_list),1)
        self.assertEqual(self.controller.state['phase'],'completed')
        self.assertTrue((Path(self.temp.name)/('a'*32+'.json')).exists())

    async def test_live_and_duplicate_start_are_rejected_before_api(self):
        with patch('study_reaction.rpc',AsyncMock()) as rpc:
            self.live.active=True
            with self.assertRaises(RuntimeError):await self.controller.start()
            self.live.active=False;self.controller.starting=True
            with self.assertRaises(RuntimeError):await self.controller.start()
            with self.assertRaises(RuntimeError):self.controller.guard_live()
            self.controller.starting=False
            rpc.assert_not_awaited()

    async def test_changed_usb_session_blocks_reaction(self):
        self.controller.state['pico_session']='old'
        with self.assertRaisesRegex(RuntimeError,'Pico'):await self.controller.react(0,{'observed_is_away':True})
        self.assertFalse(self.audio.play_lock.locked())
        self.assertFalse(self.servos.moves)


class ClassificationTests(unittest.TestCase):
    def test_unknown_policy_does_not_say_person_definitely_left(self):
        self.assertEqual(choose({'is_away':True,'observed_is_away':None,'presence_basis':'user_policy_unknown_as_away'}),'unknown')
        self.assertEqual(choose({'observed_is_away':True}),'away')
        self.assertEqual(choose({'observed_is_away':False,'study_gaze_score':2}),'refocus')
