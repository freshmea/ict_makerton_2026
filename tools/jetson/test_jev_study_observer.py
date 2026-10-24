"""Contract and failure tests; no external API calls or real credentials."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import struct
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

spec = importlib.util.spec_from_file_location('observer', Path(__file__).with_name('jev-study-observer.py'))
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)


def response(**changes):
    answers = {name: {'type': 'noul', 'noul': .95}
               for name in ['seat_observable', 'person_present', 'behavior_observable', 'gaze_observable']}
    answers.update({name: {'type': 'score', 'score': 3.2, 'confidence': .8}
                    for name in ['focus_score', 'study_gaze_score']})
    for name, value in changes.items():
        answers[name].update(value)
    return {'model': 'fixture', 'answers': answers}


class ContractTests(unittest.TestCase):
    def test_score_scale_and_real_boolean(self):
        result = observer.normalize(response())
        self.assertEqual(result['focus_score'], 8)
        self.assertEqual(result['study_gaze_score'], 8)
        self.assertIs(result['is_away'], False)
        self.assertEqual(result['status'], 'ok')

    def test_scale_endpoints(self):
        result = observer.normalize(response(focus_score={'score': 0}, study_gaze_score={'score': 4}))
        self.assertEqual((result['focus_score'], result['study_gaze_score']), (0, 10))

    def test_empty_seat_is_not_scored_as_unfocused(self):
        result = observer.normalize(response(person_present={'noul': .05}))
        self.assertIs(result['is_away'], True)
        self.assertIsNone(result['focus_score'])
        self.assertIsNone(result['study_gaze_score'])

    def test_bad_view_cannot_be_called_away(self):
        result = observer.normalize(response(seat_observable={'noul': .01}, person_present={'noul': .01}))
        self.assertIsNone(result['is_away'])
        self.assertEqual(result['status'], 'unknown')

    def test_clear_person_closeup_confirms_presence_without_seat_overview(self):
        result = observer.normalize(response(seat_observable={'noul': .03}, person_present={'noul': 1},
                                             behavior_observable={'noul': .01}, gaze_observable={'noul': 0}))
        self.assertIs(result['is_away'], False)
        self.assertIsNone(result['focus_score'])
        self.assertIsNone(result['study_gaze_score'])
        self.assertEqual(result['status'], 'partial')

    def test_unclear_person_and_hidden_seat_remain_unknown(self):
        for probability in [.01, .5]:
            with self.subTest(probability=probability):
                result = observer.normalize(response(seat_observable={'noul': .03}, person_present={'noul': probability}))
                self.assertIsNone(result['is_away'])

    def test_uncertain_presence_never_forces_boolean(self):
        self.assertIsNone(observer.normalize(response(person_present={'noul': .5}))['is_away'])

    def test_gaze_hidden_does_not_hide_valid_behavior(self):
        result = observer.normalize(response(gaze_observable={'noul': .2}))
        self.assertEqual(result['focus_score'], 8)
        self.assertIsNone(result['study_gaze_score'])
        self.assertEqual(result['status'], 'partial')

    def test_low_score_confidence_suppresses_score(self):
        result = observer.normalize(response(focus_score={'confidence': .1}))
        self.assertIsNone(result['focus_score'])

    def test_invalid_numbers_and_refusals_fail(self):
        for value in [True, '3', float('nan'), float('inf'), -1, 4.01]:
            with self.subTest(value=value), self.assertRaises(observer.ObserverError):
                observer.normalize(response(focus_score={'score': value}))
        bad = response()
        bad['answers']['person_present'] = {'type': 'refusal'}
        with self.assertRaises(observer.ObserverError):
            observer.normalize(bad)

    def test_missing_answer_fails(self):
        bad = response()
        del bad['answers']['seat_observable']
        with self.assertRaises(observer.ObserverError):
            observer.normalize(bad)

    def test_rubric_has_supported_level_count(self):
        for question in observer.questions().values():
            if question['type'] == 'score':
                self.assertEqual(len(question['criteria']), 5)

    def test_payload_references_and_no_raw_media_in_metadata(self):
        config = observer.settings({})
        image = {'ref': 'long-unique-ref', 'data': b'not-a-real-frame', 'sensor_id': 0}
        body = observer.make_body(config, [image], [{'views': {'person': image['ref']}}])
        self.assertIn(image['ref'], json.dumps(body['state']))
        self.assertEqual(body['assets'][image['ref']]['format'], 'jpg')
        self.assertNotIn('data', observer.metadata([image])[0])

    def test_key_missing_prevents_capture(self):
        with patch.object(observer, 'capture') as capture:
            with self.assertRaisesRegex(observer.ObserverError, 'credential_missing'):
                observer.execute('analyze', observer.settings({}), {})
            capture.assert_not_called()

    def test_analyze_composes_request_and_only_returns_metadata(self):
        image = {'ref': 'unique-fixture-image', 'data': b'private-image', 'sensor_id': 0,
                 'bytes': 13, 'width': 640, 'height': 360}
        groups = [{'views': {'person': image['ref']}}]
        with patch.object(observer, 'capture', return_value=([image], groups, 'fixture-generation')):
            with patch.object(observer, 'json_request', return_value=(response(), 10)) as transport:
                result = observer.execute('analyze', observer.settings({}), {'OPENCODE_API_KEY': 'fixture-only'})
        self.assertTrue(result['uploaded'])
        self.assertEqual(result['focus_score'], 8)
        self.assertEqual(transport.call_args.args[1]['model'], 'jev-1.13-free')
        serialized = json.dumps(result)
        self.assertNotIn('private-image', serialized)
        self.assertNotIn('fixture-only', serialized)
        self.assertNotIn('data_base64', serialized)

    def test_key_cannot_be_sent_to_another_host(self):
        with self.assertRaisesRegex(observer.ObserverError, 'endpoint_mismatch'):
            observer.request('https://example.com', {}, 'fixture-only')

    def test_jpeg_dimension_contract(self):
        jpeg = b'\xff\xd8\xff\xc0' + struct.pack('>HBHHB', 8, 8, 360, 640, 0) + b'\xff\xd9'
        self.assertEqual(observer.jpeg_size(jpeg), (640, 360))
        short = b'\xff\xd8\xff\xc0' + struct.pack('>HBHHB', 8, 8, 240, 320, 0) + b'\xff\xd9'
        with self.assertRaisesRegex(observer.ObserverError, 'dimensions'):
            observer.jpeg_size(short)
        with self.assertRaises(observer.ObserverError):
            observer.jpeg_size(b'not a jpeg')

    def test_free_usage_limit_is_reported_without_echoing_body(self):
        body = json.dumps({'error': {'type': 'FreeUsageLimitError', 'message': 'private echoed input'}}).encode()
        error = HTTPError(observer.ENDPOINT, 429, 'limited', {'Retry-After': '71109'}, io.BytesIO(body))
        opener = unittest.mock.Mock()
        opener.open.side_effect = error
        with patch.object(observer, 'build_opener', return_value=opener):
            with self.assertRaises(observer.ObserverError) as caught:
                observer.request(observer.ENDPOINT, {}, 'fixture-only')
        self.assertIn('FreeUsageLimitError', str(caught.exception))
        self.assertIn('retry_after_seconds=71109', str(caught.exception))
        self.assertNotIn('private echoed input', str(caught.exception))

    def test_provider_errors_never_echo_credentials_or_input(self):
        secret = 'fixture-secret-never-persist'
        error = HTTPError(observer.ENDPOINT, 400, 'bad', {}, io.BytesIO(secret.encode()))
        opener = unittest.mock.Mock()
        opener.open.side_effect = error
        with patch.object(observer, 'build_opener', return_value=opener):
            with self.assertRaises(observer.ObserverError) as caught:
                observer.request(observer.ENDPOINT, {'state': 'private scene'}, secret)
        self.assertNotIn(secret, str(caught.exception))
        self.assertNotIn('private scene', str(caught.exception))

    def test_model_and_dashboard_origin_guards(self):
        for values in [{'JEV_MODEL': 'unrelated-model'}, {'JEV_DASHBOARD_URL': 'https://example.com'},
                       {'JEV_DASHBOARD_URL': 'http://user:pw@192.168.1.2:8000'},
                       {'JEV_SEAT_ROI': '0,0,2,1'}, {'JEV_SAMPLES': '200'}]:
            with self.subTest(values=values), self.assertRaises(observer.ObserverError):
                observer.settings(values)

    def test_paid_model_is_blocked_before_any_request(self):
        with self.assertRaisesRegex(observer.ObserverError, 'free_only_policy'):
            observer.settings({'JEV_MODEL': 'jev-1.13'})

    def test_camera_generation_and_freshness_are_required(self):
        state = {'cameras': {'ready': True, 'worker_alive': True, 'run_id': 'current',
                            'cameras': [{'sensor_id': i, 'ready': True, 'preview_age_ms': 10} for i in (0, 1)]}}
        with patch.object(observer, 'json_request', return_value=(state, 1)):
            self.assertEqual(observer.camera_status(observer.settings({})), 'current')
            with self.assertRaisesRegex(observer.ObserverError, 'restarted'):
                observer.camera_status(observer.settings({}), 'previous')
            state['cameras']['cameras'][0]['preview_age_ms'] = 2000
            with self.assertRaisesRegex(observer.ObserverError, 'stale'):
                observer.camera_status(observer.settings({}))

    def test_environment_is_data_not_shell_code(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'test.env'
            p.write_text('OPENCODE_API_KEY="literal-$(not-executed)"\n', encoding='utf-8')
            p.chmod(0o600)
            with patch.dict(observer.os.environ, {}, clear=True):
                self.assertEqual(observer.load_config(p)['OPENCODE_API_KEY'], 'literal-$(not-executed)')
            p.write_text('OPENCODE_API_KEY=a\nOPENCODE_API_KEY=b\n', encoding='utf-8')
            with self.assertRaisesRegex(observer.ObserverError, 'invalid_env'):
                observer.load_config(p)


if __name__ == '__main__':
    unittest.main()
