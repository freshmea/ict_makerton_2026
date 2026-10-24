#!/usr/bin/env python3
"""Budgeted one-shot OpenAI Decisions tests; no background calls or retries.

Uses the existing Nano OPENAI_API_KEY; never changes runtime provider settings.
Shares camera capture and observation normalization with jev-study-observer.py.
"""
import argparse
import base64
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.request import build_opener, ProxyHandler, Request
import uuid

spec = importlib.util.spec_from_file_location('camera_observer', Path(__file__).with_name('jev-study-observer.py'))
camera = importlib.util.module_from_spec(spec)
spec.loader.exec_module(camera)
Error = camera.ObserverError

ENDPOINT = 'https://api.openai.com/v1/decisions'
MODEL = 'gpt-6-luna'
BUDGET_PATH = Path('/var/lib/300seconds-observer/openai-budget.json')
MAX_ATTEMPTS = 5
SESSION_CAP = Decimal('0.10')
RESERVATION = Decimal('0.02')
INPUT_USD_PER_MILLION = Decimal('0.10')
MAX_INPUT_TOKENS_RESERVED = 200000


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class Budget:
    """Persistent local test-session cap, not an account-wide billing meter."""
    def __init__(self, path=BUDGET_PATH):
        self.path = path

    @contextmanager
    def locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.path.with_name(self.path.name + '.lock')
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise Error('budget_busy_or_stale_lock: no request sent') from None
        try:
            os.close(fd)
            yield
        finally:
            lock.unlink()

    def read(self):
        if not self.path.exists():
            return {'created_at_utc': timestamp(), 'attempts': [], 'cooldown_until': 0}
        if self.path.is_symlink() or self.path.stat().st_size > 65536:
            raise Error('invalid_budget_file')
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or not isinstance(data.get('attempts'), list):
                raise ValueError()
            return data
        except (ValueError, OSError):
            raise Error('budget_corrupt: no request sent') from None

    def write(self, data):
        temporary = self.path.with_name(self.path.name + '.' + uuid.uuid4().hex + '.tmp')
        camera.save_result(temporary, data)
        if os.name != 'nt' and self.path.exists() and os.geteuid() == 0:
            previous = self.path.stat()
            os.chown(str(temporary), previous.st_uid, previous.st_gid)
        os.replace(str(temporary), str(self.path))

    def status(self):
        with self.locked():
            data = self.read()
        attempts = data['attempts']
        known = [Decimal(a['estimated_standard_cost_usd']) for a in attempts if a.get('estimated_standard_cost_usd') is not None]
        return {'local_only': True, 'attempts': len(attempts), 'max_attempts': MAX_ATTEMPTS,
                'session_cap_usd': str(SESSION_CAP),
                'reserved_usd': str(RESERVATION * len(attempts)),
                'known_standard_cost_usd': str(sum(known, Decimal(0))),
                'unknown_cost_attempts': sum(a.get('estimated_standard_cost_usd') is None for a in attempts),
                'cooldown_until_unix': data.get('cooldown_until', 0),
                'account_balance': 'not queried; see OpenAI billing', 'automatic_retry': False}

    def reserve(self, summary):
        with self.locked():
            data = self.read()
            if data.get('cooldown_until', 0) > time.time():
                raise Error('provider_cooldown: no request sent')
            count = len(data['attempts'])
            if count >= MAX_ATTEMPTS or RESERVATION * (count + 1) > SESSION_CAP:
                raise Error('local_budget_exhausted: no request sent')
            identifier = uuid.uuid4().hex
            data['attempts'].append({'id': identifier, 'at_utc': timestamp(), 'state': 'pending',
                                     'reserved_usd': str(RESERVATION), 'request': summary})
            self.write(data)
            return identifier

    def finish(self, identifier, status, usage=None, request_id=None, retry_after=None):
        with self.locked():
            data = self.read()
            entry = next((a for a in data['attempts'] if a['id'] == identifier), None)
            if entry is None:
                raise Error('budget_attempt_missing')
            entry.update(state='completed' if status == 200 else 'failed', http_status=status,
                         request_id=request_id, completed_at_utc=timestamp(), usage=usage)
            if usage is not None:
                tokens = usage.get('input_tokens')
                if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens < 0:
                    entry['usage_invalid'] = True
                else:
                    entry['estimated_standard_cost_usd'] = str(Decimal(tokens) * INPUT_USD_PER_MILLION / 1000000)
                    if tokens > MAX_INPUT_TOKENS_RESERVED:
                        data['cooldown_until'] = 10 ** 12
                        entry['reservation_exceeded'] = True
            if status in (401, 402, 403):
                data['cooldown_until'] = 10 ** 12
            elif status == 429:
                data['cooldown_until'] = time.time() + (int(retry_after) if str(retry_after).isdigit() else 3600)
            elif status == 0:
                # A timed-out POST might have been processed. Do not retry it.
                data['cooldown_until'] = 10 ** 12
            self.write(data)


