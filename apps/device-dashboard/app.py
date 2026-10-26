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
from typing import Literal

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, confloat, conint, constr, validator

from hardware import Audio, Cameras, EventLog, Metrics, Pico, PROFILES, ROOT, INSTALLATION
from eye_expressions import BY_ID, CATALOG, EyePlayer
from automatic_eyes import AutomaticEyes
from observer_client import rpc as observer_rpc
from servo_controls import ServoControls
from learning import Learning
from study_reaction import StudyReaction
from button_audio import ButtonAudio
from learning_routes import router as learning_router
from log_analytics import Analytics
from analytics_routes import router as analytics_router


async def threaded(function, *args):
    return await asyncio.get_running_loop().run_in_executor(None, function, *args)


@asynccontextmanager
async def lifespan(app):
    app.state.csrf = secrets.token_urlsafe(32)
    app.state.events = EventLog()
    app.state.pico = Pico(app.state.events)
    app.state.eyes = EyePlayer(app.state.pico, app.state.events)
    app.state.servos = ServoControls(app.state.pico, app.state.eyes, app.state.events)
    app.state.audio = Audio(app.state.events)
    app.state.cameras = Cameras(Path(os.environ.get('DASHBOARD_RUNTIME', '/run/300seconds-dashboard')), app.state.events)
    app.state.metrics = Metrics()
    app.state.profile_lock = asyncio.Lock()
    app.state.reconnect_lock = asyncio.Lock()
    app.state.pico.start()
    app.state.audio.start()
    app.state.button_audio = ButtonAudio(app.state.pico, app.state.audio, app.state.events)
    app.state.button_audio.start()
    app.state.cameras.start()
    app.state.learning = Learning(app.state.cameras, app.state.audio, app.state.pico, app.state.events,
                                  button_audio=app.state.button_audio)
    app.state.learning.start()
    app.state.study_reaction = StudyReaction(app.state.pico,app.state.audio,app.state.eyes,
        app.state.servos,app.state.learning.live,app.state.button_audio,app.state.events)
    app.state.learning.live.start_guard = app.state.study_reaction.guard_live
    app.state.study_reaction.start_switch()
    app.state.analytics = Analytics(app.state.learning.store)
    app.state.analytics.start()
    app.state.automatic_eyes = AutomaticEyes(app.state.eyes, app.state.pico, app.state.servos,
        app.state.learning, app.state.audio, app.state.events, installed=INSTALLATION['matrix_connected'])
    app.state.automatic_eyes.start()
    app.state.events.add('system', '300 Seconds 장치 대시보드 시작')
    yield
    await app.state.study_reaction.close()
    await app.state.analytics.close()
    await app.state.automatic_eyes.close()
    await app.state.learning.close()
    await threaded(app.state.button_audio.close)
    app.state.metrics.running = False
    await app.state.servos.close()
    await app.state.eyes.close()
    await threaded(app.state.pico.stop)
    await threaded(app.state.cameras.stop)
    app.state.audio.stop()


app = FastAPI(title='300 Seconds · Device Observatory', version='1.0.0', lifespan=lifespan,
              docs_url=None, redoc_url=None)
app.mount('/static', StaticFiles(directory=str(ROOT / 'static')), name='static')
app.include_router(learning_router)
app.include_router(analytics_router)


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
    elif request.url.path in ('/', '/static/app.js', '/static/styles.css'):
        response.headers['Cache-Control'] = 'no-cache'
    return response


def snapshot():
    return {'server_time': time.time(), 'pico': app.state.pico.snapshot(),
            'cameras': app.state.cameras.snapshot(), 'audio': app.state.audio.snapshot(),
            'system': app.state.metrics.state, 'events': app.state.events.snapshot(),
            'eye_expression': app.state.eyes.snapshot(),
            'servo_control': app.state.servos.snapshot(),
            'button_audio': app.state.button_audio.snapshot()}


@app.get('/')
def index():
    return FileResponse(ROOT / 'static/index.html')


