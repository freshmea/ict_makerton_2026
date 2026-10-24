"""Bounded local synthesis RPC; provider keys belong only to the TTS worker."""
import base64
import json
import os
import socket

MAX_REPLY = 3_700_000


def synthesize(text):
    path = os.environ.get('DASHBOARD_TTS_SOCKET', '/run/300seconds-tts/tts.sock')
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(50)
        connection.connect(path)
        connection.sendall(json.dumps({'text': text}).encode() + b'\n')
        with connection.makefile('rb') as stream:
            raw = stream.readline(MAX_REPLY + 1)
    if len(raw) > MAX_REPLY or not raw.endswith(b'\n'):
        raise RuntimeError('TTS 응답 크기가 올바르지 않습니다.')
    reply = json.loads(raw)
    if not reply.get('ok'):
        raise RuntimeError(reply.get('error', 'TTS 합성에 실패했습니다.'))
    return base64.b64decode(reply['wav'], validate=True), reply['metadata']
