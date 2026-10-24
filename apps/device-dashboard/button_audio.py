"""Firmware Touch events -> cached speech and rising tones. No browser or API calls."""
from collections import deque
import hashlib
import io
import json
import math
import os
from pathlib import Path
import threading
import time
import wave

import numpy as np

RATE = 48000
LIVE_HOLD_COUNT = 4


def pitch(count):
    # Half a semitone per count; bounded to a gentle 440..1318.51 Hz.
    return 440 * 2 ** (min(max(int(count) - 1, 0), 38) / 24)


def wav(pcm):
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as writer:
        writer.setparams((1, 2, RATE, 0, 'NONE', 'not compressed'))
        writer.writeframes(pcm)
    return buffer.getvalue()


def beep(counts):
    t = np.arange(round(RATE * .08)) / RATE
    envelope = np.sin(np.pi * np.minimum(1, t / .02) / 2) ** 2
    envelope *= np.sin(np.pi * np.minimum(1, (.08 - t) / .025) / 2) ** 2
    signal = sum(np.sin(2 * np.pi * pitch(count) * t) for count in counts)
    signal = signal / max(1, len(counts)) * envelope * 10 ** (-24 / 20)
    return wav(np.rint(signal * 32767).astype('<i2').tobytes())


def live_tone(action):
    duration = .6
    t = np.arange(round(RATE * duration)) / RATE
    fade = np.minimum(1, np.minimum(t / .03, (duration - t) / .05))
    hz = 660 if action == 'start' else 440
    signal = np.sin(2 * np.pi * hz * t) * fade * 10 ** (-20 / 20)
    return wav(np.rint(signal * 32767).astype('<i2').tobytes())


