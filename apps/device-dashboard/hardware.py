"""Bounded device owners and telemetry; USB is owned only by the Rust bridge."""
from collections import deque
import audioop
import io
import json
import math
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid
import wave

import numpy as np
import psutil
from tts_client import synthesize
from servo_reference import load_reference

ROOT = Path(__file__).resolve().parent
PROFILES = json.loads((ROOT / 'profiles.json').read_text(encoding='utf-8'))
INSTALLATION = json.loads((ROOT / 'installation.json').read_text(encoding='utf-8'))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.new')
    temporary.write_text(json.dumps(value))
    temporary.replace(path)


class EventLog:
    def __init__(self):
        self.items = deque(maxlen=80)
        self.lock = threading.Lock()

    def add(self, source, message, level='info'):
        with self.lock:
            self.items.appendleft({'id': uuid.uuid4().hex[:10], 'time': time.time(),
                                   'source': source, 'message': str(message)[:400], 'level': level})

    def snapshot(self):
        with self.lock:
            return list(self.items)


class Pico:
    def __init__(self, events):
        self.events = events
        self.process = None
        self.device = None
        self.received = None
        self.session = None
        self.error = None
        self.last_test = None
        self.module_tests = {}
        self.last_touch = None
        self.touch_listeners = set()
        self.outputs = None
        self.last_applied = None
        self.capabilities = {}
        self.servo_driver = None
        self.seed_session = None
        self.lock = threading.Lock()
        self.binary = Path(os.environ.get('PICO_BIN', '/opt/300seconds/dashboard/pico-device-bench'))

    def start(self):
        if self.process and self.process.poll() is None:
            return
        self.device = self.received = self.session = self.error = None
        self.last_test = self.last_touch = None
        self.outputs = self.last_applied = None
        self.capabilities = {}
        self.servo_driver = None
        self.module_tests = {}
        port = Path('/dev/pico-device')
        if not port.exists():
            self.error = ('현재 Pico는 통합 c0de:cafc 이미지가 아닙니다.' if Path('/dev/pico-neopixel').exists()
                          else 'Pico USB 장치를 찾을 수 없습니다.')
            self.events.add('pico', self.error, 'warning')
            return
        try:
            self.process = subprocess.Popen([str(self.binary), '--port', str(port), 'bridge',
                                             '--config', str(ROOT / 'pico-config.json'),
                                             '--listen', '127.0.0.1:37920'], stdout=subprocess.PIPE,
                                            stderr=subprocess.STDOUT, universal_newlines=True,
                                            bufsize=1)
            threading.Thread(target=self.read, args=(self.process,), daemon=True).start()
        except Exception as error:
            self.error = str(error)

    def read(self, process):
        for line in process.stdout:
            try:
                value = json.loads(line)
            except ValueError:
                self.events.add('pico', line.strip(), 'warning')
                continue
            event = value.get('event')
            if event == 'touch' and not INSTALLATION['touch_inputs_connected']:
                continue
            with self.lock:
                seed_needed = False
                if event == 'status':
                    self.device = value['status']
                    self.received = time.monotonic()
                    self.session = value.get('session')
                    self.error = None
                    self.outputs = value.get('outputs', self.outputs)
                    self.capabilities = value.get('capabilities', self.capabilities)
                    self.servo_driver = value.get('servo_driver', self.servo_driver)
                    if self.session and self.seed_session != self.session:
                        self.seed_session = self.session
                        seed_needed = True
                elif event == 'capabilities':
                    self.capabilities = {'single_servo': value.get('single_servo', False)}
                elif event == 'outputs':
                    self.outputs = value['outputs']
                elif event == 'servo_driver':
                    self.servo_driver = value['status']
                elif event == 'applied':
                    self.last_applied = value
                elif event == 'test_event':
                    self.last_test = value
                    self.module_tests[value['module']] = value
                elif event == 'touch':
                    self.last_touch = value
                elif event in ('error', 'cleanup_unconfirmed'):
                    self.error = value.get('error', event)
                listeners = list(self.touch_listeners) if event == 'touch' else []
            if seed_needed:
                threading.Thread(target=self.seed_reference,args=(self.session,),daemon=True).start()
            for callback in listeners:
                try:
                    callback(value)
                except Exception:
                    self.events.add('pico', '버튼 이벤트 수신기 오류', 'warning')
            if event in ('touch', 'test_event', 'error', 'bridge_ready', 'cleanup_unconfirmed'):
                self.events.add('pico', json.dumps(value, ensure_ascii=False),
                                'warning' if event in ('error', 'cleanup_unconfirmed') else 'info')
        process.wait()
        self.events.add('pico', 'USB 브리지 종료. 연결 재시도는 수동으로 실행합니다.', 'warning')

    def subscribe_touch(self, callback):
        with self.lock:
            self.touch_listeners.add(callback)
        def remove():
            with self.lock:
                self.touch_listeners.discard(callback)
        return remove

    def seed_reference(self, session):
        values=load_reference()
        if not any(v is not None for v in values):return
        error=None
        for attempt in range(4):
            state=self.snapshot()
            if state.get('session')!=session:return
            try:
                result=self.command({'cmd':'seed_servo_positions',
                                     'positions_cdeg':[v*100 if v is not None else None for v in values]})
                if not result.get('ok'):raise RuntimeError(result.get('error','reference rejected'))
                self.events.add('servo','마지막 완료 목표각 복원 · PWM 출력 없음')
                return
            except Exception as failure:
                error=failure
                time.sleep(.1*2**attempt)
        self.events.add('servo','목표각 참조 복원 실패: '+str(error)[:180],'warning')

    def snapshot(self):
        with self.lock:
            age = int((time.monotonic() - self.received) * 1000) if self.received else None
            alive = self.process is not None and self.process.poll() is None
            return {'connected': alive and age is not None and age < 1500,
                    'age_ms': age, 'device': self.device, 'session': self.session,
                    'error': self.error, 'last_test': self.last_test, 'last_touch': self.last_touch,
                    'module_tests': dict(self.module_tests),
                    'bridge_pid': self.process.pid if alive else None,
                    'outputs': self.outputs, 'last_applied': self.last_applied,
                    'capabilities': dict(self.capabilities),
                    'servo_driver': self.servo_driver,
                    'port': '/dev/pico-device', 'protocol': 'pico-device-v2',
                    'installation': INSTALLATION}

    def command(self, command):
        if not self.snapshot()['connected']:
            raise RuntimeError('Pico 상태가 오래되었거나 연결되어 있지 않습니다.')
        # Independent sockets let Stop preempt another outstanding native request.
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
            client.settimeout(6)
            client.bind(('127.0.0.1', 0))
            client.sendto(json.dumps(command).encode(), ('127.0.0.1', 37920))
            data, peer = client.recvfrom(8193)
            if peer != ('127.0.0.1', 37920) or len(data) > 8192:
                raise RuntimeError('잘못된 USB 브리지 응답입니다.')
        result = json.loads(data)
        self.events.add('pico', '%s → %s' % (command, 'ACK' if result.get('ok') else result.get('error')))
        return result

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.send_signal(signal.SIGINT)
            try:
                self.process.wait(timeout=7)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)


