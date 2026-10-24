#!/usr/bin/env python3
"""Unprivileged analysis worker; keys never enter the dashboard process."""
import asyncio
import json
import os
from pathlib import Path
import re
import signal
import socket
import struct
import threading
import time
import uuid

import study_window as window
from learning_provider import Provider, ProviderError, VISION_MODEL
from live_education import policy

STATE = Path('/var/lib/300seconds-observer')
SOCKET = Path('/run/300seconds-observer/observer.sock')
CAMERA_RUNTIME = Path('/run/300seconds-dashboard')


def error_text(code):
    if '429' in code or 'cooldown' in code:
        return 'API 사용 한도로 대기 중입니다. 자동 재시도하지 않습니다.'
    if 'budget' in code:
        return '설정한 테스트 예산 또는 횟수에 도달했습니다.'
    if '401' in code or '403' in code or 'credential' in code:
        return 'API 인증 또는 접근 권한을 확인해 주세요.'
    if 'timing' in code or 'stale' in code or 'restarted' in code or 'camera' in code:
        return '카메라의 최신 사진을 안정적으로 수집하지 못했습니다.'
    if '400' in code:
        return 'API가 이미지 요청 형식을 거부했습니다. 제공자의 이미지 지원 확인이 필요합니다.'
    return '분석을 완료하지 못했습니다. 진단 코드를 확인해 주세요.'


class Manager:
    def __init__(self, keys, state=STATE, runtime=CAMERA_RUNTIME, budget=None):
        self.keys, self.state, self.runtime = keys, state, runtime
        self.budget = budget or window.openai.Budget()
        self.task, self.cancel_event = None, threading.Event()
        self.job = {'phase': 'idle', 'captured': 0, 'total': 20, 'result': None}
        self.quota_path = state / 'provider-state.json'
        self.quotas = json.loads(self.quota_path.read_text()) if self.quota_path.exists() else {'jev_blocked_until': 0}
        self.loop = None

    def providers(self):
        now = time.time()
        try:
            budget = self.budget.status()
            openai_ready = budget['attempts'] < budget['max_attempts'] and budget['cooldown_until_unix'] <= now
        except window.Error:
            budget, openai_ready = {'error': 'budget_unavailable'}, False
        return {
            'openai': {'configured': bool(self.keys.get('OPENAI_API_KEY')), 'available': bool(self.keys.get('OPENAI_API_KEY')) and openai_ready, 'budget': budget,
                       'frame_count': window.FRAME_COUNT, 'camera_count': 1},
            'jev': {'configured': bool(self.keys.get('OPENCODE_API_KEY')), 'available': bool(self.keys.get('OPENCODE_API_KEY')) and self.quotas.get('jev_blocked_until', 0) <= now,
                    'blocked_until_unix': self.quotas.get('jev_blocked_until', 0), 'free_only': True,
                    'frame_count': window.FRAME_COUNT * 2, 'camera_count': 2}}

    def snapshot(self):
        return {'online': True, 'job': self.job, 'providers': self.providers(),
                'categories': window.category_catalog(), 'study_area': 'desk',
                'frame_count': self.job['total'], 'frames_per_camera': window.FRAME_COUNT,
                'interval_seconds': window.INTERVAL}

    async def start(self, provider, camera_id):
        if provider not in ('jev', 'openai') or type(camera_id) is not int or camera_id not in (0, 1):
            raise window.Error('request_invalid')
        if self.task and not self.task.done():
            raise window.Error('observer_busy')
        if not self.providers()[provider]['available']:
            raise window.Error('provider_cooldown_or_budget_or_key_unavailable')
        self.loop = asyncio.get_running_loop()
        self.cancel_event = threading.Event()
        cameras = window.camera_roles(provider, camera_id)
        self.job = {'id': uuid.uuid4().hex, 'provider': provider, 'camera': camera_id,
                    'cameras': cameras, 'frames_per_camera': window.FRAME_COUNT,
                    'phase': 'capturing', 'captured': 0, 'total': window.FRAME_COUNT * len(cameras),
                    'started_at_utc': window.jev.now(), 'result': None, 'error': None}
        self.task = self.loop.create_task(self.run(self.job['id'], provider, camera_id, self.cancel_event))
        return self.snapshot()

    def progress(self, job_id, count):
        if self.job.get('id') == job_id:
            self.job['captured'] = count

    async def run(self, job_id, provider, camera_id, cancelled):
        images = []
        try:
            progress = lambda count: self.loop.call_soon_threadsafe(self.progress, job_id, count)
            images, generation = await self.loop.run_in_executor(None, window.capture, self.runtime, camera_id, cancelled, progress, provider == 'jev')
            if cancelled.is_set():
                raise window.Cancelled('capture_cancelled')
            if len(images) != self.job['total']:
                raise window.Error('camera_window_incomplete')
            self.job['phase'] = 'analyzing'
            result = await self.loop.run_in_executor(None, window.analyze, provider, images, self.keys, self.budget)
            result.update(camera=camera_id, generation=generation,
                          cameras=window.camera_roles(provider, camera_id),
                          frames_per_camera=window.FRAME_COUNT,
                          images=window.jev.metadata(images), completed_at_utc=window.jev.now())
            self.job.update(phase='completed', captured=len(images), result=result, completed_at_utc=window.jev.now())
        except window.Cancelled:
            self.job.update(phase='cancelled', result=None, error=None)
        except window.Error as exc:
            code = str(exc)[:240]
            if provider == 'jev' and 'http_429' in code:
                match = re.search(r'retry_after_seconds=(\d+)', code)
                self.quotas['jev_blocked_until'] = time.time() + (int(match.group(1)) if match else 3600)
                window.jev.save_result(self.quota_path, self.quotas)
            self.job.update(phase='failed', result=None, error=error_text(code), error_code=code)
        except Exception:
            self.job.update(phase='failed', result=None, error=error_text('internal'), error_code='observer_internal_error')
        finally:
            images.clear()

    def cancel(self):
        if self.job['phase'] not in ('capturing', 'cancelling'):
            raise window.Error('capture_not_cancellable')
        self.cancel_event.set()
        self.job['phase'] = 'cancelling'
        return self.snapshot()

    async def close(self):
        self.cancel_event.set()
        if self.task:
            await self.task


