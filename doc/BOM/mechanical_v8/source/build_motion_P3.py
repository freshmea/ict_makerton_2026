"""Add four genuine SolidCraft revolute joints to a preserved P2 design.

The official 0.20.0 CLI runs in a fresh headless process; never connects to GUI.
No geometry regeneration and no write to P2. All limits are provisional CAD
demonstration limits, not measured servo or hardware-safe limits.
"""
from pathlib import Path
import argparse, hashlib, json, math
from mcp_client import Client

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'source/P3_files'
OUT.mkdir(exist_ok=True)
P2=ROOT/'cad/fold_wing_v8_P2.solidcraft'
P3=ROOT/'cad/fold_wing_v8_P3_motion.solidcraft'

def dump(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

def command(command_id,**params):return {'command':command_id,'params':params}

def make_commands(components):
    leaves={body:(c['occurrences'][0]['id'],c['occurrences'][0]['name']) for c in components['components'] if c['id']!=0 and c['bodies'] for body in c['bodies']}
    base=next(c for c in components['components'] if c['id']==1)['occurrences'][0]
    armsets={};handsets={}
    moving=set()
    for side in ['L','R']:
        armsets[side]=[side+'_'+s+'_part' for s in ['CURVED_ARM_CORE_FRONT','CURVED_ARM_CORE_REAR','PITCH_SERVO_EMBEDDED','FIXED_SUPPORT_STUB_TRIAL']]
        handsets[side]=[side+'_'+s+'_part' for s in ['SHORT_SERVO_SHAFT_TRIAL','ACTUAL_CROSS_HORN_PLACEHOLDER','F625ZZ_BEARING']]
        moving.update(armsets[side]+handsets[side])
    fixed=sorted({v[0] for body,v in leaves.items() if body not in moving and not body.startswith('SEAM_SPLICE_')})
    cmds=[command('component.unlock',component=1)]
    for side in ['L','R']:
        comp='P3_'+side+'_HAND'
        cmds += [command('component.create',name=comp,parent='root',activate=False),command('component.move_bodies',bodies=[side+'_WRAP_HAND_FRONT',side+'_WRAP_HAND_REAR',side+'_HAND_DOWEL_1',side+'_HAND_DOWEL_2'],component=comp)]
    cmds += [command('occurrence.ground',occurrence=base['id'],grounded=True),command('joint.rigid_group',occurrences=[base['id']]+fixed)]
    for side in ['L','R']:
        cmds += [command('joint.rigid_group',occurrences=[leaves[b][0] for b in armsets[side]]),command('joint.rigid_group',occurrences=['P3_'+side+'_HAND:1']+[leaves[b][0] for b in handsets[side]])]
    specs=[]
    for side,sgn in [('L',-1),('R',1)]:
        arm=leaves[side+'_CURVED_ARM_CORE_FRONT_part'][1]
        hand='P3_'+side+'_HAND:1'
        for suffix,a,b,point,axis in [('J1_YAW',base['name'],arm,[sgn*275,40,130],[0,0,1]),('J2_PITCH',arm,hand,[sgn*220,40,315],[0,1,0])]:
            spec=dict(name=side+'_'+suffix,type='revolute',a=a,b=b,at={'occurrence':a,'point':point,'z':axis},limits=[[-15,15]])
            cmds.append(command('joint.as_built',**spec));specs.append(spec)
    keys=[]
    for i,spec in enumerate(specs):
        # Sequential moves isolate each drive and return to neutral in between.
        start=i*20
        keys.append({'joint':spec['name'],'points':[[0,0],[start,0],[start+5,10],[start+10,-10],[start+15,0],[80,0]] if start else [[0,0],[5,10],[10,-10],[15,0],[80,0]]})
    cmds += [command('motion.study',name='P3_FOUR_JOINT_DEMO',steps=80,keys=keys)]
    # Four simple studies are convenient for selecting one joint in the GUI.
    for spec in specs:
        cmds.append(command('motion.study',name=spec['name']+'_DEMO',steps=20,keys=[{'joint':spec['name'],'points':[[0,0],[5,10],[10,-10],[15,0],[20,0]]}]))
    cmds += [command('document.metadata.set',values={
        'project':'Fold Wing Buddy v8 P3 motion', 'revision':'P3',
        'description':'Four grounded-chain revolute joints: left/right J1 yaw and J2 pitch. Neutral pose saved. +/-15 degree provisional CAD demonstration limits; no measured hardware limits or collision-safe range claim.'})]
    return cmds,specs,{'grounded':base,'fixed_occurrences':fixed,'arm_bodies':armsets,'hand_rigid_bodies':handsets,'native_hand_component_bodies':{s:[s+'_WRAP_HAND_FRONT',s+'_WRAP_HAND_REAR',s+'_HAND_DOWEL_1',s+'_HAND_DOWEL_2'] for s in ['L','R']}}

def execute(c,cmd,**params):return c.value(c.call('execute',{'command':cmd,'params':params}))

def rotate(point,pivot,axis,degrees):
    a=math.radians(degrees);v=[point[i]-pivot[i] for i in range(3)]
    dot=sum(v[i]*axis[i] for i in range(3))
    cross=[axis[1]*v[2]-axis[2]*v[1],axis[2]*v[0]-axis[0]*v[2],axis[0]*v[1]-axis[1]*v[0]]
    return [pivot[i]+v[i]*math.cos(a)+cross[i]*math.sin(a)+axis[i]*dot*(1-math.cos(a)) for i in range(3)]

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--build-only',action='store_true');args=ap.parse_args()
    original_hash=hashlib.sha256(P2.read_bytes()).hexdigest()
    c=Client(headless=True)
    try:
        c.call('inspect_design',{'measure':False,'sketches':False})
        c.call('open',{'path':str(P2)})
        initial=c.value(c.call('inspect_design',{'measure':True,'sketches':False}));dump('initial_P2_inspect.json',initial)
        previous=execute(c,'joint.list');dump('initial_P2_joints.json',previous)
        components=execute(c,'component.list',compact=False)
        dump('initial_P2_components.json',components)
        checkpoint=execute(c,'edit.checkpoint');dump('initial_checkpoint.json',checkpoint)
        cmds,specs,grouping=make_commands(components)
        (ROOT/'source/motion_P3.json').write_text(json.dumps({'commands':cmds},indent=2)+'\n',encoding='utf-8')
        dump('group_mapping.json',grouping)
        dump('joint_specs.json',specs)
        built=c.value(c.call('batch',{'commands':cmds,'verbose':False}));dump('build_batch.json',built)
        joints=execute(c,'joint.list');dump('built_joints.json',joints)
        dump('built_joint_inspect.json',execute(c,'joint.inspect'))
        dump('built_components.json',execute(c,'component.list',compact=True,bodies=True))
        print('built',len(joints['joints']),'revolute',sum(j['type']=='revolute' for j in joints['joints']),'conflicts',joints['conflicts'],'errors',joints['errors'],'floating',len(joints['floating']),flush=True)
        assert not joints['conflicts'] and not joints['errors']
        assert sum(j['type']=='revolute' for j in joints['joints'])==4
        grouping['grounded']['grounded']=grouping['grounded']['id'] in joints['fixed']
        dump('group_mapping.json',grouping)
        baseline={}
        for name in ['L_CURVED_ARM_CORE_FRONT_part:1','R_CURVED_ARM_CORE_FRONT_part:1','P3_L_HAND:1','P3_R_HAND:1']:
            baseline[name]=execute(c,'occurrence.properties',occurrence=name)
        dump('baseline_moving_properties.json',baseline)
        neutral=c.value(c.call('inspect_design',{'measure':True,'sketches':False}))
        before={b['name']:b for b in initial['bodies']}
        after={b['name']:b for b in neutral['bodies']}
        assert before.keys()==after.keys()
        pose_deltas={name:max(abs(before[name]['center_of_mass'][i]-after[name]['center_of_mass'][i]) for i in range(3)) for name in before}
        dump('neutral_assembly_unchanged.json',{'body_count':len(before),'max_center_shift_mm':max(pose_deltas.values()),'per_body_center_shift_mm':pose_deltas})
        assert max(pose_deltas.values())<1e-6,'Joint creation changed the modelled neutral pose'
        execute(c,'browser.visibility',joints=[j['id'] for j in joints['joints']],visible=False)
        execute(c,'browser.visibility',joints=[s['name'] for s in specs],visible=True)
        c.call('execute',{'command':'view.apply','params':{'view':'iso'}})
        c.call('save',{'path':str(P3)})
        print('saved',str(P3),flush=True)
        if args.build_only:return
        # Independent analytic COM comparisons accompany every +/- drive.
        checks=[]
        for spec in specs:
            for angle in [10,-10,0]:
                drive=execute(c,'joint.drive',joint=spec['name'],value=angle)
                props={name:execute(c,'occurrence.properties',occurrence=name) for name in baseline}
                analytic=[]
                for name in baseline:
                    initial_com=baseline[name]['total']['center_of_mass']
                    affected=(name.startswith(spec['name'][0]) or name.startswith('P3_'+spec['name'][0])) and ('J1' in spec['name'] or name.startswith('P3_'))
                    expected=rotate(initial_com,spec['at']['point'],spec['at']['z'],angle) if affected else initial_com
                    measured=props[name]['total']['center_of_mass']
                    error=max(abs(measured[i]-expected[i]) for i in range(3))
                    analytic.append({'occurrence':name,'affected':affected,'expected_center_of_mass':expected,'measured_center_of_mass':measured,'max_error_mm':error})
                    # Independently integrated COM is slightly different after
                    # a rigid rotation; the exact joint frames are checked at
                    # 1e-6 below. 0.0001 mm is a numeric, not fit, tolerance.
                    assert error<1e-4,(spec['name'],angle,name,error)
                wrist_frames=None
                if 'J1' in spec['name']:
                    wrist_name=spec['name'][0]+'_J2_PITCH'
                    wrist_frames=execute(c,'joint.inspect',joint=wrist_name)
                    wrist_spec=next(s for s in specs if s['name']==wrist_name)
                    expected_origin=rotate(wrist_spec['at']['point'],spec['at']['point'],spec['at']['z'],angle)
                    expected_axis=rotate([0,1,0],[0,0,0],[0,0,1],angle)
                    for endpoint in ['a','b']:
                        frame=wrist_frames['joints'][0][endpoint]['frame']
                        assert max(abs(frame['origin'][i]-expected_origin[i]) for i in range(3))<1e-6
                        assert max(abs(frame['z'][i]-expected_axis[i]) for i in range(3))<1e-6
                checks.append({'joint':spec['name'],'angle_deg':angle,'drive':drive,'properties':props,'analytic_com':analytic,'wrist_follows_yaw':wrist_frames})
                print('drive',spec['name'],angle,'moved',drive.get('moved'),'reason',drive.get('reason'),flush=True)
                if angle:assert drive.get('moved'),drive
        dump('drive_checks_raw.json',checks)
        dump('analytic_motion_summary.json',{'joint_count':4,'drives':12,'all_drive_moved':all(x['drive']['moved'] for x in checks),'analytic_com_checks':sum(len(x['analytic_com']) for x in checks),'max_error_mm':max(a['max_error_mm'] for x in checks for a in x['analytic_com']),'com_tolerance_mm':1e-4,'joint_frame_tolerance_mm':1e-6,'parent_yaw_carries_wrist_frames':True,'saved_neutral':True,'hardware_angle_limits_verified':False,'cad_demonstration_limits_deg':[-15,15]})
        dump('motion_studies.json',execute(c,'motion.list'))
        dump('motion_export.json',execute(c,'motion.export',study='P3_FOUR_JOINT_DEMO',samples=17))
        dump('final_joint_inspect.json',execute(c,'joint.inspect'))
        dump('final_joints.json',execute(c,'joint.list'))
        c.call('save',{'path':str(P3)})
    finally:
        c.close()
        assert hashlib.sha256(P2.read_bytes()).hexdigest()==original_hash,'P2 input changed'

if __name__=='__main__':main()
