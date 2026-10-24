#!/usr/bin/env python3
"""Operator CLI. Run as boarddash for the same-UID Unix control boundary."""
import argparse,json,os,socket,struct,time,sys
from pathlib import Path
def rpc(role,body,wait=4):
    root=Path(os.environ.get('NANO_RUN','/run/300seconds'))
    request={'v':1,'id':time.monotonic_ns(),'deadline_ms':int(time.monotonic()*1000)+2000,'body':body}
    def exact(s,n):
        data=b''
        while len(data)<n:
            chunk=s.recv(n-len(data))
            if not chunk:raise EOFError('runtime closed request')
            data+=chunk
        return data
    with socket.socket(socket.AF_UNIX) as s:
        s.settimeout(wait);s.connect(str(root/(role+('.stop.sock' if body['cmd']=='stop' else '.control.sock'))))
        data=json.dumps(request,ensure_ascii=False).encode('utf8');s.sendall(struct.pack('!I',len(data))+data)
        size=struct.unpack('!I',exact(s,4))[0]
        if not 0<size<=65536:raise ValueError('response size invalid')
        result=json.loads(exact(s,size))
    if result['id']!=request['id'] or not result['ok']:raise RuntimeError(result.get('data'))
    return result['data']
def main():
    p=argparse.ArgumentParser(description='300 Seconds quiet study companion')
    p.add_argument('action',choices=['status','stop','finish','arm','help','listen','result','correct','goal','get-goal','delete-goal','memory','usage','ocr','confirm-problem','light','pose'])
    p.add_argument('text',nargs='?',default='');p.add_argument('--speak',action='store_true');p.add_argument('--cloud-consent',action='store_true')
    p.add_argument('--audio-cloud-consent',action='store_true',help='upload only this requested utterance to Gemini; never continuous audio')
    p.add_argument('--role',default='controllerd');p.add_argument('--camera',type=int,default=0);p.add_argument('--roi',type=int,nargs=4,default=[0,0,1280,720]);p.add_argument('--rotation',type=int,default=0);p.add_argument('--no-wait',action='store_true')
    a=p.parse_args();role=a.role
    if a.action in ('help','listen','correct'):
        body={'cmd':'correct' if a.action=='correct' else 'start_turn','text':a.text or None,'cloud_consent':a.cloud_consent,'speak':a.speak}
        if a.action!='correct':body['listen']=a.action=='listen';body['audio_cloud_consent']=a.audio_cloud_consent
        if a.action=='correct' and not a.text:raise ValueError('correction text required')
    elif a.action=='goal':role='memoryd';body={'cmd':'put_goal','text':a.text}
    elif a.action in ('get-goal','delete-goal'):role='memoryd';body={'cmd':a.action.replace('-','_')}
    elif a.action=='memory':role='memoryd';body={'cmd':'memory','request':json.loads(a.text)}
    elif a.action=='usage':role='dialogued';body={'cmd':'usage'}
    elif a.action=='ocr':role='visiond';body={'cmd':'ocr','camera':a.camera,'roi':a.roi,'rotation':a.rotation}
    elif a.action=='confirm-problem':body={'cmd':'confirm_problem','text':a.text}
    elif a.action=='light':body={'cmd':'light','rgb':[255,225,180],'brightness':16,'period_ms':0}
    elif a.action=='pose':body={'cmd':'pose','targets_cdeg':json.loads(a.text),'move_ms':1000}
    else:body={'cmd':'turn_result' if a.action=='result' else 'help' if a.action=='arm' else a.action}
    result=rpc(role,body)
    if result.get('started') and not a.no_wait:
        end=time.monotonic()+90
        while time.monotonic()<end:
            time.sleep(.2);result=rpc(role,{'cmd':'turn_result'})
            if result.get('phase') in ('done','failed','cancelled'):break
        else:raise TimeoutError('job still running; inspect result/stop')
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:
        try:rpc('controllerd',{'cmd':'stop'})
        finally:sys.exit(130)
    except Exception as e:print(str(e),file=sys.stderr);sys.exit(1)
