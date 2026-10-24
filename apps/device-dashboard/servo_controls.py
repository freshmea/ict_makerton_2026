"""Explicit, single-channel bench control with a browser lease and priority Stop."""
import asyncio
import secrets
import time


class ServoControls:
    LEASE_SECONDS = 2.0

    @staticmethod
    def driver_error(p):
        driver = p.get('servo_driver')
        if not driver:
            return 'PCA9685 통신 오류 · 기존 펌웨어는 주소 0x41만 확인합니다. 주소·VCC·I2C 진단이 필요합니다.'
        probes = driver.get('probes', [0, 0])
        lines = 'SDA %s / SCL %s' % ('HIGH' if driver.get('sda_high') else 'LOW',
                                     'HIGH' if driver.get('scl_high') else 'LOW')
        labels = {0: '미검사', 1: '응답', 2: 'ACK 없음', 3: '시간 초과', 4: '버스 오류', 5: '레지스터 불일치'}
        checks = ' · '.join('0x%02X %s' % (0x40+i, labels.get(code, '오류')) for i, code in enumerate(probes))
        if probes == [1, 1]: return 'PCA9685 주소 두 개가 응답해 선택을 중단했습니다. ' + checks
        if driver.get('selected_address'):
            return 'PCA9685 0x%02X 초기화/쓰기 실패 · %s' % (driver['selected_address'], lines)
        return 'PCA9685 연결 진단 · %s · %s' % (checks, lines)

    def __init__(self, pico, eyes, events):
        self.pico, self.eyes, self.events = pico, eyes, events
        self.active = False
        self.owner = None
        self.session = None
        self.deadline = 0
        self.epoch = 0
        self.armed = False
        self.commanded = [None] * 6
        self.error = None
        self.gate = asyncio.Lock()
        self.watch_task = None

    def snapshot(self):
        p = self.pico.snapshot()
        d = p.get('device') or {}
        reasons = []
        if not p.get('connected'): reasons.append('Pico 연결을 확인해 주세요.')
        if d.get('faults', 0) & 1: reasons.append(self.driver_error(p))
        supported = p.get('capabilities', {}).get('single_servo', False)
        if not supported: reasons.append('개별 서보 제어 펌웨어 업데이트가 필요합니다.')
        if d.get('running'): reasons.append('장치 시험이 진행 중입니다.')
        return {'active': self.active, 'generation': self.epoch, 'ready': not reasons, 'supported': supported,
                'reason': ' '.join(reasons), 'busy': self.gate.locked(),
                'commanded_degrees': list(self.commanded), 'error': self.error,
                'min_degrees': 0, 'max_degrees': 180, 'speed_degrees_s': 30,
                'pulse_min_us': d.get('config', {}).get('servo_min_us', 1000),
                'pulse_max_us': d.get('config', {}).get('servo_max_us', 2000)}

    def keepalive(self, owner):
        if not self.active or not owner or owner != self.owner:
            raise RuntimeError('서보 제어를 다시 시작해 주세요.')
        p = self.pico.snapshot()
        if not p.get('connected') or p.get('session') != self.session:
            # Keep the watchdog alive so stale telemetry also revokes bridge
            # keepalives; simply clearing active could leave PWM held forever.
            self.deadline = 0
            raise RuntimeError('Pico 세션이 바뀌었습니다. 서보 제어를 다시 시작해 주세요.')
        self.deadline = time.monotonic() + self.LEASE_SECONDS
        return self.snapshot()

    async def enable(self):
        if self.active or self.gate.locked():
            raise RuntimeError('이미 서보 제어 중입니다. 먼저 정지해 주세요.')
        state = self.snapshot()
        if not state['ready']: raise RuntimeError(state['reason'])
        self.epoch += 1
        token = self.epoch
        async with self.gate:
            await self.eyes.stop()
            if token != self.epoch: raise RuntimeError('정지로 취소된 요청입니다.')
            self.owner = secrets.token_urlsafe(24)
            self.session = self.pico.snapshot().get('session')
            self.active, self.armed, self.error = True, False, None
            self.deadline = time.monotonic() + self.LEASE_SECONDS
            self.watch_task = asyncio.create_task(self.watch(token))
        return {'control_id': self.owner, 'state': self.snapshot()}

    async def watch(self, token):
        while self.active and token == self.epoch:
            await asyncio.sleep(.2)
            if token != self.epoch or not self.active: return
            p = self.pico.snapshot()
            if (time.monotonic() > self.deadline or not p.get('connected')
                    or p.get('session') != self.session or (p.get('device') or {}).get('faults', 0) & 1):
                self.error = '제어 연결 만료 또는 장치 오류로 서보 출력을 정지했습니다.'
                try: await self.stop(expected_session=self.session)
                except Exception as error: self.error = str(error)
                return

    async def move(self, owner, servo, degrees):
        self.keepalive(owner)
        if not 1 <= servo <= 6 or not 0 <= degrees <= 180:
            raise ValueError('서보 1~6번, 각도 0~180°만 사용할 수 있습니다.')
        if self.gate.locked(): raise RuntimeError('앞선 서보 이동이 끝날 때까지 기다려 주세요.')
        state = self.snapshot()
        if not state['ready']: raise RuntimeError(state['reason'])
        token, session = self.epoch, self.session
        async with self.gate:
            try:
                if not self.armed:
                    config = {'calibration_id': 20261024, 'min_cdeg': [0]*6,
                              'max_cdeg': [18000]*6, 'neutral_cdeg': [9000]*6,
                              'min_us': [state['pulse_min_us']]*6,
                              'max_us': [state['pulse_max_us']]*6, 'invert_mask': 0,
                              'max_speed_cdeg_s': 3000, 'servo_enabled': True,
                              'matrix_installed': False}
                    result = await self.eyes.command({'cmd': 'arm', 'config': config})
                    if not result.get('ok'): raise RuntimeError(result.get('error', '서보 Arm 실패'))
                    if token != self.epoch: raise RuntimeError('정지로 취소된 요청입니다.')
                    self.armed = True
                result = await self.eyes.command({'cmd': 'servo', 'channel': servo-1,
                                                  'target_cdeg': degrees*100, 'move_ms': 500})
                if not result.get('ok'): raise RuntimeError(result.get('error', '서보 요청 거부'))
                seq = result.get('ack_request_seq')
                end = time.monotonic() + 8
                while time.monotonic() < end:
                    if token != self.epoch: raise RuntimeError('정지로 취소된 요청입니다.')
                    p = self.pico.snapshot()
                    if not p.get('connected') or p.get('session') != session:
                        raise RuntimeError('Pico 연결이 변경돼 이동을 취소했습니다.')
                    if (p.get('device') or {}).get('faults', 0) & 1:
                        raise RuntimeError('PCA9685 통신 오류로 이동을 중단했습니다.')
                    applied = p.get('last_applied') or {}
                    if applied.get('request_seq') == seq and applied.get('kind') == 4:
                        self.commanded[servo-1] = degrees
                        self.error = None
                        return {'ok': True, 'servo': servo, 'degrees': degrees,
                                'request_seq': seq, 'state': self.snapshot()}
                    await asyncio.sleep(.05)
                raise RuntimeError('서보 명령 완료 응답 시간이 초과됐습니다.')
            except Exception as error:
                self.error = str(error)
                await self.stop(expected_session=session)
                raise

    async def stop(self, owner=None, expected_session=None):
        if owner is not None and self.active and owner != self.owner:
            raise RuntimeError('다른 제어 세션의 정지 요청입니다.')
        self.epoch += 1
        self.active, self.armed, self.owner = False, False, None
        p = self.pico.snapshot()
        if p.get('connected') and (expected_session is None or p.get('session') == expected_session):
            try:
                return await self.eyes.stop()
            except Exception:
                # Revoke bridge keepalives if priority Stop cannot be confirmed.
                await asyncio.get_running_loop().run_in_executor(None, self.pico.stop)
                raise
        elif p.get('bridge_pid') and (expected_session is None or p.get('session') == expected_session):
            await asyncio.get_running_loop().run_in_executor(None, self.pico.stop)
        return {'ok': True, 'offline': True}

    async def probe(self):
        p = self.pico.snapshot()
        if not p.get('connected') or not p.get('capabilities', {}).get('single_servo'):
            raise RuntimeError('Pico 연결과 개별 서보 펌웨어를 확인해 주세요.')
        await self.stop()
        try:
            result = await self.eyes.command({'cmd': 'servo_probe'})
            if not result.get('ok'): raise RuntimeError('PCA9685 driver rejected probe')
        except RuntimeError as error:
            await asyncio.sleep(.05)  # Allow the bridge telemetry reader to publish the correlated probe.
            self.error = self.driver_error(self.pico.snapshot())
            raise RuntimeError(self.error) from error
        self.error = None
        return result

    async def close(self):
        if self.active or self.gate.locked():
            try: await self.stop(expected_session=self.session)
            except Exception: pass
        self.epoch += 1
        if self.watch_task:
            await self.watch_task
