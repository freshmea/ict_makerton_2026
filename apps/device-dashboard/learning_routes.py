"""LAN dashboard routes; the application's existing CSRF middleware guards writes."""
import csv
import io
import json
import math
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, constr

from learning_client import rpc

router = APIRouter(prefix='/api/learning')


class CollectionRequest(BaseModel):
    enabled: bool

    class Config:
        extra = 'forbid'


class LiveRequest(BaseModel):
    mode: Literal['study', 'chat'] = 'study'

    class Config:
        extra = 'forbid'


class AnnotationRequest(BaseModel):
    label: constr(strip_whitespace=True, min_length=1, max_length=80)
    note: constr(max_length=1000) = ''

    class Config:
        extra = 'forbid'


def filters(since, until, camera, keyword):
    if not math.isfinite(since) or since < 0 or until is not None and (not math.isfinite(until) or until < since):
        raise HTTPException(422, '조회 기간을 확인해 주세요.')
    return dict(since=since, until=until, camera=camera, keyword=keyword)


@router.get('')
async def status(request: Request):
    value = request.app.state.learning.snapshot()
    try:
        value['provider'] = await rpc({'op': 'learning_status'}, timeout=3)
    except Exception:
        value['provider'] = {'configured': False, 'error': '분석 서비스 연결 필요'}
    return value


@router.post('/collection')
async def collection(value: CollectionRequest, request: Request):
    if value.enabled:
        try:
            provider = await rpc({'op': 'learning_status'}, timeout=3)
            if not provider['configured']:
                raise RuntimeError()
        except Exception:
            raise HTTPException(503, '분석 서비스와 OpenAI API 키 설정을 확인해 주세요.')
    return request.app.state.learning.set_enabled(value.enabled)


@router.get('/records')
def records(request: Request, since: float = 0, until: Optional[float] = None,
            camera: Optional[int] = Query(None, ge=0, le=1), keyword: str = Query('', max_length=80),
            before: Optional[int] = Query(None, ge=1), limit: int = Query(50, ge=1, le=100)):
    return request.app.state.learning.store.records(limit=limit, before=before, **filters(since, until, camera, keyword))


@router.get('/summary')
def summary(request: Request, since: float = 0, until: Optional[float] = None,
            camera: Optional[int] = Query(None, ge=0, le=1), keyword: str = Query('', max_length=80)):
    return request.app.state.learning.store.summary(**filters(since, until, camera, keyword))


@router.post('/records/{identifier}/annotation')
def annotate(identifier: int, value: AnnotationRequest, request: Request):
    try:
        request.app.state.learning.store.annotate(identifier, value.label, value.note)
    except ValueError:
        raise HTTPException(404, '관찰 기록이 없습니다.')
    return {'ok': True, 'observation_id': identifier}


EXPORT_FIELDS = ['id', 'batch_id', 'camera', 'captured_at_utc', 'status', 'description',
                 'keywords', 'actions', 'confidence', 'uncertainty', 'error', 'model',
                 'prompt_version', 'sha256', 'generation', 'live_id', 'manual_label', 'manual_note']


def csv_row(row):
    output = []
    for key in EXPORT_FIELDS:
        value = row.get(key)
        if isinstance(value, list):
            value = json.dumps(value, ensure_ascii=False)
        if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')):
            value = "'" + value
        output.append(value)
    stream = io.StringIO(newline='')
    csv.writer(stream).writerow(output)
    return stream.getvalue()


@router.get('/export')
def export(request: Request, format: Literal['csv', 'jsonl'] = 'csv', since: float = 0,
           until: Optional[float] = None, camera: Optional[int] = Query(None, ge=0, le=1),
           keyword: str = Query('', max_length=80)):
    query = filters(since, until, camera, keyword)
    # Freeze the upper time bound so a long export cannot absorb new captures.
    import time
    if query['until'] is None:
        query['until'] = time.time()
    store = request.app.state.learning.store
    def chunks():
        if format == 'csv':
            yield '\ufeff' + csv_row({key: key for key in EXPORT_FIELDS})
        before = None
        while True:
            page = store.records(limit=100, before=before, **query)
            for row in page['records']:
                yield csv_row(row) if format == 'csv' else json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n'
            before = page['next_before']
            if before is None:
                break
    return StreamingResponse(chunks(), media_type='text/csv' if format == 'csv' else 'application/x-ndjson',
                             headers={'Content-Disposition': 'attachment; filename="observations.' + format + '"'})


@router.post('/live/start')
async def live_start(value: LiveRequest, request: Request):
    try:
        return await request.app.state.learning.live.start(value.mode)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))


@router.get('/live/policy')
async def live_policy():
    try:
        return await rpc({'op': 'learning_policy'}, timeout=3)
    except Exception:
        raise HTTPException(503, '교육 프롬프트 서비스에 연결하지 못했습니다.')


@router.get('/live/context')
def live_context(request: Request, session_id: Optional[str] = Query(None, max_length=64)):
    store = request.app.state.learning.store
    if session_id:
        value = store.live_context(session_id)
        if value is None:
            raise HTTPException(404, '이 세션에는 저장된 참조 스냅샷이 없습니다.')
        return value
    reference = store.live_reference()
    return {'reference': reference, 'metadata': store.reference_metadata(reference)}


@router.post('/live/stop')
def live_stop(request: Request):
    return request.app.state.learning.live.stop()


@router.get('/live/history')
def live_history(request: Request, session_id: Optional[str] = Query(None, max_length=64),
                 before: Optional[int] = Query(None, ge=1)):
    return request.app.state.learning.store.live_history(session_id, before)


@router.get('/live/export')
def live_export(request: Request, session_id: str = Query(..., min_length=1, max_length=64)):
    store = request.app.state.learning.store
    def chunks():
        before = None
        yield json.dumps({'type': 'session', 'session': store.live_history(session_id)['selected_session']}, ensure_ascii=False) + '\n'
        while True:
            page = store.live_history(session_id, before)
            for event in reversed(page['events']):
                yield json.dumps(event, ensure_ascii=False) + '\n'
            before = page['next_before']
            if before is None:
                break
    return StreamingResponse(chunks(), media_type='application/x-ndjson',
        headers={'Content-Disposition': 'attachment; filename="live-transcript.jsonl"'})
