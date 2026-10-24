"""Large, bounded observation RPC and streaming Live transport; no credentials."""
import asyncio
import json
from observer_client import SOCKET


async def open_stream(command):
    reader, writer = await asyncio.wait_for(asyncio.open_unix_connection(SOCKET, limit=1048577), 2)
    try:
        writer.write(json.dumps(command).encode() + b'\n')
        await asyncio.wait_for(writer.drain(), 3)
        return reader, writer
    except BaseException:
        writer.close()
        raise


async def rpc(command, timeout=42):
    reader, writer = await open_stream(command)
    try:
        reply = json.loads(await asyncio.wait_for(reader.readline(), timeout))
        if not reply.get('ok'):
            raise RuntimeError(reply.get('error', 'learning_provider_error'))
        return reply['data']
    finally:
        writer.close()
        await writer.wait_closed()
