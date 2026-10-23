"""Six real revolute joints, three serial stages per arm, on native P4 geometry.

Uses the official SolidCraft 0.20.0 MCP in an isolated headless process.
P2/P3 and the desktop user's unsaved work are never modified.
"""
from pathlib import Path
import argparse, hashlib, json, math
from mcp_client import Client
from build_motion_P3 import rotate

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'source/P4_files'
OUT.mkdir(exist_ok=True)
INPUT=ROOT/'cad/fold_wing_v8_P4_geometry.solidcraft'
MODEL=ROOT/'cad/fold_wing_v8_P4_6servo.solidcraft'

def dump(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--build-only',action='store_true',help='Save/reopen QA is run separately; omit repeated analytic drive loop')
    args=parser.parse_args()
    c=Client(headless=True,timeout=240)
    original=hashlib.sha256(INPUT.read_bytes()).hexdigest()
    try:
        c.call('inspect_design',{'measure':False,'sketches':False})
        c.call('open',{'path':str(INPUT)})
        def ex(cmd,**params):return c.value(c.call('execute',{'command':cmd,'params':params}))
        # The first geometry checkpoint had two intentionally static cross
        # profiles. Freeze their exact trial coordinates without moving them.
        # This is also in the geometry generator for future clean rebuilds.
        fixes=[]
        profiles={s['name']:s for s in c.value(c.call('inspect_design',{'measure':False,'sketches':True})).get('sketches',[])}
        for side in ['L','R']:
            if profiles[side+'_ShoulderCrossProfile'].get('dof',0)==0:
                continue
            fixes.append(ex('sketch.edit',sketch=side+'_ShoulderCrossProfile'))
            fixes.append(ex('sketch.constraint.fix',entities=['l'+str(i) for i in range(1,13)],fixed=True))
            fixes.append(ex('sketch.solve'))
            fixes.append(ex('sketch.finish'))
        dump('cross_profile_constraints.json',fixes)
        initial=c.value(c.call('inspect_design',{'measure':True,'sketches':False}))
        dump('geometry_inspect.json',initial)
        comps=ex('component.list',compact=False)
        dump('initial_components.json',comps)
        dump('checkpoint.json',ex('edit.checkpoint'))
        groups=json.loads((ROOT/'source/geometry_P4_groups.json').read_text(encoding='utf-8'))
        names={b['name'] for b in initial['bodies']}
        servo_names=sorted(n for n in names if 'SERVO' in n and 'SHAFT' not in n)
        assert len(servo_names)==6,servo_names
        dump('servo_inventory.json',servo_names)
        def command(cmd,**params):return {'command':cmd,'params':params}
        cmds=[command('component.unlock',component=1)]
        moving=set()
        for side in ['L','R']:
            for stage in ['yaw_carrier','arm','hand']:
                bodies=groups[side+'_'+stage]
                assert bodies and set(bodies)<=names,(side,stage,set(bodies)-names)
                assert not moving.intersection(bodies)
                moving.update(bodies)
                name='P4_'+side+'_'+stage.upper()
                cmds += [command('component.create',name=name,parent='root',activate=False),
                         command('component.move_bodies',bodies=bodies,component=name)]
        dump('group_mapping.json',groups)
        dump('component_batch.json',c.value(c.call('batch',{'commands':cmds,'verbose':False})))
        comps=ex('component.list',compact=False)
        base=next(x for x in comps['components'] if x['id']==1)['occurrences'][0]
        fixed=sorted({o['id'] for x in comps['components'] if x.get('bodies') and not x['name'].startswith('P4_') for o in x['occurrences']})
        cmds=[command('occurrence.ground',occurrence=base['id'],grounded=True)]
        cmds += [command('joint.rigid_group',occurrences=[base['id']]+[x for x in fixed if x!=base['id']])]
        specs=[]
        for side,sgn in [('L',-1),('R',1)]:
            occ=['P4_'+side+'_'+stage+':1' for stage in ['YAW_CARRIER','ARM','HAND']]
            for suffix,a,b,point,axis in [
                ('J1_YAW',base['name'],occ[0],[sgn*275,40,130],[0,0,1]),
                ('J2_SHOULDER_PITCH',occ[0],occ[1],[sgn*275,40,180],[0,1,0]),
                ('J3_WRIST_PITCH',occ[1],occ[2],[sgn*220,40,315],[0,1,0])]:
                spec=dict(name=side+'_'+suffix,type='revolute',a=a,b=b,at={'occurrence':a,'point':point,'z':axis},limits=[[-15,15]])
                specs.append(spec);cmds.append(command('joint.as_built',**spec))
        keys=[]
        for i,s in enumerate(specs):
            start=i*20
            points=[[0,0]]+([[start,0]] if start else [])+[[start+5,10],[start+10,-10],[start+15,0],[120,0]]
            keys.append({'joint':s['name'],'points':points})
        cmds.append(command('motion.study',name='P4_SIX_JOINT_DEMO',steps=120,keys=keys))
        for s in specs:
            cmds.append(command('motion.study',name=s['name']+'_DEMO',steps=20,keys=[{'joint':s['name'],'points':[[0,0],[5,10],[10,-10],[15,0],[20,0]]}]))
        cmds.append(command('document.metadata.set',values={'project':'Fold Wing Buddy v8 P4 - six servos', 'revision':'P4', 'description':'Six CLS6336HV servo envelopes, three serial revolute joints per arm: yaw, shoulder pitch, wrist pitch. Native added shoulder housing and carrier. Neutral save; +/-15 degree provisional CAD limits only.'}))
        (ROOT/'source/motion_P4.json').write_text(json.dumps({'commands':cmds},indent=2)+'\n',encoding='utf-8')
        dump('joint_specs.json',specs)
        dump('motion_build_batch.json',c.value(c.call('batch',{'commands':cmds,'verbose':False})))
        joints=ex('joint.list')
        assert sum(j['type']=='revolute' for j in joints['joints'])==6
        assert not joints['errors'] and not joints['conflicts'] and not joints['floating'],joints
        ex('browser.visibility',joints=[j['id'] for j in joints['joints']],visible=False)
        ex('browser.visibility',joints=[s['name'] for s in specs],visible=True)
        baseline={n:ex('occurrence.properties',occurrence=n) for n in ['P4_'+s+'_'+g+':1' for s in ['L','R'] for g in ['YAW_CARRIER','ARM','HAND']]}
        dump('baseline_properties.json',baseline)
        if args.build_only:
            dump('final_joints.json',ex('joint.list'))
            dump('motion_studies.json',ex('motion.list'))
            final=c.value(c.call('inspect_design',{'measure':True,'sketches':True}))
            dump('final_inspect.json',final)
            assert not [t for t in final['timeline'] if t.get('error') or t.get('warning')]
            assert all(s.get('dof',0)==0 for s in final.get('sketches',[]))
            ex('view.apply',view='iso')
            c.call('save',{'path':str(MODEL)})
            c.call('export',{'path':str(ROOT/'cad/fold_wing_v8_P4_6servo_assembly.step'),'format':'step'})
            print('P4 SIX SERVO native assembly saved; independent QA pending',len(final['bodies']),flush=True)
            return
        checks=[]
        for i,s in enumerate(specs):
            side=s['name'][0];stage=i%3
            for angle in [10,-10,0]:
                drive=ex('joint.drive',joint=s['name'],value=angle)
                if angle:assert drive.get('moved'),drive
                comparisons=[]
                for n in baseline:
                    idx=['YAW_CARRIER','ARM','HAND'].index(n.split('_',2)[2][:-2])
                    affected=n.startswith('P4_'+side+'_') and idx>=stage
                    zero=baseline[n]['total']['center_of_mass']
                    expected=rotate(zero,s['at']['point'],s['at']['z'],angle) if affected else zero
                    actual=ex('occurrence.properties',occurrence=n)['total']['center_of_mass']
                    err=max(abs(expected[k]-actual[k]) for k in range(3))
                    assert err<0.001,(s['name'],angle,n,err)
                    comparisons.append({'occurrence':n,'affected':affected,'expected':expected,'actual':actual,'max_error_mm':err})
                children=[]
                for child in specs[i+1:(i//3+1)*3]:
                    state=ex('joint.inspect',joint=child['name'])['joints'][0]
                    expected=rotate(child['at']['point'],s['at']['point'],s['at']['z'],angle)
                    expected_axis=rotate(child['at']['z'],[0,0,0],s['at']['z'],angle)
                    for endpoint in ['a','b']:
                        frame=state[endpoint]['frame']
                        assert max(abs(frame['origin'][k]-expected[k]) for k in range(3))<1e-6
                        assert max(abs(frame['z'][k]-expected_axis[k]) for k in range(3))<1e-6
                    children.append(state)
                checks.append({'joint':s['name'],'angle_deg':angle,'drive':drive,'com_checks':comparisons,'following_children':children})
                print('drive',s['name'],angle,drive.get('moved'),flush=True)
        dump('drive_checks.json',checks)
        dump('analytic_motion_summary.json',{'servo_count':6,'revolute_count':6,'drives':18,'com_comparisons':108,'max_com_error_mm':max(x['max_error_mm'] for ch in checks for x in ch['com_checks']),'cad_limits_deg':[-15,15],'test_angles_deg':[-10,0,10],'physical_limits_verified':False})
        dump('final_joints.json',ex('joint.list'))
        dump('motion_studies.json',ex('motion.list'))
        final=c.value(c.call('inspect_design',{'measure':True,'sketches':True}))
        dump('final_inspect.json',final)
        assert not [t for t in final['timeline'] if t.get('error') or t.get('warning')]
        assert all(s.get('dof',0)==0 for s in final.get('sketches',[]))
        ex('view.apply',view='iso')
        c.call('save',{'path':str(MODEL)})
        c.call('export',{'path':str(ROOT/'cad/fold_wing_v8_P4_6servo_assembly.step'),'format':'step'})
        print('P4 SIX SERVO native assembly saved',len(final['bodies']),flush=True)
    finally:
        c.close()
        assert hashlib.sha256(INPUT.read_bytes()).hexdigest()==original

if __name__=='__main__':main()