async def serve():
    import pwd
    keys = {name: os.environ.pop(name, '') for name in ('OPENAI_API_KEY', 'OPENCODE_API_KEY')}
    manager = Manager(keys)
    learning = Provider(keys.get('OPENAI_API_KEY', ''))
    allowed = {0, pwd.getpwnam('boarddash').pw_uid}

    async def handle(reader, writer):
        try:
            peer = writer.get_extra_info('socket').getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
            if struct.unpack('3i', peer)[1] not in allowed:
                raise window.Error('peer_not_allowed')
            line = await asyncio.wait_for(reader.readline(), 5)
            if len(line) > 280000:
                raise window.Error('request_too_large')
            command = json.loads(line)
            op = command.get('op')
            if op == 'learning_status' and set(command) == {'op'}:
                result = {'configured': bool(learning.key), 'vision_model': VISION_MODEL,
                          'live_model': 'gpt-live-1', 'live_busy': learning.live_busy, 'education': policy()}
            elif op == 'learning_policy' and set(command) == {'op'}:
                result = policy(include_text=True)
            elif op == 'describe' and set(command) == {'op', 'frames'}:
                result = await learning.description(command['frames'])
            elif op == 'live' and set(command) in ({'op', 'mode'}, {'op', 'mode', 'reference'}):
                try:
                    await learning.live(reader, writer, command['mode'], command.get('reference'))
                except Exception:
                    writer.write(b'{"type":"error","code":"live_connection_failed"}\n')
                    await writer.drain()
                finally:
                    writer.close()
                    await writer.wait_closed()
                return
            elif len(line) > 2048:
                raise window.Error('request_too_large')
            elif op == 'status' and set(command) == {'op'}:
                result = manager.snapshot()
            elif op == 'start' and set(command) == {'op', 'provider', 'camera'}:
                result = await manager.start(command['provider'], command['camera'])
            elif op == 'cancel' and set(command) == {'op'}:
                result = manager.cancel()
            else:
                raise window.Error('request_invalid')
            reply = {'ok': True, 'data': result}
        except (window.Error, ProviderError, ValueError, asyncio.TimeoutError) as exc:
            reply = {'ok': False, 'error': str(exc)[:240]}
        except Exception:
            reply = {'ok': False, 'error': 'observer_internal_error'}
        try:
            writer.write(json.dumps(reply, ensure_ascii=False, allow_nan=False).encode() + b'\n')
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    SOCKET.parent.mkdir(parents=True, exist_ok=True)
    if SOCKET.exists():
        SOCKET.unlink()
    server = await asyncio.start_unix_server(handle, str(SOCKET), limit=280001)
    SOCKET.chmod(0o660)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    async with server:
        await stop.wait()
    await manager.close()
    SOCKET.unlink(missing_ok=True)


if __name__ == '__main__':
    asyncio.run(serve())
