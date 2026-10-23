"""Import P1 assembly through separate headless SolidCraft MCP, never GUI app."""
import subprocess,json,queue,threading,pathlib,time
HERE=pathlib.Path(__file__).resolve().parent;ROOT=HERE.parent;OUT=HERE/'solidcraft';OUT.mkdir(exist_ok=True)
EXE='C:/Users/Administrator/Downloads/solidcraft-cli.exe'
p=subprocess.Popen([EXE,'mcp','--allow-path',str(ROOT.resolve())],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8')
q=queue.Queue();err=[];counter=0
threading.Thread(target=lambda:[q.put(l)for l in p.stdout],daemon=True).start()
threading.Thread(target=lambda:[err.append(l.strip())for l in p.stderr],daemon=True).start()
def req(method,params):
    global counter
    counter+=1;i=counter;p.stdin.write(json.dumps({'jsonrpc':'2.0','id':i,'method':method,'params':params})+'\n');p.stdin.flush();end=time.time()+55
    while time.time()<end:
        try:r=json.loads(q.get(timeout=1))
        except (queue.Empty,ValueError):continue
        if r.get('id')==i:return r
    raise TimeoutError(method)
def call(name,args):return req('tools/call',{'name':name,'arguments':args})
def save(name,r):
    for b in r.get('result',{}).get('content',[]):
        if b.get('type')=='image' and 'data' in b:b['data']='[omitted; written by MCP to local PNG]'
    (OUT/name).write_text(json.dumps(r,indent=2,ensure_ascii=False),encoding='utf-8')
try:
    r=req('initialize',{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'Codex-FWB-P1-analysis','version':'1'}});save('mcp_initialize.json',r)
    p.stdin.write(json.dumps({'jsonrpc':'2.0','method':'notifications/initialized'})+'\n');p.stdin.flush()
    for name,args,dest in [
        ('open',{'path':str((ROOT/'cad/fold_wing_v7_P1_assembly.step').resolve())},'P1_open.json'),
        ('inspect_design',{'measure':True,'sketches':False},'P1_inspect.json'),
        ('save',{'path':str((OUT/'fold_wing_v7_P1_assembly.solidcraft').resolve())},'P1_save.json'),
        ('screenshot',{'source':'model','view':'iso','width':1200,'height':850,'grid':False,'axes':False,'path':str((OUT/'P1_assembly_iso.png').resolve())},'P1_screenshot_result.json')]:
        t=time.time();r=call(name,args);save(dest,r)
        print(name,'seconds',round(time.time()-t,2),'error',r.get('error'),flush=True)
finally:
    p.terminate();(OUT/'mcp_stderr.txt').write_text('\n'.join(err),encoding='utf-8')