class Cameras:
    def __init__(self, runtime, events):
        self.runtime, self.events = runtime, events
        self.process = None
        self.run_id = None
        self.log_file = None
        self.settings_path = Path(os.environ.get('DASHBOARD_SETTINGS', '/var/lib/300seconds-dashboard/settings.json'))
        self.profile = '720p30'
        try:
            saved = json.loads(self.settings_path.read_text()).get('profile')
            if saved in PROFILES:
                self.profile = saved
        except (OSError, ValueError):
            pass

    def start(self, profile=None):
        if profile is not None and profile not in PROFILES:
            raise ValueError('Unknown camera profile.')
        self.stop()
        self.profile = profile or self.profile
        self.run_id = uuid.uuid4().hex
        self.runtime.mkdir(parents=True, exist_ok=True)
        self.process = subprocess.Popen([sys.executable, '-B', str(ROOT / 'media_worker.py'),
                                         '--runtime', str(self.runtime), '--profile', self.profile,
                                         '--run-id', self.run_id,
                                         '--bind', os.environ.get('DASHBOARD_BIND', '127.0.0.1'),
                                         '--encoder', os.environ.get('CAMERA_ENCODER', 'omxh264enc')],
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        env=dict(os.environ, DISPLAY=''))
        threading.Thread(target=self.drain_log, args=(self.process,), daemon=True).start()
        self.events.add('camera', '두 센서 촬영 시작 · ' + PROFILES[self.profile]['label'])

    def drain_log(self, process):
        path = self.runtime / 'media.log'
        with path.open('wb') as output:
            for line in iter(process.stdout.readline, b''):
                if output.tell() + len(line) > 262144:
                    output.seek(0)
                    output.truncate()
                output.write(line[:262144])
                output.flush()

    def set_profile(self, profile):
        previous = self.profile
        self.start(profile)
        deadline = time.monotonic() + 18
        while time.monotonic() < deadline:
            state = self.snapshot()
            if state.get('ready'):
                write_json(self.settings_path, {'profile': profile})
                return state
            if self.process.poll() is not None:
                break
            time.sleep(.25)
        self.events.add('camera', '프로필 적용 실패. 이전 프로필로 복구합니다.', 'error')
        self.start(previous)
        raise RuntimeError('카메라 프로필이 시작되지 않아 이전 설정으로 복구했습니다.')

    def snapshot(self):
        try:
            value = json.loads((self.runtime / 'camera-state.json').read_text())
            if value.get('run_id') != self.run_id:
                raise ValueError('Starting a new generation.')
            fresh = time.monotonic() - value['updated_monotonic'] < 2
            alive = self.process is not None and self.process.poll() is None
            value['worker_alive'] = alive
            value['ready'] = alive and fresh and not value.get('error') and len(value['cameras']) == 2 and all(c['ready'] for c in value['cameras'])
            if not fresh or not alive or value.get('error'):
                for camera in value['cameras']:
                    camera['ready'] = False
            unavailable = []
            for camera in value['cameras']:
                if not camera['ready'] and value.get('uptime_seconds', 0) >= 15:
                    camera['error'] = '영상 수신 없음 · 카메라 연결·전원을 확인하세요.'
                    unavailable.append(str(camera['sensor_id'] + 1))
            value['warning'] = ('카메라 %s 영상 없음 · 연결·전원 확인 필요' % ', '.join(unavailable)) if unavailable else None
            return value
        except (OSError, ValueError, KeyError):
            return {'profile': self.profile, 'ready': False, 'cameras': [],
                    'error': '카메라 스트림 준비 중', 'settings': PROFILES[self.profile]}

    @staticmethod
    def can_preview(state, sensor):
        # Aggregate ready remains strict for two-camera analysis. A healthy
        # preview must not wait for the other sensor to recover.
        return state.get('worker_alive') is True and not state.get('error') and any(
            c.get('sensor_id') == sensor and c.get('ready') is True and
            isinstance(c.get('preview_age_ms'), (int, float)) and 0 <= c['preview_age_ms'] < 2000
            for c in state.get('cameras', []))

    def image_path(self, sensor):
        return self.runtime / ('cam%d.jpg' % sensor)

    def stop(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        if self.log_file:
            self.log_file.close()
            self.log_file = None


class Audio:
    RATE = 48000
    DEFAULT_GAIN_DB = 12.0
    MAX_GAIN_DB = 30.0
    PEAK_CEILING_DBFS = -1.0
    METER_SECONDS = 3

    def __init__(self, events):
        self.events = events
        self.lock = threading.Lock()
        self.play_lock = threading.Lock()
        self.feedback_until = 0.0
        self.ring = deque(maxlen=60)
        self.process = None
        self.last_pcm = None
        self.error = None
        self.settings_path = Path(os.environ.get(
            'DASHBOARD_AUDIO_SETTINGS', '/var/lib/300seconds-dashboard/audio-settings.json'))
        self.gain_db = self.DEFAULT_GAIN_DB
        try:
            self.gain_db = self.validate_gain(json.loads(self.settings_path.read_text())['gain_db'])
        except (OSError, ValueError, KeyError, TypeError):
            pass
        self.speaker = {'state': 'idle', 'last_result': None}
        self.running = True
        self.pcm_subscribers = set()

    @classmethod
    def validate_gain(cls, gain_db):
        gain = float(gain_db)
        if not math.isfinite(gain) or not 0 <= gain <= cls.MAX_GAIN_DB:
            raise ValueError('마이크 증폭은 0~30 dB 범위로 지정하세요.')
        return gain

    @classmethod
    def process_pcm(cls, data, gain_db):
        """Use one linear gain for the whole clip, capped before S16 conversion.

        The in-memory capture stays raw. Metering, WAV export and board replay
        share this path so samples are never amplified twice. Peak protection
        reduces the whole clip's gain rather than clipping individual samples.
        """
        gain_db = cls.validate_gain(gain_db)
        raw = np.frombuffer(data[:len(data) // 2 * 2], dtype='<i2').astype(np.float32)
        requested = 10 ** (gain_db / 20)
        ceiling = math.floor(32767 * 10 ** (cls.PEAK_CEILING_DBFS / 20))
        raw_peak = float(np.max(np.abs(raw))) if len(raw) else 0.0
        applied = min(requested, ceiling / raw_peak) if raw_peak else requested
        # Rounding is bounded before casting to prevent int16 wraparound.
        pcm = np.clip(np.rint(raw * applied), -ceiling, ceiling).astype('<i2')
        values = pcm.astype(np.float32) / 32768
        original = raw / 32768

        def levels(samples):
            if not len(samples):
                return -96.0, -96.0
            rms = float(np.sqrt(np.mean(samples * samples)))
            peak = float(np.max(np.abs(samples)))
            return tuple(round(20 * math.log10(max(value, 10 ** (-96 / 20))), 1)
                         for value in (rms, peak))

        rms, peak = levels(values)
        raw_rms, raw_peak_dbfs = levels(original)
        recent = values[-cls.RATE // 10:]
        return pcm.tobytes(), {
            'rms_dbfs': rms, 'peak_dbfs': peak,
            'raw_rms_dbfs': raw_rms, 'raw_peak_dbfs': raw_peak_dbfs,
            'gain_db': gain_db, 'applied_gain_db': round(20 * math.log10(applied), 1),
            'limiter_active': applied < requested - 1e-6,
            'peak_ceiling_dbfs': cls.PEAK_CEILING_DBFS,
            'meter_seconds': round(len(pcm) / cls.RATE, 1),
            'waveform': np.round(recent[::max(1, len(recent) // 128)][:128], 4).tolist(),
        }

    def set_gain(self, gain_db):
        gain = self.validate_gain(gain_db)
        with self.lock:
            # A separate file keeps the camera profile settings intact.
            write_json(self.settings_path, {'gain_db': gain})
            self.gain_db = gain
        self.events.add('audio', '마이크 녹음 증폭 +%g dB · 피크 보호 -1 dBFS' % gain)
        return self.snapshot()

    def start(self):
        threading.Thread(target=self.capture, daemon=True).start()

    def subscribe_pcm(self, loop, queue):
        subscriber = (loop, queue)
        with self.lock:
            self.pcm_subscribers.add(subscriber)
        def remove():
            with self.lock:
                self.pcm_subscribers.discard(subscriber)
        return remove

    @staticmethod
    def deliver_pcm(queue, data):
        if queue.full():
            queue.get_nowait()
        queue.put_nowait(data)

    def capture(self):
        while self.running:
            try:
                self.process = subprocess.Popen(['arecord', '-q', '-D', 'robot_capture', '-t', 'raw',
                                                 '-f', 'S16_LE', '-r', str(self.RATE), '-c', '1'],
                                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                while self.running:
                    data = self.process.stdout.read(9600)
                    if not data:
                        break
                    data = data[:len(data) // 2 * 2]
                    if not data:
                        continue
                    with self.lock:
                        self.ring.append(data)
                        self.last_pcm = time.monotonic()
                        self.error = None
                        subscribers = list(self.pcm_subscribers)
                    for loop, queue in subscribers:
                        if not loop.is_closed():
                            loop.call_soon_threadsafe(self.deliver_pcm, queue, data)
                if self.running:
                    self.error = self.process.stderr.read().decode(errors='replace')[:500] or '마이크 스트림 종료'
                    self.events.add('audio', self.error, 'error')
            except Exception as error:
                self.error = str(error)
                self.events.add('audio', self.error, 'error')
            if self.running:
                time.sleep(3)

    def snapshot(self):
        with self.lock:
            age = round((time.monotonic() - self.last_pcm) * 1000) if self.last_pcm else None
            buffered = b''.join(self.ring)
            data = buffered[-self.METER_SECONDS * self.RATE * 2:]
            gain, error, speaker = self.gain_db, self.error, dict(self.speaker)
        _, level = self.process_pcm(data, gain)
        return dict(level, connected=age is not None and age < 1500,
                    age_ms=age, error=error, rate=self.RATE, channels=1,
                    buffered_seconds=round(len(buffered) / self.RATE / 2, 1), speaker=speaker)

    @staticmethod
    def wav(data, channels=1):
        output = io.BytesIO()
        with wave.open(output, 'wb') as writer:
            writer.setnchannels(channels)
            writer.setsampwidth(2)
            writer.setframerate(Audio.RATE)
            writer.writeframes(data)
        return output.getvalue()

    def recording(self, seconds=3):
        with self.lock:
            if self.last_pcm is None or time.monotonic() - self.last_pcm >= 1.5:
                raise RuntimeError('마이크가 연결되어 있지 않습니다.')
            data = b''.join(self.ring)[-int(seconds * self.RATE * 2):]
            gain = self.gain_db
        if not data:
            raise RuntimeError('오디오 버퍼가 준비되지 않았습니다.')
        processed, _ = self.process_pcm(data, gain)
        return self.wav(processed)

    def playback(self, kind):
        if not self.play_lock.acquire(blocking=False):
            raise RuntimeError('스피커가 이미 재생 중입니다.')
        try:
            if kind == 'tone':
                samples = []
                for hz in (660, 880, 1100):
                    t = np.arange(int(.3 * self.RATE)) / self.RATE
                    fade = np.minimum(1, np.minimum(t / .015, (.3 - t) / .015))
                    signal_data = np.sin(2 * np.pi * hz * t) * fade * .16
                    samples.append((signal_data * 32767).astype('<i2').tobytes())
                    samples.append(b'\0' * int(.1 * self.RATE) * 2)
                data = self.wav(b''.join(samples))
            elif kind == 'replay':
                data = self.recording(2)
            else:
                raise ValueError('Unknown playback action.')
            return self.play_wav(data, kind, 8)
        except (subprocess.TimeoutExpired, OSError) as error:
            self.speaker = {'state': 'error', 'last_result': {'ok': False, 'time': time.time(), 'output': str(error)}}
            self.events.add('audio', str(error), 'error')
            raise RuntimeError('스피커 재생 실패: ' + str(error))
        finally:
            self.play_lock.release()

    def play_wav(self, data, kind, timeout):
        self.speaker = {'state': 'playing', 'last_result': None, 'kind': kind}
        result = subprocess.run(['aplay', '-q', '-D', 'robot_playback', '-t', 'wav', '-'],
                                input=data, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
        self.speaker = {'state': 'idle' if result.returncode == 0 else 'error',
                        'last_result': {'ok': result.returncode == 0, 'time': time.time(),
                                        'output': result.stdout.decode(errors='replace')[:500]}, 'kind': kind}
        self.events.add('audio', '스피커 PCM 재생 ' + ('성공' if result.returncode == 0 else '실패'))
        if result.returncode:
            raise RuntimeError(result.stdout.decode(errors='replace')[:500])
        return self.speaker

    def feedback_active(self):
        with self.lock:
            return time.monotonic() < self.feedback_until

    def play_feedback(self, data):
        """Cached button audio shares ALSA dmix, including while Live owns play_lock."""
        with wave.open(io.BytesIO(data), 'rb') as reader:
            duration = reader.getnframes() / reader.getframerate()
        with self.lock:
            self.feedback_until = max(self.feedback_until, time.monotonic() + duration + .25)
        result = subprocess.run(['aplay', '-q', '-D', 'robot_playback', '-t', 'wav', '-'],
                                input=data, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                timeout=max(3, duration + 2))
        if result.returncode:
            raise RuntimeError(result.stdout.decode(errors='replace')[:300])

    def tts(self, text):
        if not self.play_lock.acquire(blocking=False):
            raise RuntimeError('스피커가 이미 재생 또는 TTS 합성 중입니다.')
        try:
            self.speaker = {'state': 'synthesizing', 'kind': 'tts', 'last_result': None}
            data, metadata = synthesize(text)
            with wave.open(io.BytesIO(data), 'rb') as reader:
                rate, frames = reader.getframerate(), reader.getnframes()
                if (reader.getnchannels() != 1 or reader.getsampwidth() != 2
                        or not 8000 <= rate <= 48000 or not 0 < frames <= rate * 30):
                    raise ValueError('TTS 오디오 형식이 올바르지 않습니다.')
                raw = reader.readframes(frames)
                if len(raw) != frames * 2:
                    raise ValueError('TTS 오디오가 완전하지 않습니다.')
            if rate != self.RATE:
                raw = audioop.ratecv(raw, 2, 1, rate, self.RATE, None)[0]
            # Independent of microphone gain: speech +6 dB, linear peak cap -1 dBFS.
            amplified, level = self.process_pcm(raw, 6)
            speaker = self.play_wav(self.wav(amplified), 'tts', 35)
            return {'speaker': speaker, 'tts': metadata,
                    'gain_db': 6, 'applied_gain_db': level['applied_gain_db'],
                    'limiter_active': level['limiter_active']}
        except Exception as error:
            message = str(error) if isinstance(error, (RuntimeError, ValueError)) else 'TTS 서비스 연결 또는 재생에 실패했습니다.'
            self.speaker = {'state': 'error', 'kind': 'tts',
                            'last_result': {'ok': False, 'time': time.time(), 'output': message}}
            self.events.add('audio', message, 'error')
            raise RuntimeError(message) from error
        finally:
            self.play_lock.release()

    def stop(self):
        self.running = False
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()


class Metrics:
    def __init__(self):
        self.running = True
        self.state = {}
        self.history = deque(maxlen=60)
        threading.Thread(target=self.sample, daemon=True).start()

    def sample(self):
        while self.running:
            cpu = psutil.cpu_percent(interval=.5)
            memory = psutil.virtual_memory()
            gpu = None
            for path in ('/sys/devices/57000000.gpu/load', '/sys/devices/gpu.0/load'):
                try:
                    gpu = int(Path(path).read_text()) / 10
                    break
                except (OSError, ValueError):
                    pass
            temperatures = []
            for path in Path('/sys/class/thermal').glob('thermal_zone*/temp'):
                try:
                    temperatures.append(int(path.read_text()) / 1000)
                except (OSError, ValueError):
                    pass
            self.history.append(cpu)
            self.state = {'cpu_percent': cpu, 'gpu_percent': gpu,
                          'memory_used_mib': round(memory.used / 1048576),
                          'memory_total_mib': round(memory.total / 1048576),
                          'memory_percent': memory.percent,
                          'temperature_c': round(max(temperatures), 1) if temperatures else None,
                          'uptime_seconds': round(time.monotonic()), 'cpu_history': list(self.history)}