def bounded_summary(body, name):
    if body.get('model') != MODEL:
        raise Error('only_gpt_6_luna_allowed')
    if body.get('prompt_cache_options') != {'mode': 'explicit'}:
        raise Error('test_requires_cache_disabled')
    questions = body.get('questions', [])
    if not 1 <= len(questions) <= 24:
        raise Error('question_count_limit')
    images, text_bytes = 0, 0
    for message in body.get('input', []):
        for part in message.get('content', []):
            if part.get('type') == 'input_image':
                images += 1
                url = part.get('image_url', '')
                if not url.startswith('data:image/jpeg;base64,') or part.get('detail') != 'low':
                    raise Error('only_inline_low_detail_jpeg_allowed')
                try:
                    raw = base64.b64decode(url.split(',', 1)[1], validate=True)
                except ValueError:
                    raise Error('invalid_inline_image') from None
                width, height = camera.jpeg_size(raw)
                if width > 640 or height > 640 or len(raw) > 100000:
                    raise Error('test_image_size_limit')
            elif part.get('type') == 'input_text':
                text_bytes += len(part.get('text', '').encode())
            else:
                raise Error('unsupported_test_content')
    text_bytes += len(json.dumps(questions, ensure_ascii=False).encode())
    if images > 10 or text_bytes > 20000:
        raise Error('test_payload_limit')
    return {'name': name, 'model': MODEL, 'images': images, 'text_bytes': text_bytes,
            'questions': len(questions), 'detail': 'low', 'cache': 'disabled',
            'reservation_input_token_allowance': MAX_INPUT_TOKENS_RESERVED}


def call(body, key, budget, name):
    summary = bounded_summary(body, name)
    if not key or not key.isascii() or any(c.isspace() for c in key):
        raise Error('credential_missing_or_invalid: OPENAI_API_KEY')
    identifier = budget.reserve(summary)
    payload = json.dumps(body, ensure_ascii=False, allow_nan=False).encode()
    headers = {'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json',
               'User-Agent': '300seconds-openai-observer/0.1', 'Accept': 'application/json'}
    start = time.monotonic()
    try:
        with build_opener(ProxyHandler({}), camera.NoRedirect()).open(
                Request(ENDPOINT, data=payload, headers=headers), timeout=30) as response:
            request_id = response.headers.get('x-request-id')
            raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise Error('provider_response_too_large')
            data = json.loads(raw)
    except HTTPError as exc:
        status, request_id = exc.code, exc.headers.get('x-request-id')
        retry_after = exc.headers.get('Retry-After')
        budget.finish(identifier, status, request_id=request_id, retry_after=retry_after)
        exc.close()
        raise Error('openai_http_%d; request_id=%s' % (status, request_id or 'unavailable')) from None
    except (URLError, TimeoutError, OSError):
        budget.finish(identifier, 0)
        raise Error('openai_network_or_timeout: no automatic retry') from None
    except (ValueError, Error):
        budget.finish(identifier, 200)
        raise Error('provider_response_unusable: cost unknown') from None
    usage = data.get('usage') if isinstance(data, dict) else None
    budget.finish(identifier, 200, usage=usage if isinstance(usage, dict) else None, request_id=request_id)
    if not isinstance(data, dict) or not isinstance(usage, dict):
        raise Error('provider_usage_missing')
    tokens = usage.get('input_tokens')
    if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens < 0:
        raise Error('provider_usage_invalid')
    if data.get('model', '').split('-2026')[0] != MODEL:
        raise Error('returned_model_mismatch')
    return data, {'wall_ms': round((time.monotonic() - start) * 1000, 1),
                  'request_id': request_id, 'usage': usage,
                  'standard_input_cost_estimate_usd': str(Decimal(usage['input_tokens']) * INPUT_USD_PER_MILLION / 1000000),
                  'pricing': 'standard uncached input $0.10/1M; output free; cache disabled; invoice authoritative',
                  'local_budget': budget.status()}


def base_body(content, questions):
    return {'model': MODEL, 'input': [{'role': 'user', 'content': content}],
            'questions': questions, 'prompt_cache_options': {'mode': 'explicit'}}


