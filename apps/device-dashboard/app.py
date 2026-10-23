"""LAN device observatory. One ASGI worker; commands go through the USB owner."""
import asyncio
from contextlib import asynccontextmanager
import hmac
import json
import os
from pathlib import Path
import secrets
import time
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, constr

from hardware import Audio, Cameras, EventLog, Metrics, Pico, PROFILES, ROOT, INSTALLATION


async def threaded(function, *args):
    return await asyncio.get_running_loop().run_in_executor(None, function, *args)


@asynccontextmanager
async def lifespan(app):
    app.state.csrf = secrets.token_urlsafe(32)
    app.state.events = EventLog()
    app.state.pico = Pico(app.state.events)
    app.state.audio = Audio(app.state.events)
    app.state.cameras = Cameras(Path(os.environ.get('DASHBOARD_RUNTIME', '/run/300seconds-dashboard')), app.state.events)
    app.state.metrics = Metrics()
    app.state.profile_lock = asyncio.Lock()
    app.state.reconnect_lock = asyncio.Lock()
    app.state.pico.start()
    app.state.audio.start()
    app.state.cameras.start()
    app.state.events.add('system', '300 Seconds 장치 대시보드 시작')
    yield
    app.state.metrics.running = False
    await threaded(app.state.pico.stop)
    await threaded(app.state.cameras.stop)
    app.state.audio.stop()


app = FastAPI(title='300 Seconds · Device Observatory', version='1.0.0', lifespan=lifespan,
              docs_url=None, redoc_url=None)
app.mount('/static', StaticFiles(directory=str(ROOT / 'static')), name='static')


@app.middleware('http')
async def protect(request, call_next):
    if request.method in ('POST', 'PUT', 'PATCH', 'DELETE'):
        origin = request.headers.get('origin')
        valid_origin = not origin or urlsplit(origin).netloc == request.headers.get('host')
        token = request.headers.get('x-csrf-token', '')
        if not valid_origin or not hmac.compare_digest(token, getattr(app.state, 'csrf', 'not-ready')):
            return Response('Same-origin CSRF token required.', status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data: blob:; "
        "media-src 'self' blob:; connect-src 'self' ws: wss:; frame-ancestors 'none'; base-uri 'none'"
    )
    if request.url.path.startswith('/api'):
        response.headers['Cache-Control'] = 'no-store'
    return response


def snapshot():
    return {'server_time': time.time(), 'pico': app.state.pico.snapshot(),
            'cameras': app.state.cameras.snapshot(), 'audio': app.state.audio.snapshot(),
            'system': app.state.metrics.state, 'events': app.state.events.snapshot()}


@app.get('/')
def index():
    return FileResponse(ROOT / 'static/index.html')


@app.get('/api/session')
def session():
    return {'csrf_token': app.state.csrf, 'profiles': PROFILES,
            'rtsp_port': 8554, 'service': '300seconds-dashboard.service'}


@app.get('/api/status')
def status():
    return snapshot()


@app.get('/api/health')
def health():
    value = snapshot()
    return {'api': 'ok', 'pico': value['pico']['connected'],
            'cameras': value['cameras']['ready'], 'microphone': value['audio']['connected']}


@app.websocket('/ws/status')
async def telemetry(websocket: WebSocket):
    origin = websocket.headers.get('origin')
    if origin and urlsplit(origin).netloc != websocket.headers.get('host'):
        await websocket.close(code=1008)
        return
    await websocket.accept()
    try:
        while True:
            await websocket.send_json(snapshot())
            await asyncio.sleep(.5)
    except (WebSocketDisconnect, RuntimeError):
        pass


def require_sensor(sensor):
    if sensor not in (0, 1):
        raise HTTPException(404, '카메라가 없습니다.')


@app.get('/api/cameras/{sensor}/snapshot.jpg')
def camera_snapshot(sensor: int):
    require_sensor(sensor)
    state = app.state.cameras.snapshot()
    if not state.get('ready'):
        raise HTTPException(503, state.get('error') or '카메라를 준비하고 있습니다.')
    try:
        return Response(app.state.cameras.image_path(sensor).read_bytes(), media_type='image/jpeg')
    except OSError:
        raise HTTPException(503, '프레임이 아직 없습니다.')


@app.get('/api/cameras/{sensor}/stream.mjpg')
async def camera_stream(sensor: int, request: Request):
    require_sensor(sensor)
    async def frames():
        previous = None
        while not await request.is_disconnected():
            state = app.state.cameras.snapshot()
            if state.get('ready'):
                path = app.state.cameras.image_path(sensor)
                try:
                    stamp = path.stat().st_mtime_ns
                    if stamp != previous:
                        data = path.read_bytes()
                        previous = stamp
                        yield (b'--frame\r\nContent-Type: image/jpeg\r\nContent-Length: ' +
                               str(len(data)).encode() + b'\r\n\r\n' + data + b'\r\n')
                except OSError:
                    pass
            await asyncio.sleep(1 / 15)
    return StreamingResponse(frames(), media_type='multipart/x-mixed-replace; boundary=frame')


class ProfileRequest(BaseModel):
    profile: constr(regex=r'^(360p30|720p30|720p60|1080p30)$')


@app.post('/api/cameras/profile')
async def set_camera_profile(value: ProfileRequest):
    if app.state.profile_lock.locked():
        raise HTTPException(409, '카메라 설정을 적용 중입니다.')
    async with app.state.profile_lock:
        try:
            return await threaded(app.state.cameras.set_profile, value.profile)
        except RuntimeError as error:
            raise HTTPException(503, str(error))


class PicoRequest(BaseModel):
    cmd: constr(regex=r'^(status|stop|test)$')
    module: constr(regex=r'^(matrix|left|right|servos|all)$') = None


@app.post('/api/pico/command')
async def pico_command(value: PicoRequest):
    if value.cmd == 'test' and value.module is None:
        raise HTTPException(422, '시험 모듈을 지정하세요.')
    if value.cmd == 'test' and value.module in ('matrix', 'all') and not INSTALLATION['matrix_connected']:
        raise HTTPException(409, '도트매트릭스가 미연결이므로 해당 시험을 실행하지 않습니다.')
    command = {'cmd': value.cmd}
    if value.cmd == 'test':
        command['module'] = value.module
    try:
        result = await threaded(app.state.pico.command, command)
        if not result.get('ok'):
            raise HTTPException(409, result.get('error', '장치가 요청을 거부했습니다.'))
        return result
    except (RuntimeError, OSError, ValueError) as error:
        raise HTTPException(503, str(error))


@app.post('/api/pico/reconnect')
async def reconnect_pico():
    if app.state.reconnect_lock.locked():
        raise HTTPException(409, 'USB 연결 요청을 처리 중입니다.')
    async with app.state.reconnect_lock:
        await threaded(app.state.pico.start)
        return app.state.pico.snapshot()


@app.get('/api/audio/recent.wav')
def recent_audio():
    try:
        return Response(app.state.audio.recording(3), media_type='audio/wav',
                        headers={'Content-Disposition': 'inline; filename="microphone-last-3s.wav"'})
    except RuntimeError as error:
        raise HTTPException(503, str(error))


class AudioRequest(BaseModel):
    action: constr(regex=r'^(tone|replay)$')


@app.post('/api/audio/play')
async def play_audio(value: AudioRequest):
    try:
        return await threaded(app.state.audio.playback, value.action)
    except (RuntimeError, ValueError) as error:
        raise HTTPException(409, str(error))
