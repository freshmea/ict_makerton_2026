"""Bounded Unix-socket client; dashboard has no provider credentials."""
import asyncio
import json
import os

SOCKET = os.environ.get('STUDY_OBSERVER_SOCKET', '/run/300seconds-observer/observer.sock')


async def rpc(command):
    reader, writer = await asyncio.wait_for(asyncio.open_unix_connection(SOCKET, limit=131072), 2)
    try:
        writer.write(json.dumps(command).encode() + b'\n')
        await writer.drain()
        line = await asyncio.wait_for(reader.readline(), 3)
        reply = json.loads(line)
        if not reply.get('ok'):
            raise RuntimeError(reply.get('error', 'observer_error'))
        return reply['data']
    finally:
        writer.close()
        await writer.wait_closed()