def decision_questions():
    result = []
    for name, question in camera.questions().items():
        instruction = question['instructions']
        if instruction.startswith(camera.COMMON):
            instruction = instruction[len(camera.COMMON):]
        item = {'name': name, 'type': 'predicate' if question['type'] == 'noul' else 'score',
                'instructions': instruction}
        if question['type'] == 'score':
            item['levels'] = [{'label': str(i), 'description': description}
                              for i, description in enumerate(question['criteria'])]
        result.append(item)
    return result


def normalize(data):
    answers = data.get('answers')
    expected = {q['name']: q for q in decision_questions()}
    if not isinstance(answers, list) or len(answers) != len(expected):
        raise Error('decision_answer_count_mismatch')
    translated, refusals = {}, []
    for answer in answers:
        name = answer.get('name')
        if name not in expected or name in translated:
            raise Error('decision_answer_name_mismatch')
        kind = expected[name]['type']
        if answer.get('type') == 'refusal':
            refusals.append(name)
            translated[name] = {'type': 'noul', 'noul': .5} if kind == 'predicate' else {'type': 'score', 'score': 0, 'confidence': 0}
        elif answer.get('type') != kind:
            raise Error('decision_answer_type_mismatch')
        elif kind == 'predicate':
            translated[name] = {'type': 'noul', 'noul': answer.get('probability')}
        else:
            translated[name] = {'type': 'score', 'score': answer.get('score'), 'confidence': answer.get('confidence')}
    result = camera.normalize({'answers': translated})
    result['refused_questions'] = refusals
    return result


def execute(command, key, config, budget):
    if command == 'budget':
        return {'status': 'ok', 'budget': budget.status()}
    if command == 'auth-test':
        body = base_body([{'type': 'input_text', 'text': 'The desk lamp is on.'}],
                         [{'type': 'predicate', 'name': 'lamp_on', 'instructions': 'Is the lamp on?'}])
        data, meta = call(body, key, budget, 'text_smoke')
        answers = data.get('answers', [])
        if len(answers) != 1 or answers[0].get('type') != 'predicate' or answers[0].get('name') != 'lamp_on':
            raise Error('smoke_answer_contract_invalid')
        probability = camera.number(answers[0].get('probability'), 0, 1)
        return dict(meta, status='ok', test='live_decisions_text', model=data['model'], lamp_on_probability=probability)
    images, groups, generation = camera.capture(config)
    content = [{'type': 'input_text', 'text': camera.COMMON + '\nCamera evidence metadata: ' +
                json.dumps({'seat_roi': config['roi'], 'camera_roles': {'person': config['person'], 'desk': config['desk']}}, ensure_ascii=False)}]
    for image in images:
        roles = [role for role, sensor in [('person', config['person']), ('desk', config['desk'])] if sensor == image['sensor_id']]
        content.append({'type': 'input_text', 'text': 'Camera %d; roles %s; received %s' % (image['sensor_id'], ','.join(roles), image['received_at_utc'])})
        content.append({'type': 'input_image', 'detail': 'low',
                        'image_url': 'data:image/jpeg;base64,' + base64.b64encode(image['data']).decode()})
    data, meta = call(base_body(content, decision_questions()), key, budget, 'camera_%s' % ','.join(str(i['sensor_id']) for i in images))
    return dict(meta, **normalize(data), test='live_decisions_camera', model=data['model'],
                camera_generation=generation, images=camera.metadata(images), raw_answers=data['answers'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['budget', 'auth-test', 'analyze'])
    parser.add_argument('--env-file', type=Path, default=Path('/etc/300seconds/ai.env'))
    parser.add_argument('--camera-env-file', type=Path, default=Path('/etc/300seconds/jev-observer.env'))
    parser.add_argument('--cameras', default='0', choices=['0', '1', '0,1'])
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        values = camera.load_config(args.env_file)
        key = os.environ.get('OPENAI_API_KEY', values.get('OPENAI_API_KEY', ''))
        values = camera.load_config(args.camera_env_file)
        ids = [int(v) for v in args.cameras.split(',')]
        values.update(JEV_MODEL='jev-1.13-free', JEV_SAMPLES='1',
                      JEV_PERSON_CAMERA=str(ids[0]), JEV_DESK_CAMERA=str(ids[-1]))
        result = execute(args.command, key, camera.settings(values), Budget())
        result['at_utc'] = timestamp()
        code = 0
    except Error as exc:
        result, code = {'status': 'error', 'error': str(exc), 'at_utc': timestamp()}, 1
    if args.output:
        camera.save_result(args.output, result)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
