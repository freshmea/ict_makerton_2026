import asyncio
import importlib.util
import json
import os
from pathlib import Path
import struct
import tempfile
import threading
import unittest
from unittest.mock import patch

import study_window as window
from study_observer_service import Manager


JPEG = b'\xff\xd8\xff\xc0' + struct.pack('>HBHHB', 8, 8, 360, 640, 0) + b'\xff\xd9'


def images():
    return [{'data': JPEG, 'ref': 'unique-image-%02d' % i, 'sample': i, 'offset_seconds': float(i),
             'sensor_id': 1, 'bytes': len(JPEG), 'width': 640, 'height': 360} for i in range(10)]


def dual_images(face_id=0):
    return [dict(frame, ref='sample-%d-%s' % (frame['sample'], camera['role']),
                 sensor_id=camera['sensor_id'], camera_role=camera['role'])
            for frame in images() for camera in window.camera_roles('jev', face_id)]


def answers():
    result = {}
    for name, question in window.questions().items():
        kind = question['type']
        result[name] = {'type': 'noul', 'noul': .95} if kind == 'noul' else (
            {'type': 'score', 'score': 3.6, 'confidence': .8} if kind == 'score' else
            {'type': 'choice', 'choice': 'not_observed', 'confidence': .9})
    return result


class WindowTests(unittest.TestCase):
    def test_fifteen_independent_behavior_groups_and_twenty_one_questions(self):
        self.assertEqual(len(window.category_catalog()), 15)
        self.assertEqual(len(window.questions()), 21)
        self.assertEqual(len({c['id'] for c in window.category_catalog()}), 15)

    def test_ten_images_and_all_questions_fit_openai_bounds(self):
        body = window.openai_body(images())
        info = window.openai.bounded_summary(body, 'fixture')
        self.assertEqual(info['images'], 10)
        self.assertEqual(info['questions'], 21)

    def test_decisions_frame_labels_keep_both_camera_roles(self):
        for face_id in (0,1):
            labels=[item['text'] for item in window.content(dual_images(face_id))[1:] if item['type']=='input_text']
            self.assertEqual(len(labels),20)
            for sample in range(10):
                self.assertIn('camera %d, role face' % face_id,labels[sample*2])
                self.assertIn('camera %d, role study_area' % (1-face_id),labels[sample*2+1])

    def test_jev_references_every_photo_once_and_uses_free_model(self):
        for face_id in (0, 1):
            body = window.jev_body(dual_images(face_id))
            self.assertEqual(body['model'], 'jev-1.13-free')
            self.assertEqual(len(body['assets']), 20)
            frames = body['state']['frames_oldest_first']
            self.assertEqual([i['elapsed_seconds'] for i in frames], [i for i in range(10) for _ in range(2)])
            self.assertEqual([(i['sensor_id'], i['camera_role']) for i in frames],
                             [(face_id, 'face'), (1-face_id, 'study_area')] * 10)
            self.assertEqual([i['sample'] for i in frames], [i for i in range(1, 11) for _ in range(2)])
            for key in body['assets']:
                self.assertEqual(json.dumps(body['state']).count(key), 1)

    def test_incomplete_or_mislabelled_pair_never_reaches_jev(self):
        missing = dual_images()[:-1]
        wrong_role = dual_images(); wrong_role[1]['camera_role'] = 'face'
        wrong_sensor = dual_images(); wrong_sensor[1]['sensor_id'] = 0
        wrong_sample = dual_images(); wrong_sample[1]['sample'] = 1
        duplicate = dual_images(); duplicate[1]['ref'] = duplicate[0]['ref']
        wrong_time = dual_images(); wrong_time[1]['offset_seconds'] = 1
        for frames in (missing, wrong_role, wrong_sensor, wrong_sample, duplicate, wrong_time):
            with patch.object(window.jev, 'json_request') as request:
                with self.assertRaises(window.Error):
                    window.analyze('jev', frames, {'OPENCODE_API_KEY': 'fixture'}, None)
                request.assert_not_called()

    def test_jev_sends_one_request_and_reports_twenty_frames(self):
        with patch.object(window.jev, 'json_request', return_value=({'answers': answers(), 'model': 'jev-1.13-free'}, 123)) as request:
            result = window.analyze('jev', dual_images(), {'OPENCODE_API_KEY': 'fixture'}, None)
            self.assertEqual(request.call_count, 1)
            self.assertEqual(len(request.call_args.args[1]['assets']), 20)
            self.assertEqual(result['frame_count'], 20)
            self.assertEqual(len(result['behaviors']), 15)

    def test_observed_behavior_does_not_apply_automatic_double_penalty(self):
        data = answers()
        data['behavior_food_drink']['choice'] = 'observed'
        data['behavior_objects']['choice'] = 'observed'
        result = window.normalize(data)
        self.assertEqual(result['focus_score'], 9)
        self.assertIs(result['is_away'], False)

    def test_ambiguous_phone_and_low_confidence_are_unknown(self):
        data = answers()
        data['behavior_phone'].update(choice='unknown')
        data['behavior_computer_tablet'].update(choice='observed', confidence=.2)
        result = {i['id']: i['state'] for i in window.normalize(data)['behaviors']}
        self.assertEqual(result['phone'], 'unknown')
        self.assertEqual(result['computer_tablet'], 'unknown')

    def test_unknown_presence_uses_user_away_policy_without_fabricating_scores(self):
        data = answers()
        for name in ('seat_observable', 'person_present', 'behavior_observable', 'gaze_observable'):
            data[name]['noul'] = .1
        result = window.normalize(data)
        self.assertIs(result['is_away'], True)
        self.assertIsNone(result['observed_is_away'])
        self.assertFalse(result['valid']['is_away'])
        self.assertEqual(result['presence_basis'], 'user_policy_unknown_as_away')
        self.assertIsNone(result['focus_score'])
        self.assertIsNone(result['study_gaze_score'])

    def test_known_presence_stays_present_when_only_study_behavior_is_unknown(self):
        data = answers()
        data['behavior_observable']['noul'] = .1
        result = window.normalize(data)
        self.assertIs(result['is_away'], False)
        self.assertIsNone(result['focus_score'])
        self.assertEqual(result['presence_basis'], 'visible_evidence')

    def test_refusal_preserves_other_fields(self):
        data = answers();data['behavior_social'] = {'type': 'refusal'}
        result = window.normalize(data)
        self.assertEqual(result['behaviors'][3]['state'], 'unknown')
        self.assertEqual(result['focus_score'], 9)

    def test_openai_contract_maps_all_categories(self):
        raw = []
        for name, item in answers().items():
            raw.append(dict(item, name=name, **({'type': 'predicate', 'probability': item['noul']} if item['type'] == 'noul' else {})))
        result = window.translate_openai({'answers': raw})
        self.assertEqual(len(result['behaviors']), 15)
        self.assertEqual(result['focus_score'], 9)

    def test_stale_state_and_generation_change_stop_capture(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(window.time, 'monotonic', return_value=100):
            root = Path(directory)
            state = {'updated_monotonic': 99.9, 'run_id': 'new', 'cameras': [{'sensor_id': 1, 'ready': True, 'preview_age_ms': 10}]}
            p = root/'camera-state.json';p.write_text(json.dumps(state))
            self.assertEqual(window.read_state(root, 1), 'new')
            with self.assertRaisesRegex(window.Error, 'restarted'):
                window.read_state(root, 1, 'old')
            state['updated_monotonic'] = 90;p.write_text(json.dumps(state))
            with self.assertRaisesRegex(window.Error, 'stale'):
                window.read_state(root, 1)

    def test_fixed_cadence_collects_exactly_ten_not_cumulative_delays(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory);p=root/'cam1.jpg';p.write_bytes(JPEG)
            clock=[100.0];counts=[]
            class Cancel:
                step=0
                def is_set(self):return False
                def wait(self, delay):
                    clock[0]+=delay;self.step+=1
                    os.utime(str(p), ns=(self.step*1000000000,self.step*1000000000))
                    return False
            with patch.object(window, 'read_state', return_value='generation'), patch.object(window.time, 'monotonic', side_effect=lambda:clock[0]):
                data,generation=window.capture(root,1,Cancel(),counts.append)
            self.assertEqual(len(data),10)
            self.assertEqual([i['offset_seconds'] for i in data], list(range(10)))
            self.assertEqual(counts,list(range(1,11)))

    def test_dual_capture_collects_ten_pairs_at_one_second_cadence(self):
        for face_id in (0, 1):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                paths = [root/'cam0.jpg', root/'cam1.jpg']
                for path in paths:path.write_bytes(JPEG)
                clock = [100.0]; counts = []
                class Cancel:
                    step = 0
                    def is_set(self):return False
                    def wait(self, delay):
                        clock[0] += delay; self.step += 1
                        for path in paths:
                            os.utime(str(path), ns=(self.step*1000000000, self.step*1000000000))
                        return False
                with patch.object(window, 'read_state', return_value='g'), patch.object(window.time, 'monotonic', side_effect=lambda:clock[0]):
                    data, generation = window.capture(root, face_id, Cancel(), counts.append, True)
                self.assertEqual(len(data), 20)
                self.assertEqual(counts, list(range(2, 21, 2)))
                self.assertEqual([i['offset_seconds'] for i in data], [i for i in range(10) for _ in range(2)])
                self.assertEqual([(i['sensor_id'], i['camera_role']) for i in data], [(face_id,'face'),(1-face_id,'study_area')]*10)
                self.assertEqual(len(window.jev_body(data)['assets']), 20)

    def test_stalled_second_camera_aborts_without_counting_partial_pair(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for sensor in (0, 1):(root/('cam%d.jpg' % sensor)).write_bytes(JPEG)
            clock = [100.0]; counts = []
            class Cancel:
                step = 0
                def is_set(self):return False
                def wait(self, delay):
                    clock[0] += delay; self.step += 1
                    os.utime(str(root/'cam0.jpg'), ns=(self.step*1000000000, self.step*1000000000))
                    return False
            with patch.object(window, 'read_state', return_value='g'), patch.object(window.time, 'monotonic', side_effect=lambda:clock[0]):
                with self.assertRaisesRegex(window.Error, 'did_not_advance'):
                    window.capture(root, 0, Cancel(), counts.append, True)
            self.assertEqual(counts, [2])

    def test_both_cameras_must_be_ready_in_same_generation_before_capture(self):
        for code in ('camera_preview_stale', 'camera_restarted_during_window'):
            def state(runtime, sensor, expected=None):
                if sensor == 1:raise window.Error(code)
                return 'g'
            with patch.object(window, 'read_state', side_effect=state):
                with self.assertRaisesRegex(window.Error, code):
                    window.capture(Path('.'), 0, threading.Event(), lambda n:None, True)

    def test_cancelled_capture_has_no_complete_window(self):
        event=threading.Event();event.set()
        with patch.object(window,'read_state',return_value='g'):
            with self.assertRaises(window.Cancelled):window.capture(Path('.'),1,event,lambda n:None)

    def test_missed_deadline_does_not_burst_collect(self):
        class Cancel:
            def wait(self,delay):return False
        with patch.object(window,'read_state',return_value='g'), patch.object(window.time,'monotonic',side_effect=[100,100,100.5]):
            with self.assertRaisesRegex(window.Error,'timing_missed'):
                window.capture(Path('.'),1,Cancel(),lambda n:None)


class ManagerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory=tempfile.TemporaryDirectory()
        root=Path(self.directory.name)
        self.manager=Manager({'OPENAI_API_KEY':'fixture','OPENCODE_API_KEY':'fixture'},state=root,budget=window.openai.Budget(root/'budget.json'))

    async def asyncTearDown(self):
        await self.manager.close()
        self.directory.cleanup()

    async def test_one_job_one_upload_and_no_key_in_status(self):
        with patch.object(window,'capture',return_value=(images(),'g')), patch.object(window,'analyze',return_value={'status':'ok'}) as analyze:
            await self.manager.start('openai',1)
            with self.assertRaisesRegex(window.Error,'busy'):await self.manager.start('openai',1)
            await self.manager.task
            self.assertEqual(analyze.call_count,1)
            snapshot=self.manager.snapshot()
            self.assertNotIn('fixture',json.dumps(snapshot))
            self.assertNotIn('data_base64',json.dumps(snapshot))
            self.assertEqual(snapshot['job']['phase'],'completed')

    async def test_cancel_during_collection_never_uploads(self):
        def capture(runtime,camera,cancel,progress,dual_camera=False):
            cancel.wait(2)
            raise window.Cancelled('cancelled')
        with patch.object(window,'capture',side_effect=capture), patch.object(window,'analyze') as analyze:
            await self.manager.start('jev',1)
            self.manager.cancel()
            await self.manager.task
            analyze.assert_not_called()
            self.assertEqual(self.manager.job['phase'],'cancelled')

    async def test_jev_limit_is_persisted_and_blocks_next_job(self):
        with patch.object(window,'capture',return_value=(dual_images(1),'g')), patch.object(window,'analyze',side_effect=window.Error('http_429: retry_after_seconds=3600')):
            await self.manager.start('jev',1);await self.manager.task
            self.assertFalse(self.manager.providers()['jev']['available'])
            with self.assertRaisesRegex(window.Error,'unavailable'):await self.manager.start('jev',1)
            self.assertTrue(self.manager.quota_path.exists())

    async def test_jev_job_progress_result_and_roles_cover_both_cameras(self):
        with patch.object(window, 'capture', return_value=(dual_images(1), 'g')) as capture, patch.object(window, 'analyze', return_value={'status':'ok','frame_count':20}) as analyze:
            started = await self.manager.start('jev', 1)
            self.assertEqual(started['job']['total'], 20)
            self.assertEqual(started['job']['cameras'], [{'sensor_id':1,'role':'face'},{'sensor_id':0,'role':'study_area'}])
            await self.manager.task
            self.assertIs(capture.call_args.args[-1], True)
            self.assertEqual(analyze.call_count, 1)
            self.assertEqual(self.manager.job['captured'], 20)
            result = self.manager.job['result']
            self.assertEqual(len(result['images']), 20)
            self.assertEqual(result['cameras'], self.manager.job['cameras'])
            self.assertNotIn('data', result['images'][0])
            self.assertNotIn('fixture', json.dumps(self.manager.snapshot()))

    async def test_partial_dual_window_is_not_uploaded(self):
        with patch.object(window, 'capture', return_value=(dual_images()[:-1], 'g')), patch.object(window, 'analyze') as analyze:
            await self.manager.start('jev', 0)
            await self.manager.task
            analyze.assert_not_called()
            self.assertEqual(self.manager.job['phase'], 'failed')

    async def test_legacy_gpt_still_collects_one_camera_ten_frames(self):
        with patch.object(window, 'capture', return_value=(images(), 'g')) as capture, patch.object(window, 'analyze', return_value={'status':'ok'}):
            started = await self.manager.start('openai', 0)
            self.assertEqual(started['job']['total'], 10)
            await self.manager.task
            self.assertIs(capture.call_args.args[-1], False)
            self.assertEqual(self.manager.job['captured'], 10)

    async def test_unknown_provider_and_arbitrary_camera_are_rejected(self):
        for provider,camera in [('other',1),('openai',22),('jev',True)]:
            with self.assertRaises(window.Error):await self.manager.start(provider,camera)


if __name__=='__main__':unittest.main()
