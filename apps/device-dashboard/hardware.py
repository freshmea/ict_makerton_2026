"""Bounded device owners and telemetry; USB is owned only by the Rust bridge."""
from collections import deque
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

ROOT = Path(__file__).resolve().parent
PROFILES = json.loads((ROOT / 'profiles.json').read_text())
INSTALLATION = json.loads((ROOT / 'installation.json').read_text())


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
        self.lock = threading.Lock()
        self.binary = Path(os.environ.get('PICO_BIN', '/opt/300seconds/dashboard/pico-device-bench'))

    def start(self):
        if self.process and self.process.poll() is None:
            return
        self.device = self.received = self.session = self.error = None
        self.last_test = self.last_touch = None
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
                if event == 'status':
                    self.device = value['status']
                    self.received = time.monotonic()
                    self.session = value.get('session')
                    self.error = None
                elif event == 'test_event':
                    self.last_test = value
                    self.module_tests[value['module']] = value
                elif event == 'touch':
                    self.last_touch = value
                elif event in ('error', 'cleanup_unconfirmed'):
                    self.error = value.get('error', event)
            if event in ('touch', 'test_event', 'error', 'bridge_ready', 'cleanup_unconfirmed'):
                self.events.add('pico', json.dumps(value, ensure_ascii=False),
                                'warning' if event in ('error', 'cleanup_unconfirmed') else 'info')
        process.wait()
        self.events.add('pico', 'USB 브리지 종료. 연결 재시도는 수동으로 실행합니다.', 'warning')

    def snapshot(self):
        with self.lock:
            age = int((time.monotonic() - self.received) * 1000) if self.received else None
            alive = self.process is not None and self.process.poll() is None
            return {'connected': alive and age is not None and age < 1500,
                    'age_ms': age, 'device': self.device, 'session': self.session,
                    'error': self.error, 'last_test': self.last_test, 'last_touch': self.last_touch,
                    'module_tests': dict(self.module_tests),
                    'bridge_pid': self.process.pid if alive else None,
                    'port': '/dev/pico-device', 'protocol': 'pico-device-v1',
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
                                         '--bind', os.environ.get('DASHBOARD_BIND', '192.168.219.127'),
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
            value['ready'] = alive and fresh and not value.get('error') and all(c['ready'] for c in value['cameras'])
            if not fresh or not alive:
                for camera in value['cameras']:
                    camera['ready'] = False
            return value
        except (OSError, ValueError, KeyError):
            return {'profile': self.profile, 'ready': False, 'cameras': [],
                    'error': '카메라 스트림 준비 중', 'settings': PROFILES[self.profile]}

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

    def __init__(self, events):
        self.events = events
        self.lock = threading.Lock()
        self.play_lock = threading.Lock()
        self.ring = deque(maxlen=60)
        self.process = None
        self.last_pcm = None
        self.error = None
        self.level = {'rms_dbfs': -96.0, 'peak_dbfs': -96.0, 'waveform': []}
        self.speaker = {'state': 'idle', 'last_result': None}
        self.running = True

    def start(self):
        threading.Thread(target=self.capture, daemon=True).start()

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
                    values = np.frombuffer(data[:len(data) // 2 * 2], dtype='<i2').astype(np.float32) / 32768
                    if not len(values):
                        continue
                    rms = float(np.sqrt(np.mean(values * values)))
                    peak = float(np.max(np.abs(values)))
                    with self.lock:
                        self.ring.append(data)
                        self.last_pcm = time.monotonic()
                        self.error = None
                        self.level = {'rms_dbfs': round(20 * math.log10(max(rms, 1e-5)), 1),
                                      'peak_dbfs': round(20 * math.log10(max(peak, 1e-5)), 1),
                                      'waveform': np.round(values[::max(1, len(values) // 128)][:128], 4).tolist()}
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
            return dict(self.level, connected=age is not None and age < 1500,
                        age_ms=age, error=self.error, rate=self.RATE, channels=1,
                        buffered_seconds=round(sum(len(x) for x in self.ring) / self.RATE / 2, 1),
                        speaker=dict(self.speaker))

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
        if not self.snapshot()['connected']:
            raise RuntimeError('마이크가 연결되어 있지 않습니다.')
        with self.lock:
            data = b''.join(self.ring)[-int(seconds * self.RATE * 2):]
        if not data:
            raise RuntimeError('오디오 버퍼가 준비되지 않았습니다.')
        return self.wav(data)

    def playback(self, kind):
        if not self.play_lock.acquire(blocking=False):
            raise RuntimeError('스피커가 이미 재생 중입니다.')
        try:
            if kind == 'tone':
                samples = []
                for hz in (660, 880, 1100):
                    t = np.arange(int(.3 * self.RATE)) / self.RATE
                    fade = np.minimum(1, np.minimum(t / .015, (.3 - t) / .015))
                    signal_data = np.sin(2 * np.pi * hz * t) * fade * .10
                    samples.append((signal_data * 32767).astype('<i2').tobytes())
                    samples.append(b'\0' * int(.1 * self.RATE) * 2)
                data = self.wav(b''.join(samples))
            elif kind == 'replay':
                data = self.recording(2)
            else:
                raise ValueError('Unknown playback action.')
            self.speaker = {'state': 'playing', 'last_result': None, 'kind': kind}
            result = subprocess.run(['aplay', '-q', '-D', 'robot_playback', '-t', 'wav', '-'],
                                    input=data, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=8)
            self.speaker = {'state': 'idle' if result.returncode == 0 else 'error',
                            'last_result': {'ok': result.returncode == 0, 'time': time.time(),
                                            'output': result.stdout.decode(errors='replace')[:500]}, 'kind': kind}
            self.events.add('audio', '스피커 PCM 재생 ' + ('성공' if result.returncode == 0 else '실패'))
            if result.returncode:
                raise RuntimeError(result.stdout.decode(errors='replace'))
            return self.speaker
        except (subprocess.TimeoutExpired, OSError) as error:
            self.speaker = {'state': 'error', 'last_result': {'ok': False, 'time': time.time(), 'output': str(error)}}
            self.events.add('audio', str(error), 'error')
            raise RuntimeError('스피커 재생 실패: ' + str(error))
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
