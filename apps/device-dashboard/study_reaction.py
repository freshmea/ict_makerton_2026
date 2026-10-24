"""One manual Decisions window -> bounded, cancellable device feedback. No provider keys."""
import asyncio
import audioop
import hashlib
import io
import json
from pathlib import Path
import tempfile
import time
import wave

from observer_client import rpc
from tts_client import synthesize
from button_audio import live_tone
from eye_expressions import eyes_only_arm

PHRASES = {
    'away': '잠깐 자리를 비웠네요. 돌아오면 하던 공부를 이어 가요.',
    'engaged': '공부를 이어 가는 모습이 보여요. 지금처럼 한 단계씩 해 봐요.',
    'refocus': '잠깐 시선이 다른 곳을 향했네요. 준비되면 하던 과제로 돌아가 볼까요?',
    'unknown': '지금 화면만으로는 공부 상태를 확인하기 어려워요. 편하게 자세를 잡고 이어 가요.',
}
COLORS = {'away': [160,80,180], 'engaged': [35,210,90], 'refocus': [40,130,240], 'unknown': [230,155,25]}


def choose(result):
    observed = result.get('observed_is_away', result.get('is_away'))
    if result.get('presence_basis') == 'user_policy_unknown_as_away' or observed is None:
        return 'unknown'
    if observed is True:
        return 'away'
    focus, gaze = result.get('focus_score'), result.get('study_gaze_score')
    if isinstance(focus, (int, float)) and focus >= 7:
        return 'engaged'
    behaviors = result.get('behaviors') or []
    if (isinstance(gaze, (int, float)) and gaze < 5
            or any(b.get('id') == 'gaze_away' and b.get('state') == 'observed' for b in behaviors)):
        return 'refocus'
    return 'unknown'


class SpeechCache:
    def __init__(self, audio, directory):
        self.audio, self.directory = audio, Path(directory)

    def prepare(self, kind):
        text = PHRASES[kind]
        path = self.directory / (hashlib.sha256(('study-v1:' + text).encode()).hexdigest() + '.wav')
        if path.exists():
            data = path.read_bytes()
        else:
            data, _ = synthesize(text)
            with wave.open(io.BytesIO(data), 'rb') as reader:
                if reader.getnchannels() != 1 or reader.getsampwidth() != 2:
                    raise ValueError('TTS PCM format')
                rate = reader.getframerate()
                if not 8000 <= rate <= 48000 or not 0 < reader.getnframes() <= rate*15:
                    raise ValueError('TTS duration')
                pcm = reader.readframes(reader.getnframes())
            if rate != 48000:pcm = audioop.ratecv(pcm, 2, 1, rate, 48000, None)[0]
            pcm, _ = self.audio.process_pcm(pcm, 6)
            data = self.audio.wav(pcm)
            self.directory.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=str(self.directory), delete=False) as output:
                output.write(data)
                temporary = Path(output.name)
            temporary.chmod(0o640);temporary.replace(path)
        with wave.open(io.BytesIO(data), 'rb') as reader:
            if (reader.getframerate(),reader.getsampwidth(),reader.getnchannels()) != (48000,2,1) or not 0 < reader.getnframes() <= 720000:
                raise ValueError('Cached speech format')
        return data


