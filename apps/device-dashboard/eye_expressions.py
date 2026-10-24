"""Upright 8x8 eye artwork and playback through the existing USB owner."""
import asyncio
import time


SHAPES = {
    'happy': [0,0,24,36,66,129,0,0],
    'smile': [0,24,36,66,66,0,0,0],
    'joy': [0,0,24,60,102,66,0,0],
    'closed': [0,0,0,126,0,0,0,0],
    'squeeze': [0,64,32,16,8,16,32,64],
    'heart': [102,255,255,255,126,60,24,0],
    'little-heart': [0,36,126,126,60,24,0,0],
    'star': [24,24,255,126,60,102,195,0],
    'sparkle': [16,16,56,254,56,16,16,0],
    'confident': [0,126,66,90,66,60,0,0],
    'angry': [128,192,96,62,66,90,66,60],
    'sad': [3,6,12,120,132,156,132,120],
    'tear': [60,66,153,153,66,60,64,224],
    'cry': [0,126,66,126,36,36,36,36],
    'sob': [126,66,90,126,18,36,18,36],
    'sleep': [0,0,0,126,66,60,0,0],
    'drowsy': [0,0,126,66,90,66,60,0],
    'bored': [0,0,126,90,66,60,0,0],
    'exhausted': [129,66,36,24,24,36,66,129],
    'spiral': [60,66,157,165,185,129,66,60],
    'spiral-turn': [60,66,189,165,165,153,66,60],
    'question': [60,66,2,12,16,0,16,0],
    'exclaim': [24,60,60,24,24,0,24,0],
    'tiny': [0,0,0,24,24,0,0,0],
    'surprise': [60,126,255,231,231,255,126,60],
    'grumpy': [0,126,0,126,66,90,66,60],
    'check': [0,1,2,132,72,48,0,0],
    'music': [6,10,18,34,34,230,230,68],
    'fire': [8,24,90,126,255,219,126,60],
    'bolt': [12,24,48,126,12,24,48,32],
    'flower': [24,90,126,189,189,126,90,24],
    'sun': [153,90,60,255,255,60,90,153],
    'diamond': [24,36,66,129,129,66,36,24],
}


def mirror(rows):
    return [int('{:08b}'.format(row)[::-1], 2) for row in rows]


def gaze(x=3, y=3):
    rows = [60,66,129,129,129,129,66,60]
    for yy in (y, y + 1):
        rows[yy] |= (128 >> x) | (128 >> (x + 1))
    return rows


def shape(name):
    return list(SHAPES[name])


def frame(left, right, ms=1000):
    return {'left': list(left), 'right': list(right), 'ms': ms}


def preset(key, name, group, description, left, right=None, motion='blink', alternate=None):
    right = list(left) if right is None else right
    frames = [frame(left, right, 1800)]
    if motion == 'blink':
        frames += [frame(shape('closed'), shape('closed'), 140), frame(left, right, 900)]
    elif alternate is not None:
        frames[0]['ms'] = 600
        frames.append(frame(alternate[0], alternate[1], 400))
    return {'id': key, 'name': name, 'group': group, 'description': description, 'frames': frames}


