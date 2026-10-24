"""Local, twenty-second expression selection from device activity and saved evidence."""
import asyncio
from collections import deque
import json
import random
import time

from eye_expressions import BY_ID

INTERVAL = 20.0
# Friendly robot gestures when evidence is unclear; never random distress/anger.
IDLE_EYES = ('neutral','look-left','look-right','look-up','wink-left','wink-right',
             'googly','cross-eyed','gentle-smile')
CURIOSITY_EYES = ('curious','look-left','look-right','look-up','googly','cross-eyed')
BUTTONS = {1:'gentle-smile', 2:'curious', 3:'confident', 4:'sparkling', 5:'music', 6:'happy'}
ACTION_EYES = [('writing','confident'), ('reading','look-down'), ('typing','determined'),
               ('phone_use','curious'), ('eating_drinking','relaxed'),
               ('handling_objects','curious'), ('looking_away','look-left')]
KEYWORD_EYES = [
    (('음악','노래','music'),'music'), (('완료','정답','성공','축하'),'well-done'),
    (('수학','문제','계산','질문','탐구'),'curious'), (('독서','책','읽기'),'look-down'),
    (('필기','공책','연필','쓰기'),'confident'), (('휴식','음료','물 마시'),'relaxed'),
    (('코딩','컴퓨터','키보드'),'determined'), (('그림','미술','색칠'),'sparkling'),
    (('인사','친구'),'gentle-smile')]


def choose(observations, live=None, speaker=None, button=None, now=None, activity=None):
    """Robot feedback, never a claim about a learner's emotion or mental state."""
    now = time.time() if now is None else now
    live, speaker = live or {}, speaker or {}
    if live.get('phase') in ('preparing','connecting'):
        return 'curious', 'Live 연결 준비', []
    if live.get('phase') in ('active','closing'):
        return 'gentle-smile', 'Live 대화', []
    if button in BUTTONS:
        return BUTTONS[button], '버튼 %d 입력' % button, []
    if activity:
        return activity[0], activity[1], []
    if speaker.get('state') not in (None,'idle','failed','error'):
        return 'music', '기기 음성·소리 재생', []
    rows = [r for r in observations if 0 <= now-r['captured'] <= 120
            and isinstance(r.get('confidence'), (int,float)) and r['confidence'] >= .5]
    ids = [r['id'] for r in rows]
    actions = {a for r in rows for a in r.get('actions', [])}
    for action, preset in ACTION_EYES:
        if action in actions:return preset, '관찰 행동 · '+action, ids
    words = ' '.join(str(k)[:60] for r in rows for k in r.get('keywords', [])[:8]).casefold()
    for keywords, preset in KEYWORD_EYES:
        for keyword in keywords:
            if keyword in words:return preset, '관찰 키워드 · '+keyword, ids
    if 'person_present' in actions:return 'gentle-smile', '사람이 보이는 학습 공간', ids
    return 'neutral', '기본 눈', ids


def vary(preset, reason, recent, rng):
    """Vary idle/broad curiosity feedback, preserving explicit activity choices."""
    if reason == '기본 눈':
        pool, reason = IDLE_EYES, '상황 판단 보류 · 자연스러운 대기'
    elif reason == '사람이 보이는 학습 공간':
        pool, reason = IDLE_EYES, '사람이 보이는 학습 공간 · 자연스러운 대기'
    elif preset == 'curious' and reason.startswith('관찰 '):
        pool = CURIOSITY_EYES
    else:
        return preset, reason
    return rng.choice([item for item in pool if item not in recent]), reason