@app.get('/analytics')
def analytics_page():
    return FileResponse(ROOT / 'static/analytics.html')


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
    if not Cameras.can_preview(state, sensor):
        camera = next((c for c in state.get('cameras', []) if c.get('sensor_id') == sensor), {})
        raise HTTPException(503, camera.get('error') or state.get('error') or '카메라를 준비하고 있습니다.')
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
            if Cameras.can_preview(state, sensor):
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


class StudyRequest(BaseModel):
    provider: Literal['openai', 'jev', 'decisions']
    # GPT: selected camera. JEV: face camera; the other sensor is the study area.
    camera: Literal[0, 1] = 1

    class Config:
        extra = 'forbid'


@app.get('/api/study')
async def study_status():
    try:
        value = await observer_rpc({'op': 'status'})
        controller = getattr(app.state,'study_reaction',None)
        if controller:value['reaction']=controller.snapshot()
        return value
    except (OSError, RuntimeError, ValueError, asyncio.TimeoutError):
        return {'online': False, 'error': '분석 서비스를 준비하고 있습니다.', 'job': {'phase': 'offline'}, 'providers': {}}


@app.post('/api/study/analyze')
async def study_analyze(value: StudyRequest):
    if not app.state.cameras.snapshot().get('ready'):
        raise HTTPException(409, '카메라가 준비되지 않았습니다.')
    try:
        controller = getattr(app.state,'study_reaction',None)
        if value.provider == 'decisions':
            if not controller:raise RuntimeError('기기 반응 서비스를 준비하고 있습니다.')
            return await controller.start(value.camera)
        if controller and controller.busy:raise RuntimeError('Decisions 분석·반응이 진행 중입니다.')
        return await observer_rpc({'op': 'start', 'provider': value.provider, 'camera': value.camera})
    except RuntimeError as exc:
        message = (str(exc) if value.provider == 'decisions' else
                   '다른 분석이 진행 중입니다.' if 'busy' in str(exc) else 'API 키·사용 한도·테스트 예산을 확인해 주세요.')
        raise HTTPException(409, message)
    except (OSError, ValueError, asyncio.TimeoutError):
        raise HTTPException(503, '분석 서비스에 연결하지 못했습니다.')


@app.post('/api/study/cancel')
async def study_cancel():
    controller = getattr(app.state,'study_reaction',None)
    if controller and controller.busy:
        await controller.abort()
        return await study_status()
    try:
        return await observer_rpc({'op': 'cancel'})
    except RuntimeError:
        raise HTTPException(409, '사진 수집 단계에서만 취소할 수 있습니다.')
    except (OSError, ValueError, asyncio.TimeoutError):
        raise HTTPException(503, '분석 서비스에 연결하지 못했습니다.')


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


class EyeRequest(BaseModel):
    preset_id: constr(regex=r'^[a-z][a-z-]{0,31}$')
    seconds: Literal[3, 5, 10] = 5

    class Config:
        extra = 'forbid'


@app.get('/api/pico/expressions')
def eye_presets():
    return {'count': len(CATALOG), 'presets': CATALOG}


class AutomaticEyeRequest(BaseModel):
    enabled: bool

    class Config:
        extra = 'forbid'


@app.post('/api/pico/expressions/automatic')
async def automatic_eyes(value: AutomaticEyeRequest):
    try:
        owner = app.state.automatic_eyes
        owner.set_enabled(value.enabled)
        if not value.enabled and app.state.eyes.active and app.state.eyes.active.get('mode') == 'automatic':
            await app.state.eyes.stop()
        return owner.snapshot()
    except (RuntimeError, OSError, ValueError) as error:
        raise HTTPException(409, str(error))


