"""OpenAI Decisions schema and spending safeguards; no real API calls."""
import importlib.util
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

spec = importlib.util.spec_from_file_location('openai_observer', Path(__file__).with_name('openai-study-observer.py'))
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)


def response():
    answers = []
    for q in observer.decision_questions():
        a = {'name': q['name'], 'type': q['type']}
        a.update({'probability': .95} if q['type'] == 'predicate' else {'score': 3.2, 'confidence': .8})
        answers.append(a)
    return {'model': observer.MODEL, 'answers': answers, 'usage': {'input_tokens': 1000, 'output_tokens': 0}}


def text_body():
    return observer.base_body([{'type': 'input_text', 'text': 'fixture'}],
                              [{'name': 'lamp_on', 'type': 'predicate', 'instructions': 'Lamp on?'}])


class DecisionsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.budget = observer.Budget(Path(self.temp.name) / 'budget.json')

    def tearDown(self):
        self.temp.cleanup()

    def test_five_attempt_cap_persists_across_instances(self):
        for _ in range(5):
            identifier = self.budget.reserve({})
            self.budget.finish(identifier, 200, {'input_tokens': 10})
        other = observer.Budget(self.budget.path)
        with self.assertRaisesRegex(observer.Error, 'budget_exhausted'):
            other.reserve({})
        self.assertEqual(other.status()['reserved_usd'], '0.10')

    def test_input_usage_cost_and_unknown_attempt_are_separate(self):
        first = self.budget.reserve({})
        self.budget.finish(first, 200, {'input_tokens': 1234})
        self.budget.reserve({})
        status = self.budget.status()
        self.assertEqual(status['known_standard_cost_usd'], '0.0001234')
        self.assertEqual(status['unknown_cost_attempts'], 1)

    def test_parallel_lock_does_not_allow_another_reservation(self):
        with self.budget.locked():
            with self.assertRaisesRegex(observer.Error, 'budget_busy'):
                self.budget.reserve({})

    def test_corrupt_budget_fails_closed(self):
        self.budget.path.write_text('broken', encoding='utf-8')
        with self.assertRaisesRegex(observer.Error, 'budget_corrupt'):
            self.budget.reserve({})

    def test_rate_limit_stops_later_calls(self):
        identifier = self.budget.reserve({})
        self.budget.finish(identifier, 429, retry_after='300')
        with self.assertRaisesRegex(observer.Error, 'cooldown'):
            self.budget.reserve({})

    def test_timeout_never_retries_and_keeps_reservation(self):
        opener = Mock()
        opener.open.side_effect = URLError('test timeout')
        with patch.object(observer, 'build_opener', return_value=opener):
            with self.assertRaisesRegex(observer.Error, 'no automatic retry'):
                observer.call(text_body(), 'fixture-key', self.budget, 'fixture')
        self.assertEqual(opener.open.call_count, 1)
        self.assertEqual(self.budget.status()['attempts'], 1)
        with self.assertRaisesRegex(observer.Error, 'cooldown'):
            self.budget.reserve({})

    def test_unauthorized_does_not_log_body_or_retry(self):
        error = HTTPError(observer.ENDPOINT, 401, 'bad', {'x-request-id': 'fixture-request'}, io.BytesIO(b'fixture-key private-data'))
        opener = Mock()
        opener.open.side_effect = error
        with patch.object(observer, 'build_opener', return_value=opener):
            with self.assertRaises(observer.Error) as caught:
                observer.call(text_body(), 'fixture-key', self.budget, 'fixture')
        self.assertNotIn('fixture-key', str(caught.exception))
        self.assertNotIn('private-data', self.budget.path.read_text())

    def test_decisions_mapping_keeps_0_to_10_and_boolean(self):
        result = observer.normalize(response())
        self.assertEqual(result['focus_score'], 8)
        self.assertIs(result['is_away'], False)

    def test_camera_two_closeup_keeps_occupancy_and_withholds_study_scores(self):
        data = response()
        values = {'seat_observable': .03, 'person_present': 1, 'behavior_observable': .01, 'gaze_observable': 0}
        for answer in data['answers']:
            if answer['name'] in values:
                answer['probability'] = values[answer['name']]
        result = observer.normalize(data)
        self.assertIs(result['is_away'], False)
        self.assertIsNone(result['focus_score'])
        self.assertIsNone(result['study_gaze_score'])

    def test_refusal_preserves_other_observations(self):
        data = response()
        for i, answer in enumerate(data['answers']):
            if answer['name'] == 'study_gaze_score':
                data['answers'][i] = {'name': answer['name'], 'type': 'refusal'}
        result = observer.normalize(data)
        self.assertEqual(result['focus_score'], 8)
        self.assertIsNone(result['study_gaze_score'])
        self.assertEqual(result['refused_questions'], ['study_gaze_score'])

    def test_missing_or_duplicated_answers_fail(self):
        for data in [dict(response(), answers=[]), dict(response(), answers=[response()['answers'][0]] * 6)]:
            with self.assertRaises(observer.Error):
                observer.normalize(data)

    def test_only_fixed_model_and_disabled_cache_allowed(self):
        for body in [dict(text_body(), model='gpt-6-astra'), dict(text_body(), prompt_cache_options={})]:
            with self.assertRaises(observer.Error):
                observer.bounded_summary(body, 'fixture')

    def test_external_images_and_excessive_input_are_blocked(self):
        for content in [[{'type': 'input_image', 'image_url': 'https://example.com/photo.jpg', 'detail': 'low'}],
                        [{'type': 'input_text', 'text': 'x' * 20001}]]:
            with self.assertRaises(observer.Error):
                observer.bounded_summary(observer.base_body(content, text_body()['questions']), 'fixture')

    def test_missing_key_makes_no_reservation(self):
        with self.assertRaisesRegex(observer.Error, 'credential_missing'):
            observer.call(text_body(), '', self.budget, 'fixture')
        self.assertEqual(self.budget.status()['attempts'], 0)

    def test_camera_pipeline_makes_one_request_and_only_returns_metadata(self):
        jpeg = b'\xff\xd8\xff\xc0' + struct.pack('>HBHHB', 8, 8, 360, 640, 0) + b'\xff\xd9'
        image = {'sensor_id': 0, 'data': jpeg, 'ref': 'fixture', 'received_at_utc': 'fixture-time', 'bytes': len(jpeg)}
        config = observer.camera.settings({'JEV_PERSON_CAMERA': '0', 'JEV_DESK_CAMERA': '0'})
        with patch.object(observer.camera, 'capture', return_value=([image], [], 'generation')):
            with patch.object(observer, 'call', return_value=(response(), {'wall_ms': 1})) as call:
                result = observer.execute('analyze', 'fixture-key', config, self.budget)
        body = call.call_args.args[0]
        self.assertEqual(observer.bounded_summary(body, 'fixture')['images'], 1)
        self.assertEqual(call.call_count, 1)
        self.assertNotIn('data:image', json.dumps(result))
        self.assertNotIn('fixture-key', json.dumps(result))


if __name__ == '__main__':
    unittest.main()
