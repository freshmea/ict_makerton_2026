"""Independent STEP/STL checks, headless reimport, and native edit roundtrip.
Does not modify the four saved production hand designs.
"""
from pathlib import Path
import json, sys, math, subprocess, concurrent.futures
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[3]/'tmp/cad-runtime'))
import cadquery as cq
import trimesh
from mcp_client import Client, CLI
CAD=ROOT/'cad'
NAMES=[s+'_WRAP_HAND_'+h for s in ['L','R'] for h in ['FRONT','REAR']]
def dump(path,value):path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def bbox(s):
    b=s.BoundingBox();return {'min':[b.xmin,b.ymin,b.zmin],'max':[b.xmax,b.ymax,b.zmax],'size':[b.xlen,b.ylen,b.zlen]}
def healthy(d):
    return (not any(x.get('error') or x.get('warning') for x in d['timeline']) and all(s['dof']==0 for s in d['sketches']) and d.get('body_count',len(d['bodies']))==1 and all(x['kernel']['shells']==1 for x in d['bodies']))
def walk(name):
    cmds=[]
    cases=[('cap_d',89,92,90),('palm_l',78,82,80),('palm_h',40,44,42),('wall',3,3.6,3.2),('bolt_d',3.2,3.6,3.4),('dowel_d',3.8,4.2,4),('fit',.3,.5,.4)]
    states=[]
    for par,lo,hi,default in cases:
        for value in [lo,hi,default]:
            cmds.extend([{'command':'parameters.change','params':{'name':par,'expression':str(value)}},{'command':'document.inspect','params':{'measure':True}}])
            states.append({'parameter':par,'value':value})
    path=ROOT/(name+'_parameter_walk.json');dump(path,{'commands':cmds})
    out=CAD/(name+'_parameter_walk_results.json')
    if '--reuse-walks' not in sys.argv or not out.exists():
        p=subprocess.run([str(CLI),'run',str(path),'--in',str(CAD/(name+'.solidcraft')),'--results','--json-out',str(out)],capture_output=True,text=True,encoding='utf-8',timeout=240)
        assert p.returncode==0,(name,p.stderr)
    results=json.loads(out.read_text(encoding='utf-8'))
    docs=[x for x in results if isinstance(x,dict) and 'timeline' in x and 'bodies' in x]
    assert len(docs)==len(states),(len(docs),len(states))
    baseline=json.loads((CAD/(name+'_eval.json')).read_text(encoding='utf-8'))['bodies'][0]['volume_mm3']
    for state,d in zip(states,docs):
        assert healthy(d),(name,state,'unhealthy')
        state.update(volume_mm3=d['bodies'][0]['volume_mm3'],bbox=d['bodies'][0]['bbox'],clean=True)
        if state['parameter']=='bolt_d':
            # Two holes each cross a 29 mm bridge half. The cap is clear.
            expected=baseline-2*math.pi/4*(state['value']**2-3.4**2)*29
            state['analytic_expected_volume_mm3']=expected
            state['analytic_gap_mm3']=state['volume_mm3']-expected
            assert abs(state['analytic_gap_mm3'])<.1,(name,state)
        if state['value']==next(x[3] for x in cases if x[0]==state['parameter']):
            assert abs(state['volume_mm3']-baseline)<.1,(name,state,'failed roundtrip')
    return name,states

def main():
    report={'units':'mm','separate_headless_cli':str(CLI),'parts':{},'static_interference':[]}
    assembly=cq.importers.importStep(str(ROOT.parents[1]/'mechanical_v7/cad/fold_wing_v7_P1_assembly.step')).val()
    originals=assembly.Solids()
    cores={}
    for side in ['L','R']:
        for half in ['FRONT','REAR']:
            name=side+'_CURVED_ARM_CORE_'+half
            local=cq.importers.importStep(str(ROOT.parents[1]/('mechanical_v7/cad/'+name+'.step'))).val()
            b=local.BoundingBox()
            matches=[s for s in originals if abs(s.Volume()-local.Volume())<.1 and all(abs(a-v)<.001 for a,v in zip(bbox(s)['size'],[b.xlen,b.ylen,b.zlen])) and ((s.Center().x<0)==(side=='L'))]
            assert len(matches)==1,(name,len(matches))
            cores[name]=matches[0]
    for name in NAMES:
        s=cq.importers.importStep(str(CAD/(name+'.step'))).val()
        mesh=trimesh.load_mesh(str(CAD/(name+'.stl')))
        ev=json.loads((CAD/(name+'_eval.json')).read_text(encoding='utf-8'))
        assert s.isValid() and len(s.Solids())==1 and len(s.Shells())==1 and all(sh.Closed() for sh in s.Shells()),name
        assert mesh.is_watertight and mesh.is_volume,name
        assert healthy(ev),name
        prior=cq.importers.importStep(str(ROOT.parents[1]/('mechanical_v7/cad/'+name+'.step'))).val()
        report['parts'][name]={'step_valid':s.isValid(),'step_solids':len(s.Solids()),'step_shells':len(s.Shells()),'shells_closed':[sh.Closed() for sh in s.Shells()],'stl_watertight':bool(mesh.is_watertight),'stl_volume':bool(mesh.is_volume),'volume_mm3':s.Volume(),'bbox':bbox(s),'v7_default_volume_mm3':prior.Volume(),'volume_change_from_v7_default_mm3':s.Volume()-prior.Volume(),'timeline_count':len(ev['timeline']),'all_sketch_dof_zero':True,'timeline_errors_warnings':[]}
        for cname,core in cores.items():
            if not cname.startswith(name[0]):continue
            overlap=s.intersect(core).Volume()
            report['static_interference'].append({'a':name,'b':cname,'intersection_mm3':overlap})
            assert overlap<1e-5,(name,cname,overlap)
    for side in ['L','R']:
        front=cq.importers.importStep(str(CAD/(side+'_WRAP_HAND_FRONT.step'))).val()
        rear=cq.importers.importStep(str(CAD/(side+'_WRAP_HAND_REAR.step'))).val()
        overlap=front.intersect(rear).Volume()
        report['static_interference'].append({'a':side+'_WRAP_HAND_FRONT','b':side+'_WRAP_HAND_REAR','intersection_mm3':overlap})
        assert overlap<1e-5
    # Fresh MCP process: STEP open must report no open-body warning.
    client=Client(headless=True)
    try:
        report['initial_headless_design']=Client.value(client.call('inspect_design',{'measure':False,'sketches':False}))
        for name in NAMES:
            opened=Client.value(client.call('open',{'path':str((CAD/(name+'.step')).resolve())}))
            report['parts'][name]['solidcraft_step_reimport']=opened
            assert not opened.get('warnings') and not opened.get('errors'),(name,opened)
    finally:client.close()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for name,states in pool.map(walk,NAMES):
            report['parts'][name]['parameter_walk']=states
    report['accepted']=True
    report['limitations']=['New native palm is an intentional capsule-extrusion redesign, not an equivalent STEP repair.','v7 volume comparison uses CadQuery default integration because reference transformed ellipsoids show integration differences; geometry and topology are intentionally changed.','Static assembly pose only; no servo motion, load, print, physical fit or fastener purchase validation.']
    dump(ROOT/'hands_native_verification.json',report)
    print('PASS: four native one-solid closed hands; STEP reopen clean; zero static core intersection; 84 clean parameter states.')

if __name__=='__main__':main()