CATALOG = [
    preset('neutral','기본 눈','기본·시선','편안하게 정면을 바라봐요.',gaze()),
    preset('look-left','왼쪽 보기','기본·시선','기기 기준 왼쪽으로 시선을 옮겨요.',gaze(5,3)),
    preset('look-right','오른쪽 보기','기본·시선','기기 기준 오른쪽으로 시선을 옮겨요.',gaze(1,3)),
    preset('look-up','위 보기','기본·시선','무언가 떠올리듯 위를 바라봐요.',gaze(3,1)),
    preset('look-down','아래 보기','기본·시선','아래쪽을 차분히 살펴봐요.',gaze(3,5)),
    preset('happy','활짝 웃음','기쁨','기분 좋은 반달 눈으로 웃어요.',shape('happy')),
    preset('gentle-smile','방긋 미소','기쁨','부드럽고 작은 미소를 지어요.',shape('smile')),
    preset('laugh','깔깔 웃음','기쁨','눈을 꼭 감고 신나게 웃어요.',mirror(shape('squeeze')),shape('squeeze'),motion='change',alternate=(shape('joy'),shape('joy'))),
    preset('delighted','즐거움','기쁨','통통 튀는 웃는 눈을 보여줘요.',shape('joy')),
    preset('excited','신남','기쁨','양쪽 별 눈이 반짝반짝 빛나요.',shape('star'),motion='change',alternate=(shape('sparkle'),shape('sparkle'))),
    preset('love','사랑 가득','애정','커다란 하트가 두근두근 뛰어요.',shape('heart'),motion='change',alternate=(shape('little-heart'),shape('little-heart'))),
    preset('fondness','작은 설렘','애정','작은 하트로 마음을 전해요.',shape('little-heart'),motion='change',alternate=(shape('heart'),shape('heart'))),
    preset('wink-left','왼쪽 눈 윙크','애정','기기의 왼쪽 눈을 살짝 감아 인사해요.',shape('closed'),gaze(),motion='change',alternate=(gaze(),gaze())),
    preset('wink-right','오른쪽 눈 윙크','애정','기기의 오른쪽 눈을 살짝 감아 인사해요.',gaze(),shape('closed'),motion='change',alternate=(gaze(),gaze())),
    preset('shy','수줍음','애정','하트와 미소로 수줍게 표현해요.',shape('little-heart'),shape('smile')),
    preset('confident','자신감','자신감','눈을 또렷하게 뜨고 자신 있게 바라봐요.',shape('confident'),mirror(shape('confident'))),
    preset('proud','뿌듯함','자신감','웃는 눈과 별 눈으로 성취를 표현해요.',shape('happy'),shape('star')),
    preset('well-done','잘했어','자신감','두 개의 체크 표시로 응원해요.',shape('check'),motion='change',alternate=(shape('star'),shape('star'))),
    preset('determined','굳은 결심','자신감','단단한 눈썹으로 의지를 보여줘요.',mirror(shape('angry')),shape('confident')),
    preset('relaxed','여유로움','자신감','느긋하게 눈을 가늘게 뜨고 쉬어요.',shape('sleep'),shape('smile')),
    preset('sad','슬픔','슬픔','처진 눈썹으로 속상한 마음을 표현해요.',mirror(shape('sad')),shape('sad')),
    preset('tearful','눈물 맺힘','슬픔','눈 아래에 작은 눈물이 맺혀요.',mirror(shape('tear')),shape('tear')),
    preset('crying','울먹울먹','슬픔','양쪽 눈에서 눈물이 흘러요.',shape('cry'),motion='change',alternate=(shape('sob'),mirror(shape('sob')))),
    preset('sobbing','엉엉 울음','슬픔','구불구불한 눈물로 크게 울어요.',shape('sob'),mirror(shape('sob')),motion='change',alternate=(shape('cry'),shape('cry'))),
    preset('disappointed','실망','슬픔','힘이 빠진 눈과 처진 눈썹을 보여줘요.',shape('drowsy'),shape('sad')),
    preset('surprised','깜짝 놀람','놀람·긴장','동그랗게 커진 눈으로 놀라요.',shape('surprise')),
    preset('shocked','화들짝','놀람·긴장','느낌표 두 개로 큰 놀람을 표현해요.',shape('exclaim'),motion='change',alternate=(shape('surprise'),shape('surprise'))),
    preset('nervous','긴장','놀람·긴장','또렷한 눈 옆에 식은땀이 맺혀요.',gaze(),shape('tear')),
    preset('scared','두려움','놀람·긴장','작아진 눈동자로 움츠러든 마음을 보여줘요.',shape('tiny'),motion='change',alternate=(gaze(2,3),gaze(4,3))),
    preset('confused','어리둥절','놀람·긴장','두 개의 물음표로 궁금함을 표현해요.',shape('question')),
    preset('angry','화남','분노·불만','안쪽으로 내려오는 눈썹을 보여줘요.',mirror(shape('angry')),shape('angry')),
    preset('furious','불같은 분노','분노·불만','불꽃 눈이 이글이글 움직여요.',shape('fire'),motion='change',alternate=(mirror(shape('fire')),mirror(shape('fire')))),
    preset('annoyed','짜증','분노·불만','한쪽 눈을 가늘게 뜨고 불만을 표현해요.',shape('drowsy'),shape('angry')),
    preset('skeptical','의심','분노·불만','서로 다른 눈썹으로 의심스러워해요.',shape('confident'),shape('sad')),
    preset('grumpy','심통','분노·불만','굵은 눈썹 아래로 뾰로통하게 바라봐요.',shape('grumpy')),
    preset('sleepy','졸림','피곤·휴식','눈꺼풀이 무거워져 천천히 감겨요.',shape('drowsy')),
    preset('sleeping','새근새근','피곤·휴식','두 눈을 편안하게 감고 쉬어요.',shape('sleep'),motion='still'),
    preset('exhausted','기진맥진','피곤·휴식','X자 눈으로 지친 상태를 표현해요.',shape('exhausted'),motion='still'),
    preset('dizzy','어질어질','피곤·휴식','소용돌이 눈이 빙글빙글 돌아요.',shape('spiral'),motion='change',alternate=(shape('spiral-turn'),shape('spiral-turn'))),
    preset('bored','심심함','피곤·휴식','반쯤 감긴 눈으로 느긋하게 기다려요.',shape('bored')),
    preset('mischievous','장난꾸러기','장난·호기심','짓궂은 눈과 웃는 눈을 함께 보여줘요.',mirror(shape('angry')),shape('happy')),
    preset('curious','궁금해','장난·호기심','물음표와 동그란 눈으로 질문해요.',shape('question'),gaze()),
    preset('cheeky','장난 윙크','장난·호기심','윙크와 별 눈으로 장난스럽게 인사해요.',shape('closed'),shape('star')),
    preset('cross-eyed','눈 모으기','장난·호기심','눈동자를 코 쪽으로 모아봐요.',gaze(1,3),gaze(5,3)),
    preset('googly','눈 벌리기','장난·호기심','눈동자가 서로 반대쪽을 바라봐요.',gaze(5,3),gaze(1,3)),
    preset('sparkling','반짝반짝','기호·응원','십자 별빛이 반짝여요.',shape('sparkle'),motion='change',alternate=(shape('diamond'),shape('diamond'))),
    preset('music','흥얼흥얼','기호·응원','음표 두 개로 신나는 리듬을 표현해요.',shape('music'),mirror(shape('music')),motion='change',alternate=(mirror(shape('music')),shape('music'))),
    preset('energy','에너지 충전','기호·응원','번개 눈으로 힘을 충전해요.',shape('bolt'),motion='change',alternate=(mirror(shape('bolt')),mirror(shape('bolt')))),
    preset('bloom','꽃 피는 마음','기호·응원','활짝 핀 꽃으로 따뜻한 마음을 전해요.',shape('flower'),motion='still'),
    preset('celebrate','축하해','기호·응원','햇살과 다이아몬드가 번갈아 빛나요.',shape('sun'),shape('diamond'),motion='change',alternate=(shape('diamond'),shape('sun'))),
]
BY_ID = {item['id']: item for item in CATALOG}