class ButtonAudio:
    def __init__(self, pico, audio, events, directory=None):
        self.pico, self.audio, self.events = pico, audio, events
        saved = Path('/var/lib/300seconds-dashboard/button-audio')
        bundled = Path(__file__).resolve().parent / 'assets/button-audio'
        configured = directory or os.environ.get('BUTTON_AUDIO_DIR')
        if configured:
            self.directory = Path(configured)
        else:
            try:
                self.directory = saved if saved.exists() else bundled
            except OSError:
                self.directory = bundled
        self.condition = threading.Condition()
        self.queues = {'label': deque(), 'beep': deque()}
        self.assets = {}
        self.live_assets = {}
        self.live_requests = deque(maxlen=1)
        self.study_requests = deque(maxlen=1)
        self.cue_lock = threading.Lock()
        self.announcing = None
        self.running = False
        self.threads = []
        self.remove = lambda: None
        self.session = self.sequence = None
        self.active_counts = {}
        self.sw1_hold = None
        self.study_hold = None
        self.counters = dict(press_events=0, count_events=0, labels_played=0,
                             beeps_played=0, dropped=0, rejected=0, live_hold_requests=0, study_hold_requests=0)
        self.last = None
        self.error = None

    def load(self):
        manifest = json.loads((self.directory / 'manifest.json').read_text())
        entries = [(i, 'button-%d' % i, manifest['buttons'][str(i)]) for i in range(1, 7)]
        entries += [(action, 'live-' + action, manifest['extras']['live-' + action])
                    for action in ('start', 'end')]
        if (manifest['buttons']['1']['text'] != '일번'
                or manifest['extras']['live-start']['text'] != '라이브 대화 시작'
                or manifest['extras']['live-end']['text'] != '라이브 대화 끝'):
            raise ValueError('Live announcement text mismatch')
        for index, stem, item in entries:
            for extension in ('mp3', 'wav'):
                data = (self.directory / (stem + '.' + extension)).read_bytes()
                if hashlib.sha256(data).hexdigest() != item[extension + '_sha256']:
                    raise ValueError('button asset checksum mismatch')
                if extension == 'wav':
                    with wave.open(io.BytesIO(data), 'rb') as reader:
                        if (reader.getnchannels(), reader.getsampwidth(), reader.getframerate()) != (1, 2, RATE):
                            raise ValueError('button asset PCM format')
                        if not 0 < reader.getnframes() <= RATE * 5:
                            raise ValueError('button asset duration')
                        if len(reader.readframes(reader.getnframes())) != reader.getnframes() * 2:
                            raise ValueError('button asset truncated')
                    if index in ('start', 'end'):
                        self.live_assets[index] = data
                    else:
                        self.assets[index] = data

    def start(self):
        try:
            self.load()
        except (OSError, ValueError, KeyError) as error:
            self.error = '버튼 음성 파일 확인 실패: ' + str(error)
            self.events.add('button_audio', self.error, 'error')
        self.running = True
        self.remove = self.pico.subscribe_touch(self.on_touch)
        for kind in ('label', 'beep'):
            thread = threading.Thread(target=self.work, args=(kind,), daemon=True,
                                      name='button-audio-' + kind)
            thread.start()
            self.threads.append(thread)

    def on_touch(self, packet):
        """Only fresh events on the current USB session; never poll last_touch."""
        state = self.pico.snapshot()
        touch = packet.get('touch') or {}
        now = time.monotonic()
        with self.condition:
            if not self.running:
                return
            session = state.get('session')
            if self.session != session:
                self.session, self.sequence = session, None
                self.active_counts.clear()
                self.sw1_hold = None
                self.study_hold = None
                self.live_requests.clear()
                self.study_requests.clear()
                for queue in self.queues.values():
                    queue.clear()
            seq, index = touch.get('event_seq'), touch.get('index')
            device_time = (state.get('device') or {}).get('uptime_ms', 0)
            if (not state.get('connected') or not session or packet.get('session') != session
                    or type(index) is not int or not 1 <= index <= 6
                    or type(seq) is not int or not 0 <= seq <= 0xffffffff
                    or abs(device_time - touch.get('uptime_ms', -10000)) > 2000
                    or abs(time.time() * 1000 - packet.get('host_unix_ms', 0)) > 2000
                    or self.sequence is not None and not 0 < ((seq - self.sequence) & 0xffffffff) < 0x80000000):
                self.counters['rejected'] += 1
                return
            self.sequence = seq
            kind = touch.get('kind')
            if kind == 'Pressed':
                self.active_counts[index] = 0
                self.counters['press_events'] += 1
                item = (now, session, index, 0)
                if index in (1, 2):
                    hold = dict(token=seq, session=session, label_played=False, beeps=set(), requested=False)
                    if index == 1:self.sw1_hold = hold
                    else:self.study_hold = hold
                    item += (seq,)
                self.enqueue('label', item)
            elif kind == 'Interval':
                count = touch.get('interval_count')
                if (touch.get('pressed') is True and type(count) is int
                        and 0 < count <= 0xffffffff and index in self.active_counts
                        and count > self.active_counts[index]):
                    self.active_counts[index] = count
                    self.counters['count_events'] += 1
                    if index not in (1, 2) or count <= LIVE_HOLD_COUNT:
                        item = (now, session, index, count)
                        if index in (1, 2):
                            item += ((self.sw1_hold if index == 1 else self.study_hold)['token'],)
                        self.enqueue('beep', item)
            elif kind == 'Released':
                self.active_counts.pop(index, None)

    def live_request_valid(self, request):
        state = self.pico.snapshot()
        hold = self.sw1_hold if request[2] == 1 else self.study_hold
        return (state.get('connected') and state.get('session') == request[1]
                and (len(request) < 5 or request[2] not in (1, 2)
                     or hold is not None and hold['token'] == request[4]))

    def completed_feedback(self, kind, batch):
        """Called under condition only after ALSA playback succeeds."""
        for item in batch.values():
            hold = self.sw1_hold if item[2] == 1 else self.study_hold
            if (item[2] not in (1, 2) or len(item) < 5 or hold is None
                    or item[4] != hold['token'] or item[1] != hold['session']):
                continue
            if kind == 'label':
                hold['label_played'] = True
            else:
                hold['beeps'].add(item[3])
        for index, hold, requests, counter in [(1, self.sw1_hold, self.live_requests, 'live_hold_requests'),
                (2, self.study_hold, self.study_requests, 'study_hold_requests')]:
            if (hold is not None and hold['label_played'] and not hold['requested']
                    and all(count in hold['beeps'] for count in range(1, LIVE_HOLD_COUNT + 1))):
                requests.append((time.monotonic(), hold['session'], index, LIVE_HOLD_COUNT, hold['token']))
                self.counters[counter] += 1
                hold['requested'] = True

    def take_live_request(self):
        return self.take_request(self.live_requests)

    def take_study_request(self):
        return self.take_request(self.study_requests)

    def take_request(self, requests):
        with self.condition:
            while requests:
                request = requests.popleft()
                if time.monotonic() - request[0] <= 2 and self.live_request_valid(request):
                    return request
                self.counters['dropped'] += 1

    def announce_live(self, action):
        """Blocking completion is required before a microphone/API session may start."""
        with self.cue_lock:
            with self.condition:
                data = self.live_assets.get(action)
                if data is None:
                    raise RuntimeError('Live 시작·종료 안내 MP3가 준비되지 않았습니다.')
                self.announcing = action
            try:
                self.audio.play_feedback(data)
                self.audio.play_feedback(live_tone(action))
                self.events.add('button_audio', '라이브 대화 ' + ('시작' if action == 'start' else '끝') + ' 안내 완료')
            finally:
                with self.condition:
                    self.announcing = None

    def enqueue(self, kind, item):
        queue = self.queues[kind]
        if len(queue) >= 12:
            queue.popleft()
            self.counters['dropped'] += 1
        queue.append(item)
        self.condition.notify_all()

    def take(self, kind):
        queue = self.queues[kind]
        while queue:
            item = queue.popleft()
            limit = 3 if kind == 'label' else .75
            state = self.pico.snapshot()
            if (time.monotonic() - item[0] > limit or not state.get('connected')
                    or state.get('session') != item[1]):
                self.counters['dropped'] += 1
                continue
            return item

    def work(self, kind):
        while True:
            with self.condition:
                while self.running and not self.queues[kind]:
                    self.condition.wait(.5)
                if not self.running:
                    return
                item = self.take(kind)
                batch = {item[2]: item} if item else {}
                if kind == 'beep':
                    while self.queues[kind]:
                        # Preserve each count; never combine two ticks of one hold.
                        if self.queues[kind][0][2] in batch:
                            break
                        extra = self.take(kind)
                        if extra is not None:
                            if extra[2] in batch:
                                self.counters['dropped'] += 1
                            batch[extra[2]] = extra
            if item is None:
                continue
            _, _, index, count = item[:4]
            try:
                data = self.assets.get(index) if kind == 'label' else beep([v[3] for v in batch.values()])
                if data is None:
                    raise ValueError('button-%d.mp3 준비 필요' % index)
                with self.cue_lock:
                    if (time.monotonic() - item[0] > (3 if kind == 'label' else .75)
                            or not self.live_request_valid(item)):
                        with self.condition:
                            self.counters['dropped'] += len(batch)
                        continue
                    self.audio.play_feedback(data)
                with self.condition:
                    self.counters['labels_played' if kind == 'label' else 'beeps_played'] += len(batch)
                    self.completed_feedback(kind, batch)
                    self.last = dict(kind=kind, index=index, count=count, time=time.time(),
                                     pitch_hz=round(pitch(count), 2) if kind == 'beep' else None)
                    self.error = None
            except Exception as error:
                with self.condition:
                    self.error = str(error)[:300]
                self.events.add('button_audio', '버튼 소리 재생 실패: ' + str(error)[:200], 'error')

    def snapshot(self):
        with self.condition:
            return dict(self.counters, running=self.running, ready=len(self.assets) == 6 and len(self.live_assets) == 2,
                        cached_buttons=sorted(self.assets), last=self.last, error=self.error,
                        queued={k: len(v) for k, v in self.queues.items()},
                        base_hz=440, max_hz=round(pitch(100), 2), beep_ms=80,
                        live_hold_count=LIVE_HOLD_COUNT, live_hold_ms=3200, announcing=self.announcing,
                        sw1_beeps_played=len(self.sw1_hold['beeps']) if self.sw1_hold else 0,
                        study_switch=2, study_beeps_played=len(self.study_hold['beeps']) if self.study_hold else 0,
                        source='firmware Touch events / Jetson systemd / cached MP3')

    def close(self):
        self.remove()
        with self.condition:
            self.running = False
            for queue in self.queues.values():
                queue.clear()
            self.live_requests.clear()
            self.study_requests.clear()
            self.condition.notify_all()
        for thread in self.threads:
            thread.join(timeout=5)
