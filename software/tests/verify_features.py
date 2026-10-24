#!/usr/bin/env python3
"""Real Pico/audio + explicitly synthetic loopback API contracts. No cloud calls.
Temporarily commands six bare servos to neutral and +2 nominal degrees, then Stop.
Installed calibration is never enabled or edited. Requires no other device owner.
"""
import argparse,json,os,signal,socket,subprocess,tempfile,threading,time,io,wave
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from verify_runtime import recv,send
class Fixture(BaseHTTPRequestHandler):
    mode='ok';hint='문제에 주어진 조건을 먼저 하나 찾아볼까?';calls=0;started=threading.Event()
    tts_calls=0;tts_started=threading.Event()
    def log_message(self,*a):pass
    def do_GET(self):
        raw=json.dumps({'plan':'free','credits':{'plan_credits':15000,'used_credits':15000 if Fixture.mode=='credits_empty' else 0}}).encode()
        self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_POST(self):
        n=int(self.headers.get('Content-Length',0));assert 0<n<2_000_000
        body=json.loads(self.rfile.read(n));mode=Fixture.mode;hint=Fixture.hint;Fixture.calls+=1;Fixture.started.set()
        if self.path.endswith('/v1/text-to-speech'):
            assert body['language']=='kor' and body['output']['audio_format']=='wav';Fixture.tts_calls+=1;Fixture.tts_started.set()
            if mode=='tts_slow':time.sleep(3)
            out=io.BytesIO()
            with wave.open(out,'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(44100);w.writeframes(bytes(44100*2))
            raw=b'invalid' if mode=='tts_badwav' else out.getvalue();self.send_response(402 if mode=='tts_402' else 200);self.send_header('Content-Length',str(len(raw)));self.end_headers()
            try:self.wfile.write(raw)
            except (BrokenPipeError,ConnectionResetError):pass
            return
        if mode=='slow':time.sleep(3)
        code=429 if mode=='429' else 200
        if code==429:v={'error':{'status':'RESOURCE_EXHAUSTED'}}
        elif mode=='malformed':v={'invalid':'fixture'}
        elif 'questions' in body:
            if isinstance(body['questions'],list):v={'model':'fixture-decisions','answers':[{'type':'refusal','name':'action'}] if mode=='refusal' else [{'type':'choice','name':'action','choice':'offer_hint','confidence':.99}],'usage':{'input_tokens':1,'output_tokens':1}}
            else:v={'model':'fixture-jev','answers':{} if mode=='refusal' else {k:{'type':'noul','noul':.99 if k=='offer_hint' else .01} for k in body['questions']},'usage':{'input_tokens':1,'output_tokens':1}}
        elif 'contents' in body:
            content={'action':'offer_hint','confidence':.99,'hint':hint}
            if 'hint' not in body.get('generationConfig',{}).get('responseJsonSchema',{}).get('properties',{}):content.pop('hint')
            if not body.get('generationConfig',{}).get('responseJsonSchema'):text=hint
            else:text=json.dumps(content,ensure_ascii=False)
            v={'modelVersion':'fixture-gemini','candidates':[{'finishReason':'SAFETY' if mode=='refusal' else 'STOP','content':{'parts':[{'text':text}]}}],'usageMetadata':{'promptTokenCount':1,'candidatesTokenCount':1}}
        else:v={'status':'completed','model':'fixture-openai','output':[{'type':'message','content':[{'type':'output_text','text':hint}]}],'usage':{'input_tokens':1,'output_tokens':1}}
        raw=json.dumps(v,ensure_ascii=False).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers()
        try:self.wfile.write(raw)
        except (BrokenPipeError,ConnectionResetError):pass
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);a=parser.parse_args()
    repo=Path(__file__).resolve().parents[2];binary=repo/'software/target/release/nano-runtime';procs={};logs={};report={'real_pico_and_audio':True,'cloud_calls':0,'provider_evidence':'synthetic loopback contract checks, not provider accuracy/latency','checks':[],'physical_servo_motion_confirmed':False}
    server=ThreadingHTTPServer(('127.0.0.1',0),Fixture);server.daemon_threads=True;threading.Thread(target=server.serve_forever,daemon=True).start()
    with tempfile.TemporaryDirectory(prefix='features-') as temp:
        root=Path(temp);calibration=root/'actuators.json';calibration.write_bytes((repo/'software/config/actuators.json').read_bytes())
        env=os.environ.copy();env.update(NANO_RUN=temp,NANO_DB=str(root/'memory.sqlite3'),NANO_CONFIG=str(repo/'apps/device-dashboard/pico-config.json'),NANO_BRIDGE=str(repo/'tools/pico-device-bench/target/release/pico-device-bench'),NANO_ACTUATORS=str(calibration),NANO_AI_WORKER=str(repo/'software/workers/local_ai.py'),NANO_AI_TEST='1',NANO_AI_TEST_URL='http://127.0.0.1:'+str(server.server_port),NANO_DECISION_PROVIDER='gemini',NANO_GENERATION_PROVIDER='gemini')
        env['NANO_TTS_BACKEND']='espeak';env['NANO_TYPECAST_VOICE_ID']='tc_fixture'
        for k in ['OPENAI_API_KEY','GEMINI_API_KEY','TYPESAFE_API_KEY','TYPECAST_API_KEY']:env.pop(k,None)
        def check(name,value=True):assert value,name;report['checks'].append(name)
        def rpc(role,body,ok=True):
            req={'v':1,'id':time.monotonic_ns(),'deadline_ms':int(time.monotonic()*1000)+2000,'body':body}
            with socket.socket(socket.AF_UNIX) as s:
                s.settimeout(5);s.connect(str(root/(role+('.stop.sock' if body['cmd']=='stop' else '.control.sock'))));send(s,json.dumps(req).encode());r=json.loads(recv(s));assert r['ok']==ok,r;return r['data']
        def wait(fn,seconds=20):
            end=time.monotonic()+seconds
            while time.monotonic()<end:
                try:
                    r=fn()
                    if r:return r
                except (OSError,EOFError,AssertionError):pass
                time.sleep(.05)
            raise AssertionError('timeout waiting for condition')
        def start(role):
            f=open(root/(role+'.log'),'ab');logs.setdefault(role,[]).append(f);procs[role]=subprocess.Popen([str(binary),'serve',role],env=env,stdout=f,stderr=f)
            wait(lambda:rpc(role,{'cmd':'status'})['role']==role)
        def kill(role):
            p=procs[role]
            if p.poll() is None:
                p.send_signal(signal.SIGINT)
                try:p.wait(8)
                except subprocess.TimeoutExpired:p.kill();p.wait()
        def finish():return wait(lambda:(lambda r:r if r.get('phase') in ['done','failed'] else None)(rpc('controllerd',{'cmd':'turn_result'})),30)
        def turn(text='힌트 하나 줘',speak=False):
            rpc('controllerd',{'cmd':'start_turn','text':text,'cloud_consent':True,'speak':speak});return finish()
        def provider(name,generation='gemini'):
            kill('dialogued');env['NANO_DECISION_PROVIDER']=name;env['NANO_GENERATION_PROVIDER']=generation;start('dialogued');Fixture.mode='ok';Fixture.started.clear()
        try:
            for role in ['picod','audiod','memoryd','dialogued','controllerd']:start(role)
            wait(lambda:rpc('picod',{'cmd':'status'})['fresh']);wait(lambda:rpc('audiod',{'cmd':'status'})['fresh'])
            rpc('controllerd',{'cmd':'light','rgb':[255,0,0],'brightness':16,'period_ms':0},ok=False);check('quiet rejects light without explicit Help')
            n=Fixture.calls;r=turn('잠깐 기다려');check('local Wait avoids model and speech',Fixture.calls==n and r['result']['action']=='wait')
            rpc('controllerd',{'cmd':'start_turn','text':'힌트 줘','cloud_consent':False});r=finish();check('missing consent fails quiet without network',r['phase']=='failed' and Fixture.calls==n)
            for name,generation in [('gemini','gemini'),('decisions','openai'),('jev','gemini')]:
                provider(name,generation);r=turn();check(name+' adapter -> policy -> one hint',r['phase']=='done' and r['result']['dialogue']['action']=='offer_hint' and r['result']['dialogue']['classification']['transport']=='fixture_loopback');check(name+' returns to quiet',rpc('controllerd',{'cmd':'status'})['phase']=='quiet')
            Fixture.hint='3이 3개씩 있는 묶음으로 그려보세요.';r=turn();check('observed incorrect numeric hint replaced before speech',r['phase']=='done' and r['result']['dialogue']['numeric_hint_replaced'] and '3' not in r['result']['dialogue']['hint']);Fixture.hint='문제에 주어진 조건을 먼저 하나 찾아볼까?'
            provider('gemini');r=turn(speak=True);check('real Korean local TTS -> PCM ACK -> ALSA -> quiet',r['phase']=='done' and r['result']['spoken']);report['tts_result']=r
            env['NANO_TTS_BACKEND']='typecast';provider('gemini');r=turn(speak=True)
            check('Typecast contract -> bounded WAV -> resample -> PCM -> ALSA',r['phase']=='done' and r['result']['dialogue']['tts']['provider']=='typecast' and r['result']['spoken'])
            check('temporary Typecast audio removed after completed turn',not list(root.glob('turn-*/typecast.wav')))
            for mode in ['credits_empty','tts_402','tts_badwav']:
                Fixture.mode=mode;r=turn(speak=True);check('Typecast '+mode+' fails quiet without fallback',r['phase']=='failed' and rpc('controllerd',{'cmd':'status'})['phase']=='quiet')
            Fixture.mode='tts_slow';Fixture.tts_started.clear();rpc('controllerd',{'cmd':'start_turn','text':'힌트 줘','cloud_consent':True,'speak':True});assert Fixture.tts_started.wait(5)
            rpc('controllerd',{'cmd':'stop'});time.sleep(3.1);check('Stop cancels Typecast and late WAV never plays',rpc('controllerd',{'cmd':'turn_result'})['phase']=='cancelled' and not list(root.glob('turn-*/typecast.wav')))
            env['NANO_TTS_BACKEND']='espeak';provider('gemini')
            for mode in ['429','malformed','refusal']:
                Fixture.mode=mode;n=Fixture.calls;r=turn();check(mode+' fails quiet and never retries',r['phase']=='failed' and Fixture.calls==n+1 and rpc('controllerd',{'cmd':'status'})['phase']=='quiet')
            Fixture.mode='slow';Fixture.started.clear();rpc('controllerd',{'cmd':'start_turn','text':'힌트 줘','cloud_consent':True});assert Fixture.started.wait(3)
            t=time.monotonic();rpc('controllerd',{'cmd':'stop'});report['stop_during_provider_ms']=round((time.monotonic()-t)*1000);check('Stop cancels in-flight provider independent of reply',rpc('controllerd',{'cmd':'status'})['phase']=='stopped');time.sleep(3.1);check('late provider reply never resumes speech',rpc('controllerd',{'cmd':'turn_result'})['phase']=='cancelled')
            Fixture.mode='slow';Fixture.started.clear();rpc('controllerd',{'cmd':'start_turn','text':'옛 질문','cloud_consent':True});assert Fixture.started.wait(3)
            old=rpc('controllerd',{'cmd':'status'})['turn_epoch'];Fixture.mode='ok';Fixture.hint='정정된 문제에서 조건을 찾아볼까?';rpc('controllerd',{'cmd':'correct','text':'새 질문에서 힌트 줘','cloud_consent':True,'speak':False});r=finish();check('correction cancels old job and starts a fresh epoch',r['phase']=='done' and r['epoch']>old and r['result']['dialogue']['hint']==Fixture.hint)
            rpc('memoryd',{'cmd':'memory','request':{'op':'save','text':'내가 고른 독서','confirmed':True,'source':'user'}},ok=False);check('memory opt-in required')
            rpc('memoryd',{'cmd':'memory','request':{'op':'consent','enabled':True}});rpc('memoryd',{'cmd':'memory','request':{'op':'save','text':'독서 먼저 5쪽 읽기','confirmed':True,'source':'user'}})
            kill('memoryd');start('memoryd');v=rpc('memoryd',{'cmd':'memory','request':{'op':'search','query':'독서'}});check('confirmed memory survives owner restart',len(v['notes'])==1)
            note=int(v['notes'][0]['id']);rpc('memoryd',{'cmd':'memory','request':{'op':'update','id':note,'text':'독서 먼저 3쪽 읽기','confirmed':False,'source':'user correction'}},ok=False)
            rpc('memoryd',{'cmd':'memory','request':{'op':'update','id':note,'text':'독서 먼저 3쪽 읽기','confirmed':True,'source':'user correction'}})
            kill('memoryd');start('memoryd');v=rpc('memoryd',{'cmd':'memory','request':{'op':'search','query':'3쪽'}});check('explicit memory correction preserves note ID and confirmation time after restart',len(v['notes'])==1 and int(v['notes'][0]['id'])==note and bool(v['notes'][0]['confirmed_at']))
            rpc('memoryd',{'cmd':'memory','request':{'op':'delete_all'}});check('memory delete revokes consent and clears notes',rpc('memoryd',{'cmd':'memory','request':{'op':'list'}})['notes']==[])
            rpc('controllerd',{'cmd':'help'});rpc('controllerd',{'cmd':'light','rgb':[255,180,100],'brightness':16,'period_ms':800});wait(lambda:rpc('picod',{'cmd':'status'})['state']['telemetry'].get('outputs',{}).get('light_active'));check('general bounded light reaches Pico outputs');time.sleep(.5)
            rpc('controllerd',{'cmd':'pose','targets_cdeg':[9000]*6,'move_ms':1000},ok=False);check('uncalibrated operational servos blocked');rpc('controllerd',{'cmd':'stop'})
            rpc('controllerd',{'cmd':'help'});rpc('controllerd',{'cmd':'light','rgb':[20,100,255],'brightness':16,'period_ms':0})
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as s:
                s.settimeout(3);t=time.monotonic();s.sendto(b'{"cmd":"stop"}',('127.0.0.1',37920));assert json.loads(s.recv(8192))['ok']
            wait(lambda:rpc('controllerd',{'cmd':'status'})['phase']=='stopped',3);report['mcu_stop_to_controller_observed_ms']=round((time.monotonic()-t)*1000);check('MCU-only Stop revokes turn and flushes Nano audio',not rpc('audiod',{'cmd':'status'})['lease_valid'])
            c=json.loads(calibration.read_text());c.update(servo_enabled=True,calibration_id=9001);calibration.write_text(json.dumps(c));rpc('controllerd',{'cmd':'help'})
            rpc('controllerd',{'cmd':'pose','targets_cdeg':[9000]*6,'move_ms':500});wait(lambda:rpc('picod',{'cmd':'status'})['state']['telemetry'].get('outputs',{}).get('applied_seq',0)>0);check('bench neutral command reports register Applied')
            rpc('controllerd',{'cmd':'pose','targets_cdeg':[11000]*6,'move_ms':1000},ok=False);check('Pico rejects out-of-calibration pose')
            rpc('controllerd',{'cmd':'pose','targets_cdeg':[9200]*6,'move_ms':1000});time.sleep(.3);rpc('controllerd',{'cmd':'stop'});wait(lambda:rpc('picod',{'cmd':'status'})['state']['telemetry']['status']['oe_high']);check('Stop cancels interpolation and gates OE high')
            rpc('controllerd',{'cmd':'help'});v=rpc('controllerd',{'cmd':'eyes','left':[255]*8,'right':[255]*8,'brightness':1},ok=False);check('missing matrix rejected by Pico capability','Unsupported' in str(v));rpc('controllerd',{'cmd':'stop'})
            report['passed']=True
        finally:
            for role in ['controllerd','audiod','picod','memoryd','dialogued']:
                if role in procs:kill(role)
            report['fixture_requests']=Fixture.calls;report['process_returncodes']={r:p.poll() for r,p in procs.items()}
            for group in logs.values():
                for f in group:f.close()
            report['logs']={r:(root/(r+'.log')).read_text(errors='replace')[-6000:] for r in procs};Path(a.output).write_text(json.dumps(report,ensure_ascii=False,indent=2))
    server.shutdown();print(json.dumps({'passed':report.get('passed',False),'checks':len(report['checks']),'cloud_calls':0}))
if __name__=='__main__':main()
