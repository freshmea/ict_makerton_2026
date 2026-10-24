"""Synthesize only: existing Rust Typecast budget/credit checks, no audio device."""
import asyncio
import base64
import io
import json
import logging
import os
from pathlib import Path
import signal
import socket
import struct
import tempfile
import wave

SOCKET = Path(os.environ.get('DASHBOARD_TTS_SOCKET', '/run/300seconds-tts/tts.sock'))
BINARY = os.environ.get('DASHBOARD_TTS_BINARY', '/opt/300seconds/runtime/nano-runtime')


def validate_text(text):
    if not isinstance(text, str) or not text.strip() or len(text.encode('utf-16-le')) // 2 > 240:
        raise ValueError('TTS 문장을 1~240자 이내로 입력하세요.')
    if any(ord(c) < 32 and c not in '\n\r\t' for c in text):
        raise ValueError('TTS 문장에 사용할 수 없는 문자가 있습니다.')
    return text.strip()


def read_wav(path):
    data = path.read_bytes()
    if not 44 <= len(data) <= 2_700_000:
        raise ValueError('TTS 오디오 크기가 올바르지 않습니다.')
    with wave.open(io.BytesIO(data), 'rb') as reader:
        if (reader.getnchannels() != 1 or reader.getsampwidth() != 2
                or not 8000 <= reader.getframerate() <= 48000
                or not 0 < reader.getnframes() <= reader.getframerate() * 30):
            raise ValueError('TTS 오디오 형식 또는 길이가 올바르지 않습니다.')
        if len(reader.readframes(reader.getnframes())) != reader.getnframes() * 2:
            raise ValueError('TTS 오디오가 완전하지 않습니다.')
    return data


def provider_error(output):
    for code, label in (('dns', 'DNS 조회'), ('connect', '서버 연결'),
                        ('timeout', '응답 시간 초과'), ('tls', 'TLS 인증'),
                        ('connection_lost', '연결 끊김'), ('unknown', '통신')):
        if 'transport ' + code + ';' in output:
            logging.warning('tts_provider_transport_failure category=%s', code)
            return 'Typecast %s 오류입니다. 고정 대기 없이 다시 요청할 수 있습니다.' % label
    if 'character_budget' in output or 'budget_or_cooldown' in output:
        return '설정된 TTS 문자 사용량 한도에 도달했습니다. 사용량을 확인해 주세요.'
    if 'credits exhausted' in output or 'paid plan' in output:
        return 'Typecast 포함 크레딧 또는 요금제 제한으로 합성을 중단했습니다.'
    if 'HTTP 429' in output:
        return 'Typecast 동시 요청 한도입니다. 진행 중인 요청이 끝난 뒤 다시 시도하세요.'
    if 'credential_' in output or 'HTTP 401' in output or 'HTTP 403' in output:
        return 'Typecast 인증 설정을 확인해 주세요.'
    return 'TTS 합성에 실패했습니다. 서비스 연결과 Typecast 상태를 확인해 주세요.'


async def synthesize(text):
    text = validate_text(text)
    # Temporary files are private and removed on success, error, or cancellation.
    with tempfile.TemporaryDirectory(prefix='utterance-', dir=str(SOCKET.parent)) as directory:
        path = Path(directory) / 'speech.wav'
        process = await asyncio.create_subprocess_exec(
            BINARY, 'typecast-sample', str(path), text,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, limit=65536)
        try:
            output, _ = await asyncio.wait_for(process.communicate(), 42)
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
        if process.returncode:
            raise RuntimeError(provider_error(output.decode(errors='replace')))
        metadata = json.loads(output)
        return {'ok': True, 'wav': base64.b64encode(read_wav(path)).decode('ascii'),
                'metadata': metadata}


async def serve():
    import pwd
    allowed = {0, pwd.getpwnam('boarddash').pw_uid}
    lock = asyncio.Lock()

    async def handle(reader, writer):
        try:
            peer = writer.get_extra_info('socket').getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
            if struct.unpack('3i', peer)[1] not in allowed:
                raise ValueError('TTS 접근 권한이 없습니다.')
            raw = await asyncio.wait_for(reader.readline(), 3)
            if len(raw) > 4096:
                raise ValueError('TTS 요청이 너무 큽니다.')
            request = json.loads(raw)
            if not isinstance(request, dict) or set(request) != {'text'}:
                raise ValueError('TTS 요청 형식이 올바르지 않습니다.')
            if lock.locked():
                raise RuntimeError('TTS 합성 중입니다. 완료 후 다시 시도하세요.')
            async with lock:
                reply = await synthesize(request['text'])
        except asyncio.TimeoutError:
            reply = {'ok': False, 'error': 'TTS 합성 시간이 초과됐습니다. 자동 재시도하지 않습니다.'}
        except (ValueError, RuntimeError) as error:
            reply = {'ok': False, 'error': str(error)}
        except Exception:
            reply = {'ok': False, 'error': 'TTS 서비스 오류입니다. 관리자에게 문의하세요.'}
        try:
            writer.write(json.dumps(reply).encode() + b'\n')
            await asyncio.wait_for(writer.drain(), 5)
        finally:
            writer.close()
            await writer.wait_closed()

    SOCKET.parent.mkdir(parents=True, exist_ok=True)
    if SOCKET.exists():
        SOCKET.unlink()
    server = await asyncio.start_unix_server(handle, str(SOCKET), limit=4096)
    SOCKET.chmod(0o660)
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(sig, stop.set)
    async with server:
        await stop.wait()
    if SOCKET.exists():
        SOCKET.unlink()


if __name__ == '__main__':
    asyncio.run(serve())
