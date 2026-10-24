"""Continuous dual-camera evidence and finite, board-owned GPT-Live sessions."""
import asyncio
import audioop
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
import uuid

from learning_client import rpc, open_stream
from learning_store import Store, SCHEMA_VERSION, HISTORY_LIMIT

INTERVAL = 10.0
MAX_LIVE_SECONDS = 600


class Live:
    def __init__(self, audio, store, events, end_cue=None):
        self.audio, self.store, self.events = audio, store, events
        self.end_cue = end_cue
        self.start_guard = None
        self.task = None
        self.state = {'phase': 'idle', 'max_seconds': 600, 'switch': 1}
        self.stop_event = None

    def snapshot(self):
        value = dict(self.state)
        value['remaining_seconds'] = max(0, round(value.get('deadline', 0) - time.monotonic())) if self.active else 0
        value.pop('deadline', None)
        return value

    @property
    def active(self):
        return self.task is not None and not self.task.done()

    async def start(self, mode='study', source='dashboard', before_start=None):
        if self.start_guard:self.start_guard()
        if self.active or self.state['phase'] == 'preparing':
            raise RuntimeError('이미 Live 대화가 진행 중입니다.')
        if not self.audio.snapshot().get('connected'):
            raise RuntimeError('보드 마이크가 준비되지 않았습니다.')
        if not self.audio.play_lock.acquire(blocking=False):
            raise RuntimeError('스피커가 이미 사용 중입니다.')
        identifier = uuid.uuid4().hex
        self.stop_event = asyncio.Event()
        created = False
        try:
            if before_start is not None:
                self.state = {'phase': 'preparing', 'max_seconds': 600, 'switch': 1,
                              'switch_hold_count': 4, 'source': source}
                await asyncio.get_running_loop().run_in_executor(None, before_start)
                if self.stop_event.is_set():
                    self.state['phase'] = 'idle'
                    self.audio.play_lock.release()
                    return self.snapshot()
            reference = self.store.live_reference()
            self.store.live_start(identifier, mode, source)
            created = True
            metadata = self.store.save_live_reference(identifier, reference)
        except BaseException:
            self.audio.play_lock.release()
            self.state['phase'] = 'failed'
            if created:
                self.store.live_end(identifier, 'reference_preparation_failed', 'failed')
            raise
        self.state = {'id': identifier, 'phase': 'connecting', 'mode': mode, 'source': source,
                      'started': time.time(), 'max_seconds': 600, 'switch': 1, 'error': None,
                      'reference': metadata, 'switch_hold_count': 4}
        self.audio.speaker = {'state': 'live', 'kind': 'gpt-live', 'last_result': None}
        self.task = asyncio.create_task(self.run(identifier, mode, reference))
        return self.snapshot()

    def stop(self):
        if self.active or self.state['phase'] == 'preparing':
            self.state['phase'] = 'closing'
            self.stop_event.set()
        return self.snapshot()

    async def run(self, identifier, mode, reference):
        player = writer = None
        remove = lambda: None
        tasks = []
        finalized, reason, failure = False, 'user_stop', False
        output_until = 0
        bytes_in = bytes_out = 0
        end_announced = False

        async def stop_player():
            nonlocal player
            if player and player.returncode is None:
                player.terminate()
                try:
                    await asyncio.wait_for(player.wait(), 2)
                except asyncio.TimeoutError:
                    player.kill()
                    await player.wait()
            player = None

        async def announce_end():
            nonlocal end_announced
            if self.end_cue is not None and not end_announced:
                end_announced = True
                try:
                    await asyncio.get_running_loop().run_in_executor(None, self.end_cue)
                except Exception:
                    self.events.add('learning', 'Live 종료 안내 음성 재생 실패', 'warning')
        try:
            reader, writer = await open_stream({'op': 'live', 'mode': mode, 'reference': reference})
            # A stop during handshake must not open a microphone or leave a session running.
            first = json.loads(await asyncio.wait_for(reader.readline(), 30))
            if first.get('type') != 'session.started':
                raise RuntimeError('live_start_failed')
            audit = first.get('_application')
            if audit:
                if audit['reference']['sha256'] != self.state['reference']['sha256'] or not all(audit['server_confirmed'].values()):
                    raise RuntimeError('live_reference_confirmation_failed')
                self.state['education'] = audit['education']
                self.state['server_confirmed'] = audit['server_confirmed']
            self.store.live_event(identifier, first)
            self.state.update(phase='active', deadline=time.monotonic() + MAX_LIVE_SECONDS,
                              provider_session_id=first['session']['id'])
            player = await asyncio.create_subprocess_exec('aplay', '-q', '-D', 'robot_playback',
                '-t', 'raw', '-f', 'S16_LE', '-r', '24000', '-c', '1',
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL)
            pcm = asyncio.Queue(maxsize=3)
            remove = self.audio.subscribe_pcm(asyncio.get_running_loop(), pcm)

            async def send_audio():
                nonlocal bytes_in
                converter = None
                while not self.stop_event.is_set():
                    raw = await asyncio.wait_for(pcm.get(), 2)
                    # Half duplex on this board until acoustic echo cancellation is validated.
                    if time.monotonic() < output_until + .25 or self.audio.feedback_active():
                        raw = bytes(len(raw))
                    raw, _ = self.audio.process_pcm(raw, self.audio.gain_db)
                    raw, converter = audioop.ratecv(raw, 2, 1, 48000, 24000, converter)
                    bytes_in += len(raw)
                    writer.write(json.dumps({'type': 'session.input_audio.append',
                                             'audio': base64.b64encode(raw).decode()}).encode() + b'\n')
                    await asyncio.wait_for(writer.drain(), 2)

            async def receive():
                nonlocal output_until, bytes_out, finalized
                while True:
                    raw = await reader.readline()
                    if not raw:
                        raise RuntimeError('live_transport_closed')
                    event = json.loads(raw)
                    kind = event.get('type')
                    if kind == 'session.output_audio.delta':
                        if self.stop_event.is_set():
                            continue
                        data = base64.b64decode(event['delta'], validate=True)
                        if len(data) > 192000 or len(data) % 2:
                            raise RuntimeError('live_audio_invalid')
                        output_until = max(time.monotonic(), output_until) + len(data) / 48000
                        if output_until - time.monotonic() > 4:
                            raise RuntimeError('live_audio_backpressure')
                        bytes_out += len(data)
                        if self.audio.feedback_active():
                            data = audioop.mul(data, 2, .25)
                        player.stdin.write(data)
                        await asyncio.wait_for(player.stdin.drain(), 2)
                    elif kind == 'error':
                        raise RuntimeError('live_provider_error')
                    else:
                        self.store.live_event(identifier, event)
                        if kind == 'session.closed':
                            finalized = True
                            self.state['usage'] = event.get('usage', {})
                            return

            sender, receiver = asyncio.create_task(send_audio()), asyncio.create_task(receive())
            stopper = asyncio.create_task(self.stop_event.wait())
            timer = asyncio.create_task(asyncio.sleep(MAX_LIVE_SECONDS))
            tasks = [sender, receiver, stopper, timer]
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            reason = 'time_limit' if timer in done else 'provider_closed' if receiver in done else 'user_stop'
            for task in done:
                task.result()
            self.stop_event.set()
            self.state['phase'] = 'closing'
            sender.cancel()
            await asyncio.gather(sender, return_exceptions=True)
            remove()
            remove = lambda: None
            await stop_player()
            if not finalized:
                writer.write(b'{"type":"session.close"}\n')
                await asyncio.wait_for(writer.drain(), 2)
            await announce_end()
            if not finalized:
                await asyncio.wait_for(receiver, 6)
        except asyncio.CancelledError:
            failure, reason = True, 'service_shutdown'
        except Exception:
            failure, reason = True, 'live_connection_or_audio_failed'
            self.state['error'] = 'Live 연결·API 권한·보드 오디오를 확인해 주세요. 자동 재연결하지 않습니다.'
        finally:
            remove()
            for task in tasks:
                if not task.done():
                    task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            if writer:
                writer.close()
                try:
                    await asyncio.wait_for(writer.wait_closed(), 2)
                except Exception:
                    pass
            await stop_player()
            phase = 'failed' if failure else 'completed'
            try:
                await announce_end()
            finally:
                self.state.update(phase=phase, finalized=finalized, reason=reason,
                                  input_pcm_bytes=bytes_in, output_pcm_bytes=bytes_out)
                self.audio.speaker = {'state': 'idle', 'kind': 'gpt-live', 'last_result': {'ok': not failure}}
                self.audio.play_lock.release()
                self.store.live_end(identifier, reason, phase)
                self.events.add('learning', 'GPT Live 종료 · ' + reason)

    async def close(self):
        self.stop()
        if self.active:
            try:
                await asyncio.wait_for(asyncio.shield(self.task), 16 if self.end_cue else 9)
            except asyncio.TimeoutError:
                self.task.cancel()
                await self.task