class StudyReaction:
    def __init__(self, pico, audio, eyes, servos, live, buttons, events,
                 directory='/var/lib/300seconds-dashboard/study-reactions'):
        self.pico,self.audio,self.eyes,self.servos = pico,audio,eyes,servos
        self.live,self.buttons,self.events = live,buttons,events
        self.directory = Path(directory)
        self.speech = SpeechCache(audio, self.directory/'speech')
        self.state = {'phase':'idle','switch':2,'hold_count':4,'hold_ms':3200}
        self.epoch, self.starting, self.running = 0, False, True
        self.task = self.switch_task = None
        self.eye_lease = None
        self.owner = None

    @property
    def busy(self):
        return self.starting or self.task is not None and not self.task.done()

    def snapshot(self):
        return dict(self.state, busy=self.busy)

    def guard_live(self):
        if self.busy:raise RuntimeError('책상 분석·기기 반응이 끝난 뒤 Live를 시작하세요.')

    def check(self, token):
        if token != self.epoch or not self.running:raise asyncio.CancelledError()
        session = self.state.get('pico_session')
        if session is not None:
            state = self.pico.snapshot()
            if not state.get('connected') or state.get('session') != session:
                raise RuntimeError('Pico 연결이 변경되어 기기 반응을 중단했습니다.')

    def restore_eyes(self):
        if self.eye_lease is not None and self.eyes.external_until == self.eye_lease:
            self.eyes.external_until = time.monotonic()+.25
        self.eye_lease = None

    async def command(self, value):
        result = await self.eyes.command(value)
        if not result.get('ok'):raise RuntimeError(result.get('error') or '기기 명령 응답 오류')
        return result

    async def start(self, camera=0, source='dashboard'):
        if self.busy:raise RuntimeError('책상 분석·기기 반응이 이미 진행 중입니다.')
        if self.live.active or self.live.state['phase'] in ('preparing','closing'):
            raise RuntimeError('Live 대화를 종료한 뒤 책상 분석을 시작하세요.')
        if self.servos.active or self.servos.gate.locked():
            raise RuntimeError('수동 서보 제어를 정지한 뒤 시작하세요.')
        if self.audio.play_lock.locked():raise RuntimeError('스피커 사용이 끝난 뒤 시작하세요.')
        pico = self.pico.snapshot()
        if not pico.get('connected'):raise RuntimeError('Pico 연결을 확인한 뒤 분석을 시작하세요.')
        self.epoch += 1;token = self.epoch;self.starting = True
        self.state = {'phase':'starting','source':source,'switch':2,'hold_count':4,'hold_ms':3200,
                      'started':time.time(),'error':None,'reaction':None,'pico_session':pico.get('session')}
        try:
            state = await rpc({'op':'start','provider':'decisions','camera':camera})
            self.check(token)
            job = state['job']
            self.state.update(phase=job['phase'],job_id=job['id'])
            self.eye_lease = time.monotonic()+120
            self.eyes.external_until = self.eye_lease
            self.task = asyncio.create_task(self.run(token,job['id']))
            return dict(state,reaction=self.snapshot())
        except BaseException:
            if token != self.epoch:
                try:await rpc({'op':'cancel'})
                except Exception:pass
            self.restore_eyes()
            self.state['phase'] = 'failed'
            raise
        finally:self.starting = False

    async def run(self, token, identifier):
        try:
            deadline = time.monotonic()+75
            while time.monotonic() < deadline:
                self.check(token)
                state = await rpc({'op':'status'})
                job = state['job']
                if job.get('id') != identifier:raise RuntimeError('분석 작업이 변경됐습니다.')
                self.state['phase'] = job['phase']
                if job['phase'] == 'completed':
                    result = job['result'];break
                if job['phase'] in ('failed','cancelled'):raise RuntimeError(job.get('error') or '분석 취소')
                await asyncio.sleep(.4)
            else:raise RuntimeError('분석 응답 시간이 초과됐습니다.')
            self.check(token)
            self.state['phase'] = 'reacting'
            self.state['result'] = result
            await self.react(token,result)
            self.check(token)
            self.state.update(phase='completed',completed=time.time())
            self.directory.mkdir(parents=True,exist_ok=True)
            path = self.directory/(identifier+'.json')
            path.write_text(json.dumps(self.snapshot(),ensure_ascii=False,indent=2),encoding='utf-8')
            path.chmod(0o640)
        except asyncio.CancelledError:
            self.state['phase'] = 'cancelled'
        except Exception as error:
            self.state.update(phase='failed',error=str(error)[:300])
            self.events.add('study',str(error),'warning')
        finally:
            if self.owner is not None:
                try:await self.servos.stop(self.owner)
                except Exception:pass
                self.owner = None
            self.restore_eyes()

    async def react(self, token, result):
        kind = choose(result)
        report = {'kind':kind,'text':PHRASES[kind],'rgb':COLORS[kind],
                  'speech':'pending','led':'pending','servos':[],'errors':[]}
        self.state['reaction'] = report
        data, locked, heartbeat, voice_task, hardware_owned = None, False, None, None, False
        try:
            locked = self.audio.play_lock.acquire(blocking=False)
            if locked:
                try:data = await asyncio.get_running_loop().run_in_executor(None,self.speech.prepare,kind)
                except Exception as error:report['speech']='failed';report['errors'].append(str(error)[:180])
            else:report['speech']='speaker_busy'
            self.check(token)
            ready = self.servos.snapshot()
            if self.servos.active:
                report['errors'].append('수동 서보 제어 중이므로 기기 출력을 생략했습니다.')
                if data is not None:await self.play_voice(token,data,report)
                return
            if not ready['ready']:
                report['errors'].append(ready.get('reason') or '서보 사용 중')
                hardware_owned = True
                await self.eyes.stop();self.check(token)
                await self.command(eyes_only_arm())
                await self.command({'cmd':'light','rgb':COLORS[kind],'brightness':24,'period_ms':800})
                report['led']='applied'
                if data is not None:await self.play_voice(token,data,report)
                await asyncio.sleep(2)
                return
            # Stop clears firmware telemetry to zero; retain the last acknowledged
            # target instead of treating that sentinel as a physical zero angle.
            outputs = self.pico.snapshot().get('outputs') or {}
            raw = outputs.get('commanded_cdeg') or [9000]*6
            known = ready.get('commanded_degrees') or [None]*6
            base = [max(0,min(180,round(known[i] if known[i] is not None else
                    raw[i]/100 if outputs.get('armed') else 90))) for i in range(6)]
            enabled = await self.servos.enable();self.owner = enabled['control_id']
            hardware_owned = True
            self.check(token)
            async def keepalive():
                while True:
                    self.check(token);self.servos.keepalive(self.owner)
                    await asyncio.sleep(.25)
            heartbeat = asyncio.create_task(keepalive())
            for servo in range(1,5):
                self.check(token)
                center = base[servo-1];target = center+4 if center <= 176 else center-4
                await self.servos.move(self.owner,servo,target)
                self.check(token)
                if servo == 1:
                    await self.command({'cmd':'light','rgb':COLORS[kind],'brightness':24,'period_ms':800})
                    report['led']='applied'
                    if data is not None:voice_task=asyncio.create_task(self.play_voice(token,data,report))
                await self.servos.move(self.owner,servo,center)
                report['servos'].append({'servo':servo,'from':center,'to':target,'returned':center,'acknowledged':True})
            if voice_task:await voice_task
        finally:
            if heartbeat:
                heartbeat.cancel();await asyncio.gather(heartbeat,return_exceptions=True)
            if voice_task and not voice_task.done():
                voice_task.cancel();await asyncio.gather(voice_task,return_exceptions=True)
            if locked:self.audio.play_lock.release()
            if self.owner is not None:
                try:await self.servos.stop(self.owner)
                finally:self.owner=None
            elif hardware_owned:
                try:await self.servos.stop()
                except Exception:pass

    async def play_voice(self, token, data, report):
        self.check(token)
        player = None
        try:
            self.audio.speaker={'state':'playing','kind':'study-reaction','last_result':None}
            player=await asyncio.create_subprocess_exec('aplay','-q','-D','robot_playback','-t','wav','-',
                stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.PIPE)
            _, error=await asyncio.wait_for(player.communicate(data),18)
            if player.returncode:raise RuntimeError(error.decode(errors='replace')[:180])
            report['speech']='played'
        except Exception as error:
            report['speech']='failed';report['errors'].append(str(error)[:180])
        finally:
            if player and player.returncode is None:
                player.terminate()
                try:await asyncio.wait_for(player.wait(),2)
                except asyncio.TimeoutError:player.kill();await player.wait()
            self.audio.speaker={'state':'idle','kind':'study-reaction','last_result':{'ok':report['speech']=='played'}}

    async def abort(self, cancel_remote=True):
        self.epoch += 1
        was_busy=self.busy
        if self.task and not self.task.done():
            self.task.cancel();await asyncio.gather(self.task,return_exceptions=True)
        if cancel_remote and was_busy:
            try:await rpc({'op':'cancel'})
            except Exception:pass
        self.restore_eyes()
        self.state['phase']='cancelled'
        return self.snapshot()

    def start_switch(self):
        self.switch_task=asyncio.create_task(self.switch_loop())

    async def switch_loop(self):
        while self.running:
            request=self.buttons.take_study_request()
            if request is not None:
                try:
                    if self.busy:await self.abort()
                    else:
                        await asyncio.get_running_loop().run_in_executor(None,self.audio.play_feedback,live_tone('start'))
                        if self.buttons.live_request_valid(request):await self.start(0,'SW2-hold4')
                except Exception as error:
                    self.state['error']=str(error)[:300];self.events.add('study',str(error),'warning')
            await asyncio.sleep(.1)

    async def close(self):
        self.running=False
        if self.switch_task:self.switch_task.cancel();await asyncio.gather(self.switch_task,return_exceptions=True)
        await self.abort()