class AutomaticEyes:
    def __init__(self, eyes, pico, servos, learning, audio, events, installed=True):
        self.eyes, self.pico, self.servos = eyes, pico, servos
        self.learning, self.audio, self.events = learning, audio, events
        self.installed = installed
        self.enabled = installed and bool(learning.store.setting('automatic_eyes_enabled', True))
        self.running, self.reconnecting = False, False
        self.task, self.remove = None, lambda:None
        self.next_selection = self.retry_until = 0
        self.selected, self.reason = 'neutral', '기본 눈'
        self.recent_presets = deque(maxlen=3)
        self.random = random.Random()
        self.observation_ids, self.selections = [], 0
        self.selected_at = None
        self.waiting, self.error = None, None
        self.button = None
        self.consumed_button = None
        self.generation = 0
        self.session = None
        self.activity = self.consumed_activity = None
        self.eyes.default_on = self.enabled
        self.eyes.auto_allowed = self.allowed
        self.eyes.automatic_status = self.snapshot

    def snapshot(self):
        return {'enabled':self.enabled, 'interval_seconds':INTERVAL,
                'preset_id':self.selected, 'name':BY_ID[self.selected]['name'],
                'reason':self.reason, 'observation_ids':list(self.observation_ids),
                'selections':self.selections, 'selected_at':self.selected_at,
                'next_selection_ms':max(0,round((self.next_selection-time.monotonic())*1000)) if self.enabled else 0,
                'waiting':self.waiting, 'error':self.error, 'extra_ai_requests':0}

    def set_enabled(self, enabled):
        if enabled and not self.installed:
            raise ValueError('눈 매트릭스 연결 설정을 확인해 주세요.')
        self.learning.store.set_setting('automatic_eyes_enabled', enabled)
        self.enabled = self.eyes.default_on = enabled
        self.generation += 1
        self.next_selection = self.retry_until = 0
        self.waiting = None if enabled else '사용자 정지'
        return self.snapshot()

    def allowed(self):
        if not self.enabled or not self.running or self.reconnecting or self.eyes.stopping:
            return False
        state = self.pico.snapshot()
        if not state.get('connected') or state.get('installation',{}).get('matrix_connected') is False:
            return False
        if self.servos.active or self.servos.gate.locked():return False
        if (state.get('device') or {}).get('running') not in (None,'None','Idle'):return False
        if time.monotonic() < self.eyes.external_until:return False
        active = self.eyes.active
        return not (active and active.get('mode') == 'manual' and active['until'] > time.monotonic())

    def on_touch(self, packet):
        state = self.pico.snapshot()
        touch = packet.get('touch') or {}
        if (not state.get('connected') or packet.get('session') != state.get('session')
                or abs(time.time()*1000-packet.get('host_unix_ms',0)) > 2000
                or touch.get('kind') not in ('Pressed','Interval')
                or type(touch.get('index')) is not int or touch['index'] not in BUTTONS
                or type(touch.get('event_seq')) is not int):return
        key = (state.get('session'),touch['event_seq'])
        if self.button and self.button[0] == key:return
        if self.button and self.button[0][0] == key[0] and not 0 < ((key[1]-self.button[0][1]) & 0xffffffff) < 0x80000000:return
        self.button = (key,touch['index'],time.monotonic())

    def start(self):
        self.running = True
        self.remove = self.pico.subscribe_touch(self.on_touch)
        self.task = asyncio.create_task(self.run())

    def remember_activity(self):
        # Catch a short sound/action between selection ticks; ignore our own eye events.
        if not hasattr(self.events,'snapshot'):return
        for event in self.events.snapshot()[:40]:
            if event.get('level') != 'info' or not 0 <= time.time()-event.get('time',0) <= 40:continue
            source = event.get('source')
            choice = ('music','기기 음성·소리 재생') if source in ('audio','tts') else (
                ('gentle-smile','기기 대화 활동') if source == 'learning' else None)
            if source == 'pico':
                try:message = json.loads(event.get('message',''))
                except (ValueError,TypeError):message = {}
                if not isinstance(message,dict):message = {}
                if message.get('event') == 'test_event' and message.get('done') is True and not message.get('fault'):
                    choice = ('well-done','장치 시험 완료')
            if choice:
                self.activity = (choice,event['id'],event['time'])
                return

    async def tick(self):
        now = time.monotonic()
        self.remember_activity()
        if not self.allowed():
            self.waiting = '수동 표정·장치 시험·연결 상태 확인 중' if self.enabled else '사용자 정지'
            return
        if self.eyes.gate.locked() or now < self.retry_until:return
        self.waiting = None
        session = self.pico.snapshot().get('session')
        if session != self.session:
            self.session, self.next_selection = session, 0
        due = now >= self.next_selection
        if due:
            generation = self.generation
            try:
                rows = await asyncio.get_running_loop().run_in_executor(None,self.learning.store.eye_observations)
            except Exception:
                rows = []
                self.error = '관찰 조회 지연 · 기본 표정으로 표시합니다.'
            button = self.button
            fresh_button = bool(button and button[0] != self.consumed_button and
                button[0][0] == self.pico.snapshot().get('session') and 0 <= now-button[2] <= 40)
            activity = self.activity
            fresh_activity = bool(activity and activity[1] != self.consumed_activity and 0 <= time.time()-activity[2] <= 40)
            selected, reason, ids = choose(rows,self.learning.live.snapshot(),self.audio.snapshot().get('speaker'),
                                           button[1] if fresh_button else None,
                                           activity=activity[0] if fresh_activity else None)
            if generation != self.generation or not self.allowed():return
            selected, reason = vary(selected,reason,self.recent_presets,self.random)
            self.selected, self.reason, self.observation_ids = selected, reason, ids
            self.recent_presets.append(selected)
            self.eyes.default_preset = selected
            if fresh_button and reason.startswith('버튼 '):self.consumed_button = button[0]
            if fresh_activity and reason == activity[0][1]:self.consumed_activity = activity[1]
        active = self.eyes.active
        if due or active is None or active.get('session') != self.pico.snapshot().get('session'):
            await self.eyes.hold(self.selected)
            self.error = None
        if due:
            self.selected_at, self.next_selection = time.time(), time.monotonic()+INTERVAL
            self.selections += 1
            self.events.add('eyes', '자동 표정 · {} · {}'.format(BY_ID[self.selected]['name'],self.reason))

    async def run(self):
        while self.running:
            try:
                await self.tick()
            except Exception:
                self.error = '눈 표시를 확인하는 중입니다. 연결 복구 후 다시 표시합니다.'
                self.retry_until = time.monotonic()+3
            await asyncio.sleep(.5)

    async def close(self):
        self.running = self.eyes.default_on = False
        self.generation += 1
        self.remove()
        if self.task:
            try:await asyncio.wait_for(asyncio.shield(self.task),8)
            except asyncio.TimeoutError:
                self.task.cancel()
                await asyncio.gather(self.task,return_exceptions=True)
