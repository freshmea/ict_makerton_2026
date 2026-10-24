#!/usr/bin/env python3
"""Installed systemd verification. No cloud generation and no servo commands."""
import argparse,json,subprocess,time,os,threading,datetime
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);args=parser.parse_args()
B='/opt/300seconds/runtime/nano-runtime'
U='300seconds-runtime@{}.service'
R=Path('/run/300seconds')
report={'passed':False,'cloud_generation_calls':0,'checks':[],'raw_images_saved_to_repo':False}
report['started_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
report['boot_id']=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
started=time.time()
power=[];power_stop=threading.Event()

def sample_power():
 rail=Path('/sys/bus/i2c/drivers/ina3221x/6-0040/iio:device0/in_voltage0_input')
 while not power_stop.is_set():
  try:power.append({'elapsed_seconds':round(time.time()-started,2),'input_mv':int(rail.read_text())})
  except (OSError,ValueError):pass
  power_stop.wait(.2)

def checkpoint():
 p=Path(args.output);p.parent.mkdir(parents=True,exist_ok=True)
 temp=p.with_suffix(p.suffix+'.tmp');temp.write_text(json.dumps(report,ensure_ascii=False,indent=2));temp.replace(p)
def ctl(cmd,*args):return subprocess.check_output(['systemctl',cmd,*args],text=True)
def rpc(role,q):
 p=subprocess.run(['sudo','-n','-u','boarddash',B,'ctl',role,json.dumps(q)],text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=6)
 if p.returncode:raise RuntimeError(role+': '+p.stderr.strip()[:1200])
 return json.loads(p.stdout)
def wait(fn,n=90):
 end=time.monotonic()+n
 while time.monotonic()<end:
  try:
   r=fn()
   if r:return r
  except (OSError,ValueError,subprocess.SubprocessError,KeyError,RuntimeError):pass
  time.sleep(.2)
 raise AssertionError('condition timed out')
def check(name,ok=True):
 assert ok,name
 report['checks'].append(name);print(name,flush=True)
 checkpoint()
def camera():return rpc('camerad',{'cmd':'status'})
def vision():return rpc('visiond',{'cmd':'status'})
def read_ready():
 c=camera();v=vision()
 if c['fresh'] and v['fresh'] and len(v['state'].get('cameras',[]))==2 and all(x.get('observation_age_ms',99999)<1500 for x in v['state']['cameras']) and all(rpc(r,{'cmd':'status'})['fresh'] for r in ['picod','audiod']):return c,v
roles=['picod','audiod','camerad','visiond','memoryd','dialogued','controllerd']
sampler=threading.Thread(target=sample_power,daemon=True);sampler.start()
try:
 ctl('start','300seconds-runtime.target');c,v=wait(read_ready,120);check('all seven installed units active',all(ctl('is-active',U.format(r)).strip()=='active' for r in roles))
 report['model_load_ms']=v['state'].get('model_load_ms');report['initial_vision']=v
 a=camera();t=time.monotonic();time.sleep(10);b=camera();duration=time.monotonic()-t
 report['camera_rates']=[{'camera':i,'source_fps':(b['state']['cameras'][i]['source_frame_id']-a['state']['cameras'][i]['source_frame_id'])/duration,'analysis_fps':(b['state']['cameras'][i]['frame_id']-a['state']['cameras'][i]['frame_id'])/duration,'sensor_mode':b['state']['cameras'][i]['sensor_mode']} for i in range(2)]
 check('both cameras actual sensor ~30fps and analysis ~10fps',all(27<x['source_fps']<33 and 8<x['analysis_fps']<12 for x in report['camera_rates']))
 for i in range(2):
  snap=rpc('camerad',{'cmd':'snapshot','camera':i})
  # The host Python imports an incompatible global NumPy/OpenCV build. Use
  # the same isolated interpreter and thread limits as the actual OCR worker.
  environment=dict(os.environ,OPENBLAS_CORETYPE='ARMV8',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
  dimensions=json.loads(subprocess.check_output(['/opt/300seconds/ai/venv/bin/python','-c','import cv2,json,sys; im=cv2.imread(sys.argv[1]); print(json.dumps(None if im is None else list(im.shape[:2])))',snap['path']],env=environment,text=True,timeout=20))
  check('camera '+str(i)+' requested JPEG is 1280x720',dimensions==[720,1280])
 # Use an explicit problem crop. A full room/background is not a textbook and
 # can exhaust Tesseract's bounded deadline without providing useful text.
 rpc('visiond',{'cmd':'ocr','camera':1,'roi':[480,270,320,180],'rotation':0})
 o=wait(lambda:(lambda x:x if x.get('phase') in ['done','failed'] else None)(rpc('visiond',{'cmd':'turn_result'})),35)
 report['actual_scene_ocr']={'phase':o['phase'],'error':o.get('error'),'quality':o.get('result',{}).get('quality'),'confidence':o.get('result',{}).get('confidence'),'candidate_characters':len(o.get('result',{}).get('text','')),'confirmed':False}
 check('actual CSI problem crop reaches OCR adapter as unconfirmed candidate',o['phase']=='done' and not o.get('result',{}).get('confirmed',True))
 old=camera()['generation'];ctl('stop',U.format('camerad'));s=wait(lambda:(lambda x:x if not x['fresh'] else None)(vision()),10);check('camera owner loss reports unknown',s['state'].get('presence')=='unknown')
 ctl('start',U.format('camerad'));c,v=wait(read_ready,60);check('camera restart uses new frame generation',c['generation']!=old and all(x['generation']==c['generation'] for x in v['state']['cameras']))
 rpc('controllerd',{'cmd':'help'});rpc('controllerd',{'cmd':'light','rgb':[40,60,20],'brightness':8,'period_ms':0});ctl('kill','--signal=SIGKILL',U.format('picod'))
 wait(lambda:rpc('controllerd',{'cmd':'status'})['phase']=='fault',8);check('picod kill revokes controller and audio',not rpc('audiod',{'cmd':'status'})['lease_valid'])
 ctl('reset-failed',U.format('picod'));ctl('start',U.format('picod'));p=wait(lambda:(lambda x:x if x['fresh'] else None)(rpc('picod',{'cmd':'status'})),35)
 check('Pico manually recovers stopped and gated',p['state']['telemetry']['status']['oe_high'] and not p['state']['telemetry']['outputs']['armed'])
 rpc('controllerd',{'cmd':'help'});rpc('controllerd',{'cmd':'stop'});check('fresh Help works after manual Pico recovery')
 rpc('controllerd',{'cmd':'help'});ctl('kill','--signal=SIGKILL',U.format('audiod'));wait(lambda:rpc('controllerd',{'cmd':'status'})['phase']=='fault',8)
 p=wait(lambda:(lambda x:x if x['state']['telemetry']['status']['oe_high'] else None)(rpc('picod',{'cmd':'status'})),5);check('audio owner kill stops Pico outputs')
 ctl('reset-failed',U.format('audiod'));ctl('start',U.format('audiod'));wait(lambda:rpc('audiod',{'cmd':'status'})['fresh'],35)
 rpc('controllerd',{'cmd':'help'});rpc('controllerd',{'cmd':'stop'});check('audio manually recovers without replay')
 report['soak']=[];ticks=os.sysconf('SC_CLK_TCK');previous={};last=time.monotonic()
 for n in range(19):
  now=time.monotonic();sample={'elapsed_seconds':n*10,'processes':{}}
  for role in roles:
   pid=int(ctl('show','-p','MainPID','--value',U.format(role)).strip());data=Path('/proc/'+str(pid)+'/stat').read_text().split();cpu=int(data[13])+int(data[14]);rss=int(data[23])*os.sysconf('SC_PAGE_SIZE')
   sample['processes'][role]={'pid':pid,'rss_bytes':rss,'cpu_percent':None if role not in previous else (cpu-previous[role])/ticks/(now-last)*100};previous[role]=cpu
  sample['available_memory_kib']=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))
  sample['temperature_mC']=max(int(p.read_text()) for p in Path('/sys/class/thermal').glob('thermal_zone*/temp'))
  sample['camera_fresh']=camera()['fresh'];sample['vision_fresh']=vision()['fresh'];report['soak'].append(sample);assert sample['camera_fresh'] and sample['vision_fresh'];last=now
  if n<18:time.sleep(10)
 check('three minute quiet soak has stable PIDs and fresh media',all(len({x['processes'][r]['pid'] for x in report['soak']})==1 for r in roles))
 check('controller remains quiet after verification',rpc('controllerd',{'cmd':'status'})['phase']=='stopped')
 report['passed']=True
except Exception as e:
 report['error']=type(e).__name__+': '+str(e)
 raise
finally:
 ctl('stop','300seconds-runtime.target',*[U.format(x) for x in roles])
 power_stop.set();sampler.join(timeout=2)
 report['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
 report['power_samples']=power
 if power:
  volts=[x['input_mv'] for x in power]
  report['power_summary']={'samples':len(volts),'min_mv':min(volts),'max_mv':max(volts),'mean_mv':sum(volts)/len(volts)}
 kernel=subprocess.check_output(['journalctl','-k','-b','--since','@'+str(int(started)),'--no-pager','-o','cat'],text=True)
 report['kernel_oc_alarms_during_test']=kernel.count('OC ALARM')
 report['kernel_oom_during_test']='Out of memory' in kernel or 'Killed process' in kernel
 report['power_stability_verified']=report['kernel_oc_alarms_during_test']==0 and not report['kernel_oom_during_test'] and bool(power)
 checkpoint()
print(json.dumps({'passed':report.get('passed',False),'checks':len(report['checks'])}))
