import subprocess,json,queue,threading,pathlib,time
out=pathlib.Path('doc/BOM/mechanical_v6/reference/solidcraft');out.mkdir(exist_ok=True)
exe='C:/Users/Administrator/Downloads/solidcraft-cli.exe'
source=str(pathlib.Path('doc/BOM/mechanical_v6/reference/SpotMicro_parts/STEP_Files/I_shoulder_cls_modi.stp').resolve())
p=subprocess.Popen([exe,'mcp','--in',source,'--allow-path',str(pathlib.Path('doc/BOM/mechanical_v6').resolve())],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,encoding='utf-8')
q=queue.Queue();err=[]
def reader():
 for line in p.stdout:q.put(line)
threading.Thread(target=reader,daemon=True).start()
def errreader():
 for line in p.stderr:err.append(line.strip())
threading.Thread(target=errreader,daemon=True).start()
def req(i,method,params):
 p.stdin.write(json.dumps({'jsonrpc':'2.0','id':i,'method':method,'params':params})+'\n');p.stdin.flush();deadline=time.time()+90
 while time.time()<deadline:
  try:line=q.get(timeout=1)
  except queue.Empty:continue
  try:r=json.loads(line)
  except:continue
  if r.get('id')==i:return r
 raise TimeoutError(method)
a=req(1,'initialize',{'protocolVersion':'2024-11-05','capabilities':{},'clientInfo':{'name':'Codex-reference-analysis','version':'1'}});(out/'mcp_initialize.json').write_text(json.dumps(a,indent=2),encoding='utf-8')
p.stdin.write(json.dumps({'jsonrpc':'2.0','method':'notifications/initialized'})+'\n');p.stdin.flush()
b=req(2,'tools/list',{});(out/'mcp_tools.json').write_text(json.dumps(b,indent=2),encoding='utf-8')
print('INITIALIZE',a);print('TOOLS',[(x['name'],x.get('description','')[:80])for x in b.get('result',{}).get('tools',[])])
c=req(3,'tools/call',{'name':'inspect_design','arguments':{'measure':True,'sketches':False}});(out/'initial_design_inspection.json').write_text(json.dumps(c,indent=2),encoding='utf-8');print('INSPECT',json.dumps(c,ensure_ascii=False)[:14000]);p.terminate();(out/'mcp_stderr.txt').write_text('\n'.join(err),encoding='utf-8')