@app.post('/api/pico/expression')
async def show_expression(value: EyeRequest):
    if not INSTALLATION['matrix_connected']:
        raise HTTPException(409, '도트매트릭스가 미연결입니다.')
    if value.preset_id not in BY_ID:
        raise HTTPException(404, '등록되지 않은 표정입니다.')
    try:
        study = getattr(app.state,'study_reaction',None)
        if study and study.busy:await study.abort()
        servos = getattr(app.state, 'servos', None)
        if servos and servos.active: await servos.stop()
        return await app.state.eyes.start(value.preset_id, value.seconds)
    except (RuntimeError, OSError, ValueError) as error:
        raise HTTPException(409, str(error))


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
        automatic = getattr(app.state, 'automatic_eyes', None)
        if value.cmd == 'stop' and automatic:
            automatic.set_enabled(False)
        study = getattr(app.state,'study_reaction',None)
        if study and study.busy and value.cmd in ('stop','test'):await study.abort()
        servos = getattr(app.state, 'servos', None)
        if servos and value.cmd == 'stop':
            result = await servos.stop()
        else:
            if servos and value.cmd == 'test' and servos.active: await servos.stop()
            result = await app.state.eyes.command(command)
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
        automatic = getattr(app.state, 'automatic_eyes', None)
        if automatic: automatic.reconnecting = True
        try:
            servos = getattr(app.state, 'servos', None)
            if servos: await servos.close()
            await app.state.eyes.close()
            await threaded(app.state.pico.stop)
            await threaded(app.state.pico.start)
            return app.state.pico.snapshot()
        finally:
            if automatic:
                automatic.next_selection = 0
                automatic.reconnecting = False


class ServoSessionRequest(BaseModel):
    action: Literal['enable', 'keepalive', 'stop', 'probe']
    control_id: constr(min_length=16, max_length=96) = None

    class Config:
        extra = 'forbid'


class ServoMoveRequest(BaseModel):
    control_id: constr(min_length=16, max_length=96)
    servo: conint(strict=True, ge=1, le=6)
    degrees: conint(strict=True, ge=0, le=180)

    class Config:
        extra = 'forbid'


@app.get('/api/pico/servos')
def servo_status():
    return app.state.servos.snapshot()


@app.post('/api/pico/servos/session')
async def servo_session(value: ServoSessionRequest):
    try:
        study = getattr(app.state,'study_reaction',None)
        if study and study.busy:await study.abort()
        owner = app.state.servos
        if value.action == 'enable': return await owner.enable()
        if value.action == 'keepalive': return owner.keepalive(value.control_id)
        if value.action == 'probe': return await owner.probe()
        return await owner.stop(value.control_id)
    except (RuntimeError, ValueError, OSError) as error:
        raise HTTPException(409, str(error))


@app.post('/api/pico/servo')
async def move_servo(value: ServoMoveRequest):
    try:
        return await app.state.servos.move(value.control_id, value.servo, value.degrees)
    except (RuntimeError, ValueError, OSError) as error:
        raise HTTPException(409, str(error))


@app.get('/api/audio/recent.wav')
def recent_audio():
    try:
        return Response(app.state.audio.recording(3), media_type='audio/wav',
                        headers={'Content-Disposition': 'inline; filename="microphone-last-3s.wav"'})
    except RuntimeError as error:
        raise HTTPException(503, str(error))


class AudioRequest(BaseModel):
    action: constr(regex=r'^(tone|replay)$')


class AudioSettingsRequest(BaseModel):
    gain_db: confloat(ge=0, le=30, allow_inf_nan=False)

    class Config:
        extra = 'forbid'


class TTSRequest(BaseModel):
    text: constr(strip_whitespace=True, min_length=1, max_length=240)

    @validator('text')
    def validate_text(cls, value):
        from tts_worker import validate_text
        return validate_text(value)

    class Config:
        extra = 'forbid'


@app.post('/api/audio/tts')
async def play_tts(value: TTSRequest):
    try:
        return await threaded(app.state.audio.tts, value.text)
    except RuntimeError as error:
        raise HTTPException(409, str(error))


@app.post('/api/audio/settings')
async def audio_settings(value: AudioSettingsRequest):
    try:
        return await threaded(app.state.audio.set_gain, value.gain_db)
    except OSError as error:
        raise HTTPException(503, '마이크 증폭 설정을 저장하지 못했습니다: ' + str(error))


@app.post('/api/audio/play')
async def play_audio(value: AudioRequest):
    try:
        return await threaded(app.state.audio.playback, value.action)
    except (RuntimeError, ValueError) as error:
        raise HTTPException(409, str(error))