class Learning:
    def __init__(self, cameras, audio, pico, events, path=None, button_audio=None):
        self.cameras, self.pico, self.events = cameras, pico, events
        self.button_audio = button_audio
        self.store = Store(path or os.environ.get('DASHBOARD_LEARNING_DB', '/var/lib/300seconds-dashboard/learning.sqlite3'))
        self.enabled = self.store.setting('collection_enabled', os.environ.get('LEARNING_AUTOSTART', '0') == '1')
        self.live = Live(audio, self.store, events,
                         end_cue=(lambda: button_audio.announce_live('end')) if button_audio else None)
        self.queue = asyncio.Queue(maxsize=2)
        self.tasks = []
        self.running = True
        self.previous = {}
        self.last_error, self.last_capture, self.next_capture = None, None, None
        self.backoff_until = 0
        self.last_analysis = None
        self.wake = asyncio.Event()

    def start(self):
        self.tasks = [asyncio.create_task(self.sample_loop()), asyncio.create_task(self.analysis_loop()),
                      asyncio.create_task(self.switch_loop())]

    def snapshot(self):
        return {'enabled': self.enabled, 'interval_seconds': INTERVAL, 'cameras': [0, 1],
                'queued_batches': self.queue.qsize(), 'last_capture': self.last_capture,
                'next_capture': self.next_capture, 'error': self.last_error,
                'backoff_until': self.backoff_until, 'live': self.live.snapshot(),
                'schema_version': SCHEMA_VERSION, 'raw_images_saved': False,
                'history_limit': HISTORY_LIMIT, 'last_analysis': self.last_analysis}

    def set_enabled(self, enabled):
        self.store.set_setting('collection_enabled', enabled)
        self.enabled = enabled
        if enabled:
            self.last_error, self.backoff_until = None, 0
        else:
            while not self.queue.empty():
                batch, _ = self.queue.get_nowait()
                self.store.finish(batch, error='collection_stopped', status='cancelled')
        self.wake.set()
        return self.snapshot()

    def capture(self):
        if shutil.disk_usage(self.store.path.parent).free < 100 * 1024 * 1024:
            self.set_enabled(False)
            self.last_error = '디스크 여유 100 MiB 미만 · 수집 중지'
            return
        state = self.cameras.snapshot()
        frames, payload = [], []
        for sensor in (0, 1):
            item = {'camera': sensor, 'captured': time.time()}
            try:
                camera = next(c for c in state.get('cameras', []) if c['sensor_id'] == sensor)
                if not state.get('worker_alive') or not camera.get('ready') or state.get('error'):
                    raise ValueError('camera_not_ready')
                if not 0 <= time.monotonic() - state['updated_monotonic'] < 2 or camera.get('preview_age_ms', 9999) >= 1500:
                    raise ValueError('camera_stale')
                with self.cameras.image_path(sensor).open('rb') as stream:
                    stat = os.fstat(stream.fileno())
                    data = stream.read(100001)
                generation = state['run_id']
                if not 0 <= time.time() - stat.st_mtime < 2 or (generation, stat.st_mtime_ns) == self.previous.get(sensor):
                    raise ValueError('camera_stale')
                after = self.cameras.snapshot()
                if after.get('run_id') != generation or not after.get('worker_alive'):
                    raise ValueError('camera_restarted')
                if len(data) > 100000 or not data.startswith(b'\xff\xd8') or not data.endswith(b'\xff\xd9'):
                    raise ValueError('camera_invalid_jpeg')
                self.previous[sensor] = (generation, stat.st_mtime_ns)
                item.update(captured=stat.st_mtime, generation=generation,
                            sha256=hashlib.sha256(data).hexdigest(), stamp=stat.st_mtime_ns,
                            bytes=len(data))
                payload.append({'camera': sensor, 'jpeg': base64.b64encode(data).decode()})
            except (OSError, ValueError, KeyError, StopIteration):
                item.update(status='camera_error', error='camera_not_fresh_or_unavailable')
            frames.append(item)
        batch = self.store.capture(frames, self.live.state.get('id') if self.live.active else None)
        self.last_capture = time.time()
        if payload:
            if self.queue.full():
                self.store.finish(batch, error='analysis_queue_full', status='dropped')
            elif time.time() < self.backoff_until:
                self.store.finish(batch, error='provider_backoff', status='skipped')
            else:
                self.queue.put_nowait((batch, payload))

    async def sample_loop(self):
        deadline = time.monotonic()
        while self.running:
            self.wake.clear()
            if self.enabled:
                try:
                    self.capture()
                except Exception:
                    self.last_error = '데이터베이스 또는 카메라 수집 오류'
                    self.enabled = False
                deadline += INTERVAL
                if deadline <= time.monotonic():
                    deadline = time.monotonic() + INTERVAL
                delay = max(0, deadline - time.monotonic())
                self.next_capture = time.time() + delay
            else:
                delay, self.next_capture = 60, None
            try:
                await asyncio.wait_for(self.wake.wait(), delay)
                deadline = time.monotonic()
            except asyncio.TimeoutError:
                pass

    async def analysis_loop(self):
        while self.running:
            batch, frames = await self.queue.get()
            try:
                if not self.enabled:
                    self.store.finish(batch, error='collection_stopped', status='cancelled')
                elif time.time() < self.backoff_until:
                    self.store.finish(batch, error='provider_backoff', status='skipped')
                else:
                    history = self.store.observation_history(batch)
                    result = await rpc({'op': 'describe', 'frames': frames, 'history': history})
                    self.last_analysis = self.store.finish(batch, result=result, history=history)
                    self.last_error = None
            except asyncio.CancelledError:
                self.store.finish(batch, error='service_shutdown', status='interrupted')
                raise
            except Exception as exc:
                # Never store transport bodies, image payloads or credential-bearing exceptions.
                code = str(exc) if isinstance(exc, RuntimeError) else 'provider_connection_failed'
                if code not in ('credential_missing', 'openai_http_401', 'openai_http_403', 'openai_http_429', 'provider_schema_invalid'):
                    code = 'provider_request_failed'
                self.store.finish(batch, error=code)
                self.last_error = code
                self.backoff_until = time.time() + 60
                if code in ('credential_missing', 'openai_http_401', 'openai_http_403', 'openai_http_429'):
                    self.set_enabled(False)
            finally:
                frames.clear()

    async def switch_loop(self):
        while self.running:
            try:
                request = self.button_audio.take_live_request() if self.button_audio else None
                if request is not None:
                    if self.live.active:
                        self.live.stop()
                    else:
                        def cue():
                            self.button_audio.announce_live('start')
                            if not self.button_audio.live_request_valid(request):
                                raise RuntimeError('Pico 연결이 변경되어 Live 시작을 취소했습니다.')
                        await self.live.start('study', 'SW1-hold4', before_start=cue)
            except Exception:
                self.events.add('learning', 'SW1 Live 시작 실패 · 마이크·스피커·API 연결을 확인하세요.', 'warning')
            await asyncio.sleep(.1)

    async def close(self):
        self.running = False
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        while not self.queue.empty():
            batch, _ = self.queue.get_nowait()
            self.store.finish(batch, error='service_shutdown', status='interrupted')
        await self.live.close()
