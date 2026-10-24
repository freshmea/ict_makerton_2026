#!/usr/bin/env python3
"""Real bounded speaker->room->mic AEC comparison. Synthetic chirp, no cloud.
Stop all other audio owners before running. Records metrics, not raw audio.
"""
import argparse,json,math,os,signal,socket,struct,subprocess,tempfile,threading,time
from pathlib import Path
import numpy as np
from verify_runtime import exact,recv,send
def run(binary,enabled):
    with tempfile.TemporaryDirectory(prefix='acoustics-') as tmp:
        root=Path(tmp);log=open(root/'audio.log','wb');env=os.environ.copy();env.update(NANO_RUN=tmp,NANO_AEC=str(int(enabled)))
        p=subprocess.Popen([str(binary),'serve','audiod'],env=env,stdout=log,stderr=log)
        halt=threading.Event();errors=[];capture=[]
        def rpc(cmd):
            with socket.socket(socket.AF_UNIX) as s:
                s.settimeout(3);s.connect(str(root/'audiod.control.sock'));q={'v':1,'id':time.monotonic_ns(),'deadline_ms':int(time.monotonic()*1000)+2000,'body':cmd};send(s,json.dumps(q).encode());r=json.loads(recv(s));assert r['ok'],r;return r['data']
        def renew():
            while not halt.wait(.1):
                try:rpc({'cmd':'renew','owner':7,'epoch':1})
                except Exception as e:errors.append(str(e));return
        def collect():
            try:
                with socket.socket(socket.AF_UNIX) as s:
                    s.settimeout(2);s.connect(str(root/'audiod.capture.sock'))
                    while not halt.is_set():
                        packet=recv(s);capture.append((time.monotonic(),np.frombuffer(packet[36:],dtype='<i2').astype(np.float64)))
            except Exception as e:
                if not halt.is_set():errors.append(str(e))
        try:
            end=time.monotonic()+12
            while time.monotonic()<end:
                try:
                    if rpc({'cmd':'status'})['fresh']:break
                except (OSError,AssertionError):pass
                time.sleep(.1)
            else:raise TimeoutError('audio unavailable')
            rpc({'cmd':'acquire','owner':7,'epoch':1});rt=threading.Thread(target=renew);ct=threading.Thread(target=collect);rt.start();ct.start();time.sleep(1)
            start=time.monotonic();phase=0
            with socket.socket(socket.AF_UNIX) as s:
                s.settimeout(2);s.connect(str(root/'audiod.playback.sock'))
                for i in range(800):
                    due=start+i*.01;time.sleep(max(0,due-time.monotonic()));freq=500+((i//10)%15)*50
                    x=np.arange(480);pcm=(np.sin(phase+2*np.pi*freq*x/48000)*12000).astype('<i2').tobytes();phase=(phase+2*np.pi*freq*480/48000)%(2*np.pi)
                    packet=b'PCM1'+struct.pack('!QQQII',1,i+1,int(time.monotonic()*1000),48000,480)+pcm;send(s,packet)
                    assert struct.unpack('!Q',exact(s,8))[0]==i+1
            time.sleep(.15);state=rpc({'cmd':'status'});halt.set();rt.join(2);rpc({'cmd':'stop'});ct.join(3)
            baseline=np.concatenate([x for t,x in capture if t<start-.1]);late=np.concatenate([x for t,x in capture if start+5<t<start+7.8]);rms=lambda x:float(np.sqrt(np.mean(x*x)))
            return {'aec':enabled,'noise_rms':rms(baseline),'late_playback_residual_rms':rms(late),'capture_samples':sum(len(x) for _,x in capture),'state':state,'errors':errors}
        finally:
            halt.set();p.send_signal(signal.SIGINT)
            try:p.wait(8)
            except subprocess.TimeoutExpired:p.kill();p.wait()
            log.close()
def main():
    a=argparse.ArgumentParser();a.add_argument('--output',required=True);args=a.parse_args();binary=Path(__file__).resolve().parents[1]/'target/release/nano-runtime'
    off=run(binary,False);on=run(binary,True)
    attenuation=20*math.log10(max(off['late_playback_residual_rms'],1e-9)/max(on['late_playback_residual_rms'],1e-9))
    sufficient=off['late_playback_residual_rms']>=2*off['noise_rms']
    result={'real_acoustic_path':True,'cloud_calls':0,'off':off,'on':on,'observed_attenuation_db':attenuation,'sufficient_excitation':sufficient,'candidate_threshold_db':6,'candidate_pass':sufficient and attenuation>=6 and not off['errors'] and not on['errors'],'human_double_talk_verified':False,'repetitions':1,'raw_audio_saved':False}
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
