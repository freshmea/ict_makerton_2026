#!/usr/bin/env python3
"""Short real USB capture/playback/duplex test. WAVs stay in the board test dir.

Run as the audio service user after configuring named robot_* ALSA PCMs.
Only low-amplitude finite test tones are generated; no mixer maximum is set.
"""
import argparse
import array
import datetime
import json
import math
import os
from pathlib import Path
import subprocess
import time
import wave

RATE = 48000
parser = argparse.ArgumentParser()
parser.add_argument('output_dir')
args = parser.parse_args()
out = Path(args.output_dir)
out.mkdir(parents=True, exist_ok=True)
os.umask(0o077)
report = {'at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'uid': os.getuid(), 'sample_rate': RATE, 'commands': []}


def command(argv, timeout=15):
    start = time.monotonic()
    p = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       universal_newlines=True, timeout=timeout)
    report['commands'].append({'argv': argv, 'exit_code': p.returncode,
                               'elapsed_seconds': time.monotonic() - start, 'output': p.stdout})
    if p.returncode:
        raise RuntimeError(p.stdout)
    return p


def samples(path):
    with wave.open(str(path), 'rb') as f:
        metadata = {'channels': f.getnchannels(), 'rate': f.getframerate(), 'frames': f.getnframes(),
                    'sample_width': f.getsampwidth()}
        values = array.array('h', f.readframes(f.getnframes()))
    return metadata, values


def stats(values):
    rms = math.sqrt(sum(v * v for v in values) / max(1, len(values)))
    return {'samples': len(values), 'rms_dbfs': 20 * math.log10(max(rms, 1e-9) / 32768),
            'peak': max((abs(v) for v in values), default=0),
            'clipped_samples': sum(abs(v) >= 32767 for v in values),
            'nonzero_fraction': sum(v != 0 for v in values) / max(1, len(values))}


def power(values, frequency):
    w = 2 * math.pi * frequency / RATE
    coeff = 2 * math.cos(w)
    a = b = 0.0
    for value in values:
        new = value + coeff * a - b
        b, a = a, new
    return max(a * a + b * b - coeff * a * b, 1e-12) / max(1, len(values)) ** 2


try:
    # Known sequence: 660/880/1100 Hz, 0.8 s each, with 0.2 s gaps.
    tone = array.array('h')
    for frequency in (660, 880, 1100):
        for i in range(int(0.8 * RATE)):
            fade = min(1.0, i / (0.02 * RATE), (0.8 * RATE - i) / (0.02 * RATE))
            sample = int(0.20 * 32767 * fade * math.sin(2 * math.pi * frequency * i / RATE))
            tone.extend((sample, sample))
        tone.extend([0] * int(0.2 * RATE) * 2)
    tone_path = out / 'speaker-test-tone.wav'
    with wave.open(str(tone_path), 'wb') as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(RATE)
        f.writeframes(tone.tobytes())
    baseline = out / 'microphone-baseline.wav'
    command(['arecord', '-q', '-D', 'robot_capture', '-t', 'wav', '-f', 'S16_LE', '-r', str(RATE), '-c', '1', '-d', '2', str(baseline)])
    capture = out / 'duplex-capture.wav'
    record_argv = ['arecord', '-q', '-D', 'robot_capture', '-t', 'wav', '-f', 'S16_LE', '-r', str(RATE), '-c', '1', '-d', '5', str(capture)]
    recorder = subprocess.Popen(record_argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    time.sleep(0.6)
    command(['aplay', '-q', '-D', 'robot_playback', str(tone_path)])
    text, _ = recorder.communicate(timeout=10)
    report['commands'].append({'argv': record_argv, 'exit_code': recorder.returncode, 'output': text})
    if recorder.returncode:
        raise RuntimeError(text)
    bm, bv = samples(baseline)
    cm, cv = samples(capture)
    report['baseline'] = dict(metadata=bm, **stats(bv))
    report['duplex'] = dict(metadata=cm, **stats(cv))
    detections = []
    for index, frequency in enumerate((660, 880, 1100)):
        # Use an interior window to tolerate a small PCM start delay.
        start = int((0.8 + index) * RATE)
        window = cv[start:start + int(0.4 * RATE)]
        target = power(window, frequency)
        background = power(bv[:len(window)], frequency)
        competitors = max(power(window, f) for f in (660, 880, 1100) if f != frequency)
        detections.append({'frequency_hz': frequency,
                           'above_baseline_db': 10 * math.log10(target / background),
                           'above_other_test_frequencies_db': 10 * math.log10(target / competitors)})
    report['tone_detections'] = detections
    report['acoustic_sequence_detected'] = all(d['above_baseline_db'] >= 6 and d['above_other_test_frequencies_db'] >= 6 for d in detections)
    report['pcm_capture_playback_duplex_pass'] = True
    # Replay the short baseline at its captured level (no gain/normalization).
    command(['aplay', '-q', '-D', 'robot_playback', str(baseline)])
except Exception as e:
    report['error'] = str(e)
    report['pcm_capture_playback_duplex_pass'] = False
finally:
    (out / 'audio-result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
if not report['pcm_capture_playback_duplex_pass']:
    raise SystemExit(1)
