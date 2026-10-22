"""Analyze preserved original files through SolidCraft MCPstdio without touching the running app."""
import subprocess,json,queue,threading,pathlib,time
HERE=pathlib.Path(__file__).resolve().parent;OUT=HERE/'solidcraft';OUT.mkdir(exist_ok=True);PARTS=HERE/'SpotMicro_parts';EXE='C:/Users/Administrator/Downloads/solidcraft-cli.exe'
p=subprocess.Popen([EXE,'mcp','--allow-path',str(HERE.resolve())],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8');q=queue.Queue();err=[];counter=0
threading.Thread(target=lambda:[q.put(l)for l in p.stdout],daemon=True).start();threading.Thread(target=lambda:[err.append(l.strip())for l in p.stderr],daemon=True).start()
def req(method,params):
 global counter
 counter+=1;i=counter;p.stdin.write(json.dumps({'jsonrpc':'2.0','id':i,'method':method,'params':params})+'\n');p.stdin.flush();end=time.time()+60
 while time.time()<end:
  try:r=json.loads(q.get(timeout=1))
  except queue.Empty:continue
  except ValueError:continue
  if r.get('id')==i:return r
 raise TimeoutError(method)
def call(name,args):return req('tools/call',{'name':name,'arguments':args})
def parsed(r):
 if 'error'in r:return {'error':r['error']}
 for c in r.get('result',{}).get('content',[]):
  if c.get('type')=='text':
   try:return json.loads(c['text'])
   except:return {'text':c['text']}
 return {}
def save(name,r):
 # Never retain base64screenshot payloads; images are saved by MCP to explicitpath.
 if isinstance(r,dict):
  for c in r.get('result',{}).get('content',[]):
   if c.get('type')=='image' and 'data'in c:c['data']='[image bytes omitted; saved to requested PNG]'
 (OUT/name).write_text(json.dumps(r,indent=2,ensure_ascii=False),encoding='utf-8')
init=req('initialize',{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'Codex-SpotMicro-reference','version':'1'}});p.stdin.write(json.dumps({'jsonrpc':'2.0','method':'notifications/initialized'})+'\n');p.stdin.flush();save('mcp_initialize.json',init)
summary=[]
for rel in ['STEP_Files/I_shoulder_cls_modi.stp','STEP_Files/O_shoulder_cls_grooved_modi.stp','STL/files/L_arm_cover.stl']:
 src=PARTS/rel;stem=src.stem;r=call('open',{'path':str(src.resolve())});save(stem+'_open.json',r)
 r=call('inspect_design',{'measure':True,'sketches':False});save(stem+'_inspect.json',r);j=parsed(r)
 m=call('measure',{});save(stem+'_measure.json',m)
 row={'file':rel,'backend':'headless in-process SolidCraft MCP','inspect':j,'measure':parsed(m)}
 for body in j.get('bodies',[]):
  topo=call('body_topology',{'body':body['name']});save(stem+'_topology.json',topo);top=parsed(topo);row['topology_keys']=list(top.keys());
  pts=[]
  for e in top.get('edges',[]):
   for k in ['start','end','midpoint']:
    if isinstance(e.get(k),list)and len(e[k])==3:pts.append(e[k])
  if pts:row['edge_sample_bounds']={'min':[min(v[k]for v in pts)for k in range(3)],'max':[max(v[k]for v in pts)for k in range(3)]}
 r=call('screenshot',{'source':'model','view':'iso','width':1000,'height':760,'grid':False,'axes':False,'path':str((OUT/(stem+'_iso.png')).resolve())});save(stem+'_screenshot_result.json',r)
 r=call('save',{'path':str((OUT/(stem+'.solidcraft')).resolve())});save(stem+'_save.json',r)
 summary.append(row);print(stem,'bodies',[(b.get('name'),b.get('bbox'))for b in j.get('bodies',[])],'error',r.get('error'))
(OUT/'analysis_summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8');p.terminate();(OUT/'mcp_stderr.txt').write_text('\n'.join(err),encoding='utf-8');print('DONE')