def eyes_command(value):
    return {'cmd': 'eyes', 'left': value['left'], 'right': value['right'], 'brightness': 1}


def frame_at(frames, elapsed_ms):
    position = elapsed_ms % sum(f['ms'] for f in frames)
    for index, value in enumerate(frames):
        if position < value['ms']:
            return index
        position -= value['ms']
    return 0


def eyes_only_arm():
    return {'cmd': 'arm', 'config': {
        'calibration_id': 1, 'min_cdeg': [8000]*6, 'max_cdeg': [10000]*6,
        'neutral_cdeg': [9000]*6, 'min_us': [1000]*6, 'max_us': [2000]*6,
        'invert_mask': 0, 'max_speed_cdeg_s': 1000,
        'servo_enabled': False, 'matrix_installed': True,
    }}


class EyePlayer:
    """One persistent or finite eye job; Stop fences pending USB work."""
    def __init__(self, pico, events):
        self.pico, self.events = pico, events
        self.gate = asyncio.Lock()
        self.stop_gate = asyncio.Lock()
        self.epoch = 0
        self.stopping = False
        self.active = None
        self.last = None
        self.error = None
        self.tasks = set()
        self.default_on = False
        self.default_preset = 'neutral'
        self.auto_allowed = None
        self.automatic_status = None
        self.external_until = 0

    async def send(self, command):
        result = await asyncio.get_running_loop().run_in_executor(None, self.pico.command, command)
        if not result.get('ok'):
            raise RuntimeError(result.get('error', 'Pico가 요청을 거부했습니다.'))
        return result

    def snapshot(self):
        active = self.active
        return {'active': active is not None, 'stopping': self.stopping,
                'preset_id': active['preset']['id'] if active else None,
                'name': active['preset']['name'] if active else None,
                'frame_index': active['frame'] if active else 0,
                'persistent': bool(active and active['until'] is None),
                'mode': active.get('mode', 'manual') if active else None,
                'remaining_ms': max(0, int((active['until']-time.monotonic())*1000)) if active and active['until'] is not None else 0,
                'automatic': self.automatic_status() if self.automatic_status else None,
                'last': self.last, 'error': self.error}

    async def start(self, preset_id, seconds):
        if preset_id not in BY_ID or seconds not in (3, 5, 10):
            raise ValueError('지원하지 않는 표정 또는 표시 시간입니다.')
        return await self._start(preset_id, seconds)

    async def hold(self, preset_id):
        if preset_id not in BY_ID:
            raise ValueError('등록되지 않은 자동 표정입니다.')
        return await self._start(preset_id, None)

    async def _start(self, preset_id, seconds):
        automatic = seconds is None
        if self.stopping:
            raise RuntimeError('정지 중입니다. 완료 후 다시 선택해 주세요.')
        requested = self.epoch
        async with self.gate:
            if self.stopping or requested != self.epoch:
                raise RuntimeError('정지로 취소된 요청입니다. 다시 선택해 주세요.')
            if automatic and (not self.default_on or self.auto_allowed and not self.auto_allowed()):
                raise RuntimeError('자동 표정이 일시 정지되었습니다.')
            status = self.pico.snapshot()
            if not status['connected']:
                raise RuntimeError('Pico 연결을 확인해 주세요.')
            if (status.get('device') or {}).get('running') not in (None, 'None', 'Idle'):
                raise RuntimeError('다른 장치 시험이 진행 중입니다.')
            previous = self.active
            replace = bool(previous and previous['session'] == status.get('session') and (automatic or self.default_on))
            if replace and automatic and previous['preset']['id'] == preset_id and previous['until'] is None:
                return {'ok': True, 'playback': self.snapshot()}
            self.epoch += 1
            token = self.epoch
            self.active = None
            self.error = None
            item = BY_ID[preset_id]
            try:
                # Firmware keeps ACTIVE latched after SetEyes; a fresh Arm needs
                # acknowledged Stop cleanup, including when replacing a preset.
                if not replace:
                    await self.send({'cmd': 'stop'})
                    if token != self.epoch or automatic and not self.default_on:
                        raise RuntimeError('표정 시험이 정지로 취소됐습니다.')
                    await self.send(eyes_only_arm())
                    if token != self.epoch or automatic and not self.default_on:
                        raise RuntimeError('표정 시험이 정지로 취소됐습니다.')
                result = await self.send(eyes_command(item['frames'][0]))
                if token != self.epoch:
                    raise RuntimeError('표정 시험이 정지로 취소됐습니다.')
            except Exception:
                if token == self.epoch:
                    try:
                        await self.send({'cmd': 'stop'})
                    except Exception as cleanup:
                        self.error = str(cleanup)
                raise
            now = time.monotonic()
            self.active = {'preset': item, 'since': now, 'until': None if automatic else now+seconds,
                           'mode': 'automatic' if automatic else 'manual',
                           'frame': 0, 'session': status.get('session')}
            task = asyncio.create_task(self.play(token))
            self.tasks.add(task)
            task.add_done_callback(self.tasks.discard)
            self.events.add('eyes', '{} · {}'.format(item['name'], '자동 상시 표시' if automatic else '{}초 표시 시작'.format(seconds)))
            return {'ok': True, 'ack_code': result.get('ack_code'), 'playback': self.snapshot()}

    async def play(self, token):
        expected_session = self.active['session'] if self.active else None
        try:
            while token == self.epoch and self.active is not None:
                await asyncio.sleep(.08)
                if token != self.epoch or self.active is None:
                    return
                active = self.active
                status = self.pico.snapshot()
                if not status['connected'] or status.get('session') != active['session']:
                    raise RuntimeError('USB 연결 또는 세션 변경으로 표정 시험을 종료했습니다.')
                if active['until'] is not None and time.monotonic() >= active['until']:
                    async with self.gate:
                        if token != self.epoch:
                            return
                        restore = self.default_on and (self.auto_allowed is None or self.auto_allowed())
                        if restore:
                            item = BY_ID[self.default_preset]
                            await self.send(eyes_command(item['frames'][0]))
                        else:
                            await self.send({'cmd': 'stop'})
                        if token != self.epoch:
                            return
                        self.last = {'id': active['preset']['id'], 'name': active['preset']['name'], 'result': 'completed'}
                        self.active = {'preset': item, 'since': time.monotonic(), 'until': None,
                                       'mode': 'automatic', 'frame': 0, 'session': active['session']} if restore else None
                        self.events.add('eyes', '{} · {}'.format(active['preset']['name'], '자동 표정 복귀' if restore else '표시 완료, 소등'))
                    if restore:
                        continue
                    return
                index = frame_at(active['preset']['frames'], int((time.monotonic()-active['since'])*1000))
                if index != active['frame']:
                    async with self.gate:
                        if token != self.epoch:
                            return
                        await self.send(eyes_command(active['preset']['frames'][index]))
                        if token == self.epoch:
                            active['frame'] = index
        except Exception as error:
            if token != self.epoch:
                return
            self.epoch += 1
            failed_epoch = self.epoch
            self.active = None
            self.error = str(error)
            self.events.add('eyes', self.error, 'warning')
            # Stop only; never replay Arm/Eyes after a failed frame or new USB session.
            async with self.gate:
                current = self.pico.snapshot()
                if self.epoch == failed_epoch and current.get('session') == expected_session and current.get('connected'):
                    try:
                        await self.send({'cmd': 'stop'})
                    except Exception:
                        pass

    async def stop(self):
        async with self.stop_gate:
            return await self._stop()

    async def _stop(self):
        self.epoch += 1
        self.stopping = True
        inflight = self.gate.locked()
        if self.active:
            self.last = {'id': self.active['preset']['id'], 'name': self.active['preset']['name'], 'result': 'stopped'}
        self.active = None
        try:
            # An independent UDP Stop preempts a lost Arm/Eyes ACK immediately.
            try:
                result = await self.send({'cmd': 'stop'})
            finally:
                if inflight:
                    # Fence an Arm submitted just before Stop: no queued work may re-arm it.
                    async with self.gate:
                        result = await self.send({'cmd': 'stop'})
            self.error = None
            return result
        finally:
            self.stopping = False

    async def command(self, command):
        if command['cmd'] == 'stop':
            return await self.stop()
        if command['cmd'] == 'test' and (self.active or self.gate.locked()):
            await self.stop()
        if command['cmd'] == 'test':
            self.external_until = time.monotonic() + 1
        requested = self.epoch
        async with self.gate:
            if self.stopping or requested != self.epoch:
                raise RuntimeError('정지로 취소된 요청입니다.')
            return await self.send(command)

    async def close(self):
        if self.active or self.gate.locked():
            try:
                await self.stop()
            except Exception:
                pass
        self.epoch += 1
        if self.tasks:
            await asyncio.gather(*tuple(self.tasks), return_exceptions=True)
