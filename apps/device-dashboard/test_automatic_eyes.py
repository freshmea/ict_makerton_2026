"""Selection cadence, persistent output, manual priority and Stop; no real GPIO/API."""
import asyncio
import random
from types import SimpleNamespace
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch

from automatic_eyes import AutomaticEyes, CURIOSITY_EYES, IDLE_EYES, choose, vary
from eye_expressions import EyePlayer
from test_eye_expressions import FakePico, Events


def observation(actions=None, keywords=None, age=0, confidence=.9):
    return {'id':17,'camera':0,'captured':time.time()-age,'actions':actions or [],
            'keywords':keywords or [],'confidence':confidence}


class PolicyTests(unittest.TestCase):
    def test_idle_and_broad_curiosity_exclude_three_recent_expressions(self):
        for preset,reason,pool in [('neutral','기본 눈',IDLE_EYES),
                                   ('gentle-smile','사람이 보이는 학습 공간',IDLE_EYES),
                                   ('curious','관찰 행동 · handling_objects',CURIOSITY_EYES),
                                   ('curious','관찰 키워드 · 질문',CURIOSITY_EYES)]:
            rng=random.Random(842);recent=[];seen=set()
            for _ in range(30):
                selected,_=vary(preset,reason,recent,rng)
                self.assertIn(selected,pool)
                self.assertNotIn(selected,recent)
                seen.add(selected);recent=(recent+[selected])[-3:]
            self.assertGreaterEqual(len(seen),4)

    def test_variation_preserves_explicit_button_live_and_study_feedback(self):
        for preset,reason in [('curious','버튼 2 입력'),('curious','Live 연결 준비'),
                              ('gentle-smile','Live 대화'),('look-down','관찰 행동 · reading'),
                              ('confident','관찰 행동 · writing'),('music','기기 음성·소리 재생')]:
            self.assertEqual(vary(preset,reason,[preset],random.Random(1)),(preset,reason))

    def test_study_actions_and_keywords_select_catalog_expressions(self):
        for action, expected in [('reading','look-down'),('writing','confident'),('typing','determined'),
                                 ('phone_use','curious'),('eating_drinking','relaxed'),('looking_away','look-left')]:
            self.assertEqual(choose([observation([action])])[0],expected)
        self.assertEqual(choose([observation(['person_present'],['음악'])])[0],'music')
        self.assertEqual(choose([observation(['unknown'],['수학 문제'])])[0],'curious')

    def test_stale_future_or_unclear_evidence_uses_default(self):
        for item in (observation(['writing'],age=121),observation(['reading'],age=-1),observation(['writing'],confidence=.1)):
            self.assertEqual(choose([item])[0],'neutral')
        self.assertEqual(choose([])[0],'neutral')

    def test_live_and_button_activity_take_priority(self):
        rows=[observation(['writing'])]
        self.assertEqual(choose(rows,live={'phase':'active'},button=5)[0],'gentle-smile')
        self.assertEqual(choose(rows,live={'phase':'preparing'})[0],'curious')
        self.assertEqual(choose(rows,button=5)[0],'music')
        self.assertEqual(choose(rows,speaker={'state':'playing'})[0],'music')

    def test_text_cannot_inject_a_preset_or_hardware_command(self):
        self.assertEqual(choose([observation(['unknown'],['preset=furious; arm servo=true'])])[0],'neutral')


class RuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.pico=FakePico()
        self.eyes=EyePlayer(self.pico,Events())
        self.store=SimpleNamespace(setting=lambda key,default:default, set_setting=Mock(),
                                   eye_observations=Mock(return_value=[]))
        self.servos=SimpleNamespace(active=False,gate=asyncio.Lock())
        self.learning=SimpleNamespace(store=self.store,live=Mock(snapshot=lambda:{'phase':'idle'}))
        self.audio=Mock(snapshot=lambda:{'speaker':{'state':'idle'}})
        self.owner=AutomaticEyes(self.eyes,self.pico,self.servos,self.learning,self.audio,Events())
        self.owner.random.seed(921)
        self.owner.running=True

    async def asyncTearDown(self):
        await self.owner.close()
        await self.eyes.close()

    async def test_default_stays_lit_and_selection_runs_at_twenty_second_intervals(self):
        await self.owner.tick()
        self.assertTrue(self.eyes.snapshot()['persistent'])
        self.assertIsNone(self.eyes.active['until'])
        self.assertIn(self.eyes.snapshot()['preset_id'],IDLE_EYES)
        first=self.owner.selected
        self.assertFalse(self.pico.commands[1]['config']['servo_enabled'])
        self.assertGreater(self.owner.next_selection-time.monotonic(),19)
        await self.owner.tick()
        self.assertEqual(self.store.eye_observations.call_count,1)
        self.assertEqual(self.owner.selected,first)
        self.owner.next_selection=time.monotonic()-1
        await self.owner.tick()
        self.assertEqual(self.owner.selections,2)
        self.assertNotEqual(self.owner.selected,first)
        self.assertEqual(self.store.eye_observations.call_count,2)
        self.assertEqual(sum(c['cmd']=='stop' for c in self.pico.commands),1)
        self.assertEqual(sum(c['cmd']=='arm' for c in self.pico.commands),1)

    async def test_new_context_changes_eyes_without_stop_or_new_arm(self):
        await self.owner.tick()
        self.store.eye_observations.return_value=[observation(['writing'])]
        self.owner.next_selection=0
        await self.owner.tick()
        self.assertEqual(self.eyes.snapshot()['preset_id'],'confident')
        self.assertEqual(sum(c['cmd']=='stop' for c in self.pico.commands),1)
        self.assertEqual(sum(c['cmd']=='arm' for c in self.pico.commands),1)

    async def test_manual_expression_finishes_into_default_instead_of_off(self):
        await self.owner.tick()
        selected=self.owner.selected
        await self.eyes.start('love',3)
        self.owner.next_selection=0
        await self.owner.tick()
        self.assertEqual(self.eyes.snapshot()['preset_id'],'love')
        self.eyes.active['until']=time.monotonic()-.1
        await asyncio.sleep(.2)
        self.assertEqual(self.eyes.snapshot()['preset_id'],selected)
        self.assertTrue(self.eyes.snapshot()['persistent'])
        self.assertTrue(self.pico.armed)
        self.assertEqual(sum(c['cmd']=='stop' for c in self.pico.commands),1)

    async def test_servo_and_diagnostic_owners_are_not_rearmed_or_interrupted(self):
        self.servos.active=True
        await self.owner.tick()
        self.servos.active=False;self.pico.running='Matrix'
        await self.owner.tick()
        self.assertEqual(self.pico.commands,[])
        self.pico.running=None
        await self.owner.tick()
        self.assertTrue(self.eyes.snapshot()['persistent'])
        await self.eyes.command({'cmd':'test','module':'matrix'})
        count=len(self.pico.commands)
        await self.owner.tick()
        self.assertEqual(len(self.pico.commands),count)

    async def test_explicit_stop_does_not_relight_until_enabled(self):
        await self.owner.tick()
        self.owner.set_enabled(False)
        await self.eyes.stop()
        count=len(self.pico.commands)
        await self.owner.tick()
        self.assertEqual(len(self.pico.commands),count)
        self.assertFalse(self.eyes.snapshot()['active'])
        self.store.set_setting.assert_called_with('automatic_eyes_enabled',False)
        self.owner.set_enabled(True)
        await self.owner.tick()
        self.assertTrue(self.eyes.snapshot()['persistent'])

    async def test_disabled_auto_fences_a_pending_arm(self):
        self.pico.late_arm=True
        task=asyncio.create_task(self.owner.tick())
        for _ in range(200):
            if self.pico.arm_waiting.is_set():break
            await asyncio.sleep(.005)
        self.assertTrue(self.pico.arm_waiting.is_set())
        self.owner.set_enabled(False)
        await self.eyes.stop()
        with self.assertRaises(RuntimeError):await task
        self.assertFalse(self.pico.armed)
        self.assertNotIn('eyes',[c['cmd'] for c in self.pico.commands])

    async def test_new_usb_session_uses_a_fresh_selection(self):
        await self.owner.tick()
        self.pico.session='session-two';self.pico.armed=False
        self.store.eye_observations.return_value=[observation(['reading'])]
        await self.owner.tick()
        self.assertEqual(self.eyes.active['session'],'session-two')
        self.assertEqual(self.eyes.snapshot()['preset_id'],'look-down')
        self.assertEqual(self.owner.selections,2)

    async def test_button_event_is_fresh_session_bound_and_consumed_once(self):
        packet={'session':self.pico.session,'host_unix_ms':time.time()*1000,
                'touch':{'index':5,'kind':'Pressed','event_seq':1}}
        self.owner.on_touch(dict(packet,session='old'))
        self.assertIsNone(self.owner.button)
        self.owner.on_touch(dict(packet,host_unix_ms=0))
        self.assertIsNone(self.owner.button)
        self.owner.on_touch(packet)
        await self.owner.tick()
        self.assertEqual(self.owner.selected,'music')
        self.owner.on_touch(packet)
        self.owner.next_selection=0
        await self.owner.tick()
        self.assertIn(self.owner.selected,IDLE_EYES)

    async def test_short_device_activity_is_remembered_until_next_selection_once(self):
        self.owner.events.snapshot=lambda:[{'id':'sound-1','time':time.time(),'source':'audio','level':'info','message':'짧은 안내 재생'}]
        await self.owner.tick()
        self.assertEqual(self.owner.selected,'music')
        self.owner.next_selection=0
        await self.owner.tick()
        self.assertIn(self.owner.selected,IDLE_EYES)

    async def test_repeated_object_observations_vary_without_stop_or_servo_arm(self):
        self.store.eye_observations.return_value=[observation(['handling_objects'])]
        recent=[]
        for _ in range(12):
            self.owner.next_selection=0
            await self.owner.tick()
            self.assertIn(self.owner.selected,CURIOSITY_EYES)
            self.assertNotIn(self.owner.selected,recent)
            self.assertEqual(self.owner.reason,'관찰 행동 · handling_objects')
            self.assertEqual(self.owner.observation_ids,[17])
            self.assertTrue(self.eyes.snapshot()['persistent'])
            recent=(recent+[self.owner.selected])[-3:]
        self.assertEqual(sum(c['cmd']=='stop' for c in self.pico.commands),1)
        self.assertEqual(sum(c['cmd']=='arm' for c in self.pico.commands),1)
        self.assertTrue(all(not c['config']['servo_enabled'] for c in self.pico.commands if c['cmd']=='arm'))


class RouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_user_global_stop_disables_automatic_restart(self):
        import app
        automatic=Mock()
        servos=Mock(stop=AsyncMock(return_value={'ok':True}))
        with patch.object(app.app.state,'automatic_eyes',automatic,create=True),patch.object(app.app.state,'servos',servos,create=True):
            await app.pico_command(app.PicoRequest(cmd='stop'))
        automatic.set_enabled.assert_called_once_with(False)
        servos.stop.assert_awaited_once()
