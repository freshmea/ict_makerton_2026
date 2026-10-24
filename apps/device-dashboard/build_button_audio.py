"""One-time Typecast synthesis -> six MP3s + decoded playback cache. No device output."""
import argparse
import audioop
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import wave

import numpy as np

from button_audio import RATE, wav
from tts_client import synthesize

BUTTON_LABELS = ('일번', '이번', '삼번', '사번', '오번', '육번')
EXTRA_LABELS = {'live-start': '라이브 대화 시작', 'live-end': '라이브 대화 끝'}


def prepare(data):
    with wave.open(io.BytesIO(data), 'rb') as reader:
        rate = reader.getframerate()
        if reader.getnchannels() != 1 or reader.getsampwidth() != 2:
            raise ValueError('TTS must be mono S16_LE')
        raw = reader.readframes(reader.getnframes())
    if rate != RATE:
        raw = audioop.ratecv(raw, 2, 1, rate, RATE, None)[0]
    samples = np.frombuffer(raw, dtype='<i2').astype(np.float64)
    voiced = np.flatnonzero(np.abs(samples) > 32767 * 10 ** (-45 / 20))
    if not len(voiced):
        raise ValueError('TTS has no audible samples')
    samples = samples[max(0, voiced[0] - 1440):min(len(samples), voiced[-1] + 1441)]
    if not 0 < len(samples) <= RATE * 5:
        raise ValueError('Button speech exceeds 5 seconds')
    samples *= 32767 * 10 ** (-9 / 20) / np.max(np.abs(samples))
    fade = min(384, len(samples) // 2)
    samples[:fade] *= np.linspace(0, 1, fade)
    samples[-fade:] *= np.linspace(1, 0, fade)
    return wav(np.rint(samples).astype('<i2').tobytes())


def build(directory, reuse_from=None):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    # Serialize builders, including different output directories: never spend twice concurrently.
    import fcntl
    with open('/var/lib/300seconds-dashboard/.button-audio-build.lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        manifest_path = directory / 'manifest.json'
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {
            'version': 1, 'provider': 'typecast', 'created_utc': datetime.now(timezone.utc).isoformat(),
            'playback': 'decoded MP3 / mono S16_LE 48000 Hz', 'buttons': {}}
        manifest.setdefault('extras', {})
        previous = json.loads((Path(reuse_from) / 'manifest.json').read_text()) if reuse_from else {}
        entries = [('buttons', str(i), 'button-%d' % i, label) for i, label in enumerate(BUTTON_LABELS, 1)]
        entries += [('extras', stem, stem, text) for stem, text in EXTRA_LABELS.items()]
        for section, key, stem, label in entries:
            reusable = next(((('button-' + old_key) if old_section == 'buttons' else old_key, value)
                             for old_section in ('buttons', 'extras')
                             for old_key, value in previous.get(old_section, {}).items()
                             if value.get('text') == label), None)
            if key not in manifest[section] and reusable is not None:
                old_stem, item = reusable
                for ext in ('mp3', 'wav'):
                    data = (Path(reuse_from) / (old_stem + '.' + ext)).read_bytes()
                    if hashlib.sha256(data).hexdigest() != item[ext + '_sha256']:
                        raise ValueError('Reusable asset checksum mismatch')
                    (directory / (stem + '.' + ext)).write_bytes(data)
                manifest[section][key] = item
            if key in manifest[section]:
                if manifest[section][key]['text'] != label:
                    raise ValueError('Cached pronunciation differs; build into a new output directory')
                for ext in ('mp3', 'wav'):
                    data = (directory / (stem + '.' + ext)).read_bytes()
                    if hashlib.sha256(data).hexdigest() != manifest[section][key][ext + '_sha256']:
                        raise ValueError('Existing asset changed; refusing automatic resynthesis')
                temporary = directory / 'manifest.new'
                temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
                temporary.replace(manifest_path)
                print('cached', stem, flush=True)
                continue
            source, _metadata = synthesize(label)
            with tempfile.TemporaryDirectory(dir=str(directory)) as temp:
                temp = Path(temp)
                (temp / 'speech.wav').write_bytes(prepare(source))
                subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-i', str(temp / 'speech.wav'),
                                '-codec:a', 'libmp3lame', '-b:a', '96k', str(temp / 'speech.mp3')],
                               check=True, timeout=15)
                subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-i', str(temp / 'speech.mp3'),
                                '-ar', str(RATE), '-ac', '1', '-codec:a', 'pcm_s16le', str(temp / 'decoded.wav')],
                               check=True, timeout=15)
                item = {'text': label}
                for ext, source_name in [('mp3', 'speech.mp3'), ('wav', 'decoded.wav')]:
                    data = (temp / source_name).read_bytes()
                    target = directory / (stem + '.' + ext)
                    target.write_bytes(data)
                    item[ext + '_sha256'] = hashlib.sha256(data).hexdigest()
                with wave.open(str(directory / (stem + '.wav')), 'rb') as reader:
                    item['seconds'] = round(reader.getnframes() / RATE, 3)
                manifest[section][key] = item
                temporary = directory / 'manifest.new'
                temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
                temporary.replace(manifest_path)
                print('created', stem, item['seconds'], flush=True)
        return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='/var/lib/300seconds-dashboard/button-audio')
    parser.add_argument('--reuse-from')
    args = parser.parse_args()
    build(args.output, args.reuse_from)
