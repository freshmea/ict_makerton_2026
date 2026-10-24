#!/usr/bin/env python3
"""Linux hardware acceptance. Starts seven real Rust processes, no cloud calls.
One short left LED test verifies controller-death Stop. Never tests servos.
All processes are stopped in finally; evidence excludes raw camera/audio data.
"""
import argparse, json, os, signal, socket, struct, subprocess, tempfile, time
from pathlib import Path

def exact(s, n):
    data=b''
    while len(data)<n:
        part=s.recv(n-len(data))
        if not part: raise EOFError('closed frame')
        data+=part
    return data

def recv(s):
    n=struct.unpack('!I',exact(s,4))[0]
    assert 0<n<=65536
    return exact(s,n)

def send(s, data): s.sendall(struct.pack('!I',len(data))+data)

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True);a=p.parse_args()
    repo=Path(__file__).resolve().parents[2];binary=repo/'software/target/release/nano-runtime'
    report={'real_hardware':True,'cloud_calls':0,'checks':[]}
    processes={}; logs={}
    with tempfile.TemporaryDirectory(prefix='rust-runtime-') as temp:
        root=Path(temp);env=os.environ.copy();env.update(NANO_RUN=str(root),NANO_DB=str(root/'memory.sqlite3'),NANO_CONFIG=str(repo/'apps/device-dashboard/pico-config.json'),NANO_BRIDGE=str(repo/'tools/pico-device-bench/target/release/pico-device-bench'),NANO_CUDA='1',NANO_ACTUATORS=str(repo/'software/config/actuators.json'),NANO_AI_WORKER=str(repo/'software/workers/local_ai.py'))
        def rpc(role, body, ok=True, deadline=None):
            req={'v':1,'id':time.monotonic_ns(),'deadline_ms':deadline if deadline is not None else int(time.monotonic()*1000)+2000,'body':body}
            with socket.socket(socket.AF_UNIX) as s:
                s.settimeout(5);s.connect(str(root/(role+'.control.sock')));send(s,json.dumps(req).encode());reply=json.loads(recv(s));assert reply['id']==req['id'];assert reply['ok']==ok,reply;return reply
        def check(name, value=True): assert value,name;report['checks'].append(name)
        def start(role):
            log=open(root/(role+'.log'),'ab');logs[role]=log
            processes[role]=subprocess.Popen([str(binary),'serve',role],env=env,stdout=log,stderr=log)
        def wait(name, predicate, seconds=25):
            until=time.monotonic()+seconds
            while time.monotonic()<until:
                try:
                    result=predicate()
                    if result:return result
                except (OSError,EOFError,AssertionError):pass
                time.sleep(.1)
            raise AssertionError(name)
        try:
            for role in ['picod','camerad','audiod','visiond','memoryd','dialogued','controllerd']:start(role)
            wait('sockets',lambda:all((root/(r+'.control.sock')).exists() for r in processes))
            pico=wait('real Pico telemetry',lambda: (lambda x:x if x['data']['fresh'] else None)(rpc('picod',{'cmd':'status'})))
            report['pico_initial']=pico
            check('quiet startup has no controller motion lease',not rpc('picod',{'cmd':'status'})['data']['lease_valid'])
            rpc('controllerd',{'cmd':'test','owner':0,'epoch':0,'module':'left'},ok=False);check('test before Help rejected')
            audio=wait('actual microphone',lambda:(lambda x:x if x['data']['fresh'] else None)(rpc('audiod',{'cmd':'status'})))
            cameras=wait('both CSI cameras',lambda:(lambda x:x if len([v for v in x['data']['state'].get('cameras',[]) if v.get('frame_id',0)>5])==2 else None)(rpc('camerad',{'cmd':'status'})))
            vision=wait('CUDA stats on actual frames',lambda:(lambda x:x if x['data']['fresh'] and len(x['data']['state'].get('cameras',[]))==2 else None)(rpc('visiond',{'cmd':'status'})),90)
            check('two real CSI -> tmpfs slots -> visiond',all(v['backend']=='cuda-sm53' for v in vision['data']['state']['cameras']))
            check('TensorRT FP16 semantic model on both actual cameras',all(v['inference']['backend']=='tensorrt8-fp16-sm53' for v in vision['data']['state']['cameras']))
            report.update(audio=audio,cameras=cameras,vision=vision)
            result=subprocess.check_output([str(binary),'cuda-check'],env=env,text=True);report['cuda_check']=json.loads(result);check('CUDA/CPU reference equality',report['cuda_check']['cpu_match'])
            with socket.socket(socket.AF_UNIX) as s:
                s.settimeout(3);s.connect(str(root/'audiod.capture.sock'));packet=recv(s);assert packet[:4]==b'PCM1';rate,samples=struct.unpack('!II',packet[28:36]);check('real bounded PCM capture',rate==48000 and len(packet)==36+samples*2)
            goal="child chooses 'reading'; DROP TABLE goal; --"
            rpc('memoryd',{'cmd':'put_goal','text':goal});check('SQLite bound goal roundtrip',rpc('memoryd',{'cmd':'get_goal'})['data']['goal']==goal)
            rpc('memoryd',{'cmd':'delete_goal'});check('SQLite delete',rpc('memoryd',{'cmd':'get_goal'})['data']['goal']=='')
            rpc('dialogued',{'cmd':'decide','text':'hint requested'},ok=False);check('unconfigured provider is explicit error')
            rpc('picod',{'cmd':'status'},ok=False,deadline=int(time.monotonic()*1000)-1);check('expired IPC rejected')
            with socket.socket(socket.AF_UNIX) as s:
                s.settimeout(2);s.connect(str(root/'controllerd.control.sock'));s.sendall(struct.pack('!I',65537));check('oversize frame connection closed',s.recv(1)==b'')
            rpc('controllerd',{'cmd':'help'});time.sleep(1)
            rpc('controllerd',{'cmd':'help'},ok=False);check('active Help cannot silently replace an epoch')
            current=rpc('picod',{'cmd':'status'})['data'];epoch=current['epoch'];check('controller renew keeps lease live',current['lease_valid'])
            rpc('controllerd',{'cmd':'test','owner':0,'epoch':0,'module':'matrix'},ok=False);check('missing matrix blocked')
            with socket.socket(socket.AF_UNIX) as s:
                s.connect(str(root/'audiod.playback.sock'));stamp=int(time.monotonic()*1000);packet=b'PCM1'+struct.pack('!QQQII',epoch,1,stamp,48000,480)+bytes(960);send(s,packet)
            wait('PCM accepted',lambda:rpc('audiod',{'cmd':'status'})['data']['state'].get('pcm_accepted',0)>0);check('current epoch PCM reaches native playback queue')
            stopped=rpc('controllerd',{'cmd':'stop'});check('Stop waits for device flush',stopped['data']['audio']['device_flushed']);report['explicit_stop']=stopped
            with socket.socket(socket.AF_UNIX) as s:
                s.settimeout(2);s.connect(str(root/'audiod.playback.sock'));send(s,packet);check('stale PCM rejected after Stop',s.recv(1)==b'')
            rpc('controllerd',{'cmd':'help'});rpc('controllerd',{'cmd':'test','owner':0,'epoch':0,'module':'left'})
            running=wait('LED test active before controller death',lambda:(lambda x:x if x['data']['state']['telemetry'].get('status',{}).get('running') is not None else None)(rpc('picod',{'cmd':'status'})),3)
            report['pico_before_controller_death']=running
            old_epoch=rpc('picod',{'cmd':'status'})['data']['epoch'];t=time.monotonic();processes['controllerd'].kill();processes['controllerd'].wait()
            post=wait('controller death -> Stop',lambda:(lambda x:x if not x['data']['lease_valid'] and x['data']['state']['telemetry'].get('status',{}).get('oe_high') is True else None)(rpc('picod',{'cmd':'status'})),5)
            report['controller_death_observed_ms']=round((time.monotonic()-t)*1000);report['pico_after_controller_death']=post;check('controller death stops despite USB KeepAlive')
            start('controllerd');wait('new controller',lambda:rpc('controllerd',{'cmd':'status'})['generation']!=stopped['generation'])
            check('new controller starts quiet',rpc('controllerd',{'cmd':'status'})['data']['phase']=='quiet')
            check('old turn has not resumed',rpc('picod',{'cmd':'status'})['data']['epoch']==old_epoch and not rpc('picod',{'cmd':'status'})['data']['lease_valid'])
            report['passed']=True
        finally:
            for role in ['controllerd','audiod','picod','visiond','camerad','memoryd','dialogued']:
                proc=processes.get(role)
                if proc and proc.poll() is None:
                    proc.send_signal(signal.SIGINT)
                    try:proc.wait(timeout=8)
                    except subprocess.TimeoutExpired:proc.kill();proc.wait()
            report['process_returncodes']={r:p.poll() for r,p in processes.items()}
            # Bounded diagnostic text; never include captured PCM or images.
            report['logs']={r:(root/(r+'.log')).read_text(errors='replace')[-12000:] for r in processes}
            for log in logs.values():log.close()
            Path(a.output).write_text(json.dumps(report,ensure_ascii=False,indent=2))
            assert 'CRITICAL' not in report['logs']['audiod'],report['logs']['audiod']
    print(json.dumps({'passed':report.get('passed',False),'checks':len(report['checks'])}))
if __name__=='__main__':main()
