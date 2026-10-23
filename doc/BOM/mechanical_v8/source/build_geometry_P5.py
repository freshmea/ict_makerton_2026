"""Native SolidCraft P5: yaw / shoulder pitch / longitudinal wrist roll.

P4 is preserved. The wrist geometry, servo and bearing become coaxial with X;
the removable outer bearing cap gives a real assembly access path.
"""
from pathlib import Path
import argparse, hashlib, json, math, re, shutil
from mcp_client import Client
from build_hands_native import make_script

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'source/P5_geometry_files'
P5=ROOT/'P5'
INPUT=ROOT/'cad/fold_wing_v8_P4_geometry.solidcraft'
NATIVE=ROOT/'cad/fold_wing_v8_P5_geometry.solidcraft'


def hand_commands(side, sign, half):
    """Keep the constrained P4 palm/fingers; replace all drive geometry."""
    old,script=make_script(sign,half)
    tag=side+('_ROLL_YOKE_PALM_FRONT' if half=='FRONT' else '_ROLL_PALM_REAR')
    names={step['params']['name']:'P5_'+tag+'__'+step['params']['name'] for step in script['commands'] if 'name' in step['params']}
    def rewrite(value):
        if isinstance(value,list):return [rewrite(v) for v in value]
        if isinstance(value,dict):return {k:rewrite(v) for k,v in value.items()}
        if isinstance(value,str):
            for oldname,newname in sorted(names.items(),key=lambda item:-len(item[0])):
                value=re.sub(r'\b'+re.escape(oldname)+r'\b',newname,value)
            value=value.replace(old+'_Palm',tag+'_Palm').replace(old,tag)
        return value
    cmds=[]
    # Parameters before first solid; all have one namespace per part.
    for step in script['commands']:
        if step['command']=='solid.cylinder':break
        cmds.append({'command':step['command'],'params':rewrite(step['params'])})
    # Neck anchors the native palm and gives repeatable service bolt locations.
    sx=sign*220
    inward0,inward1=(29,70) if half=='FRONT' else (34,70)
    length=inward1-inward0
    cmds.append({'command':'solid.box','params':{'length':length,'width':29,'height':20,
        'center':[sx-sign*(inward0+inward1)/2,25.5 if half=='FRONT' else 54.5,315],
        'operation':'new','body_name':tag,'name':tag+'_Neck'}})
    start=next(i for i,s in enumerate(script['commands']) if s['command']=='sketch.create' and s['params'].get('name')=='PalmOuterProfile')
    stop=next(i for i,s in enumerate(script['commands']) if s['params'].get('name')=='DiffuserAperture')
    for step in script['commands'][start:stop+1]:
        cmds.append({'command':step['command'],'params':rewrite(step['params'])})
    bolt_start=next(i for i,s in enumerate(script['commands']) if s['command']=='sketch.create' and s['params'].get('name')=='BridgeBolt1Profile')
    for step in script['commands'][bolt_start:]:
        if step['command']=='document.inspect':continue
        cmds.append({'command':step['command'],'params':rewrite(step['params'])})
    return tag,cmds


def side_commands(side, sign):
    out=[]
    def add(command,**params):out.append({'command':command,'params':params})
    qx=sign*220
    axis=[sign,0,0]  # axial shape direction outwards; motion uses inward +/-X.
    arm_names=[side+'_CURVED_ARM_CORE_'+h+'_part' for h in ['FRONT','REAR']]
    # Remove the obsolete Y-axis wrist drive. Native history is retained.
    old_hardware=[side+'_'+s+'_part' for s in ['PITCH_SERVO_EMBEDDED','SHORT_SERVO_SHAFT_TRIAL','ACTUAL_CROSS_HORN_PLACEHOLDER','F625ZZ_BEARING','FIXED_SUPPORT_STUB_TRIAL']]
    add('solid.remove',bodies=old_hardware+[side+'_WRAP_HAND_FRONT',side+'_WRAP_HAND_REAR']+[side+'_RGB_'+str(i) for i in range(6)])
    for half,arm in zip(['FRONT','REAR'],arm_names):
        add('solid.box',length=1000,width=200,height=200,corner=[-500,-60,270],operation='cut',targets=[arm],name='P5_'+side+'_RemoveYWrist_'+half)
        core=side+'_RollCoreTemp_'+half
        add('solid.cylinder',diameter=80,height=54,base=[qx-sign*27,40,315],axis=axis,operation='new',body_name=core,name=core)
        add('solid.cylinder',diameter=74,height=48,base=[qx-sign*24,40,315],axis=axis,operation='cut',targets=[core],name=core+'_Cavity')
        # Axial front-wall rails have 0.5 mm material overlap and avoid case.
        for i,yy in enumerate([5.5,55],1):
            add('solid.box',length=11,width=6,height=20,center=[qx-sign*19,yy,315],operation='join',targets=[core],name=core+'_ServoRail'+str(i))
            for dz in [-5,5]:
                add('solid.cylinder',diameter=3.4,height=18,base=[qx-sign*30,yy,315+dz],axis=axis,operation='cut',targets=[core],name=core+'_ServoBolt'+str(i)+'_'+str(dz))
        add('solid.cylinder',diameter=9,height=8,base=[qx-sign*30,40,315],axis=axis,operation='cut',targets=[core],name=core+'_DriveOpening')
        add('solid.cylinder',diameter=5,height=8,base=[qx+sign*21,40,315],axis=axis,operation='cut',targets=[core],name=core+'_StubOpening')
        # Split Y40 with 0.1 mm relief. Existing lower arm still mates at Y40.
        if half=='FRONT':
            add('solid.box',length=200,width=150,height=200,corner=[qx-100,39.9,220],operation='cut',targets=[core],name=core+'_ServiceSplit')
        else:
            add('solid.box',length=200,width=150.1,height=200,corner=[qx-100,-110,220],operation='cut',targets=[core],name=core+'_ServiceSplit')
        # Keep this fixed adapter inside X +/-25, clear of moving end caps.
        add('solid.box',length=32,width=16.7,height=16,center=[qx+sign*9,31.45 if half=='FRONT' else 48.55,274],operation='join',targets=[core],name=core+'_LinkAdapter')
        for dx in [-15,15]:
            for dz in [-26,26]:
                add('solid.cylinder',diameter=8,height=25.8,base=[qx+dx,14 if half=='FRONT' else 40.2,315+dz],axis='Y',operation='join',targets=[core],name=core+'_CaseBoss_'+str(dx)+'_'+str(dz))
                add('solid.cylinder',diameter=3.4,height=70,base=[qx+dx,5,315+dz],axis='Y',operation='cut',targets=[core],name=core+'_CaseBolt_'+str(dx)+'_'+str(dz))
        add('solid.combine',target=arm,tools=[core],operation='join',keep_tools=False)
    # Fixed servo and opposed stub belong to the arm, never to the hand.
    servo=side+'_P5_WRIST_SERVO_CASE'
    add('solid.box',length=40,width=40.5,height=20.2,center=[qx,30.25,315],operation='new',body_name=servo,name=servo)
    stub=side+'_P5_WRIST_FIXED_STUB'
    add('solid.cylinder',diameter=4.9,height=14,base=[qx+sign*23,40,315],axis=axis,operation='new',body_name=stub,name=stub)
    add('solid.cylinder',diameter=8,height=2,base=[qx+sign*22,40,315],axis=axis,operation='join',targets=[stub],name=stub+'_Shoulder')
    # Native palm geometry with fully constrained original capsule sketches.
    front,front_cmds=hand_commands(side,sign,'FRONT');out.extend(front_cmds)
    rear,rear_cmds=hand_commands(side,sign,'REAR');out.extend(rear_cmds)
    # Inner drive cap + rear radial bridge, then fuse to the front neck.
    yoke=side+'_P5_YokeTemp'
    add('solid.cylinder',diameter=88,height=6,base=[qx-sign*34,40,315],axis=axis,operation='new',body_name=yoke,name=yoke)
    add('solid.box',length=58,width=22,height=20,center=[qx-sign,92,315],operation='join',targets=[yoke],name=yoke+'_RadialBridge')
    add('solid.combine',target=front,tools=[yoke],operation='join',keep_tools=False)
    # One YZ cross outline, fixed, cuts the actual X-axis drive cap.
    sketch=side+'_P5_RollHornProfile'
    add('sketch.create',plane={'origin':[qx-sign*30.7,40,315],'x_dir':[0,1,0],'y_dir':[0,0,sign]},name=sketch)
    cross=[(-15,-3.2),(-3.2,-3.2),(-3.2,-15),(3.2,-15),(3.2,-3.2),(15,-3.2),(15,3.2),(3.2,3.2),(3.2,15),(-3.2,15),(-3.2,3.2),(-15,3.2)]
    add('sketch.line',points=cross,closed=True,infer=False)
    add('sketch.constraint.fix',entities=['l'+str(i) for i in range(1,13)],fixed=True)
    add('sketch.solve');add('sketch.finish')
    add('solid.extrude',sketch=sketch,distance=3.7,operation='cut',targets=[front],name=side+'_P5_RollHornPocket')
    add('solid.cylinder',diameter=5.3,height=10,base=[qx-sign*36,40,315],axis=axis,operation='cut',targets=[front],name=side+'_P5_HornCentre')
    # Removable outer cap, bearing and two service fasteners.
    cap=side+'_ROLL_BEARING_CAP'
    add('solid.cylinder',diameter=88,height=6,base=[qx+sign*28,40,315],axis=axis,operation='new',body_name=cap,name=cap)
    add('solid.box',length=6,width=22,height=20,center=[qx+sign*31,92,315],operation='join',targets=[cap],name=cap+'_Ear')
    add('solid.cylinder',diameter=16.3,height=8,base=[qx+sign*27,40,315],axis=axis,operation='cut',targets=[cap],name=cap+'_BearingSeat')
    add('solid.cylinder',diameter=18.2,height=1.05,base=[qx+sign*33,40,315],axis=axis,operation='cut',targets=[cap],name=cap+'_FlangeSeat')
    for dz in [-5,5]:
        add('solid.cylinder',diameter=3.4,height=20,base=[qx+sign*18,90,315+dz],axis=axis,operation='cut',targets=[front,cap],name=side+'_P5_CapBolt_'+str(dz))
        add('solid.box',length=2.2,width=5.8,height=5.8,center=[qx+sign*26.9,90,315+dz],operation='cut',targets=[front],name=side+'_P5_CapNut_'+str(dz))
        add('solid.cylinder',diameter=6.4,height=3.2,base=[qx+sign*31.8,90,315+dz],axis=axis,operation='cut',targets=[cap],name=side+'_P5_CapHead_'+str(dz))
    shaft=side+'_P5_WRIST_SHAFT'
    add('solid.cylinder',diameter=6,height=9.5,base=[qx-sign*29.5,40,315],axis=axis,operation='new',body_name=shaft,name=shaft)
    horn=side+'_P5_WRIST_HORN'
    add('solid.box',length=2.2,width=29.6,height=6,center=[qx-sign*29.2,40,315],operation='new',body_name=horn,name=horn)
    add('solid.box',length=2.2,width=6,height=29.6,center=[qx-sign*29.2,40,315],operation='join',targets=[horn],name=horn+'_Cross')
    add('solid.cylinder',diameter=3.2,height=6,base=[qx-sign*32,40,315],axis=axis,operation='cut',targets=[horn],name=horn+'_Centre')
    bearing=side+'_P5_WRIST_BEARING'
    add('solid.cylinder',diameter=16,height=4,base=[qx+sign*29,40,315],axis=axis,operation='new',body_name=bearing,name=bearing)
    add('solid.cylinder',diameter=18,height=1,base=[qx+sign*33,40,315],axis=axis,operation='join',targets=[bearing],name=bearing+'_Flange')
    add('solid.cylinder',diameter=5,height=7,base=[qx+sign*27,40,315],axis=axis,operation='cut',targets=[bearing],name=bearing+'_Bore')
    # Six small display-only dots on exposed retained link; no LED hardware
    # dimensions or electrical module fit are asserted.
    for i in range(6):
        newz=244+i*4.4
        def px(z):
            t=(z-130)/185
            return sign*(275-55*t+22*math.sin(math.pi*t))
        add('solid.cylinder',diameter=3.2,height=1.2,base=[px(newz),22,newz],axis=[0,-1,0],operation='new',body_name=side+'_RGB_'+str(i),name='P5_'+side+'_RGB_'+str(i))
    add('appearance.assign',bodies=[front,rear,cap]+arm_names,color='#e8dbb7')
    add('appearance.assign',bodies=[servo,shaft],color='#303338')
    add('appearance.assign',bodies=[horn,bearing,stub],color='#8d969b')
    add('appearance.assign',bodies=[side+'_RGB_'+str(i) for i in range(6)],color='#e8a340')
    return out


def groups(body_names):
    g={'fixed':[]}
    for side in ['L','R']:
        g[side+'_yaw_carrier']=[side+'_'+s for s in ['SHOULDER_YAW_TURRET','SHOULDER_SERVO_TRIAL','SHOULDER_FIXED_STUB_TRIAL']]
        g[side+'_arm']=[side+'_CURVED_ARM_CORE_'+h+'_part' for h in ['FRONT','REAR']]+[side+'_P5_WRIST_SERVO_CASE',side+'_P5_WRIST_FIXED_STUB']
        g[side+'_arm'] += [side+'_'+s for s in ['SHOULDER_SHAFT_TRIAL','SHOULDER_HORN_TRIAL','SHOULDER_BEARING_TRIAL']]+[side+'_RGB_'+str(i) for i in range(6)]
        g[side+'_hand']=[side+'_'+s for s in ['ROLL_YOKE_PALM_FRONT','ROLL_PALM_REAR','ROLL_BEARING_CAP']]+[side+'_HAND_DOWEL_'+str(i) for i in [1,2]]+[side+'_P5_WRIST_'+s for s in ['SHAFT','HORN','BEARING']]
    moving={n for k,v in g.items() if k!='fixed' for n in v}
    if moving-set(body_names):raise RuntimeError('Missing P5 bodies '+repr(moving-set(body_names)))
    g['fixed']=sorted(set(body_names)-moving)
    return g


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--skip-export',action='store_true');ns=ap.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    for folder in ['cad','stl','renders']:(P5/folder).mkdir(parents=True,exist_ok=True)
    original=hashlib.sha256(INPUT.read_bytes()).hexdigest()
    def dump(name,value):(OUT/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    stages=[side_commands('L',-1),side_commands('R',1)]
    (ROOT/'source/geometry_P5.json').write_text(json.dumps({'commands':sum(stages,[])},indent=2)+'\n',encoding='utf-8')
    c=Client(headless=True,timeout=240)
    try:
        c.call('inspect_design',{'measure':False,'sketches':False})
        dump('open_P4.json',c.value(c.call('open',{'path':str(INPUT)})))
        # Stabilise the two existing P4 cross profiles without altering shape.
        for side in ['L','R']:
            for cmd,params in [('sketch.edit',{'sketch':side+'_ShoulderCrossProfile'}),('sketch.constraint.fix',{'entities':['l'+str(i) for i in range(1,13)],'fixed':True}),('sketch.solve',{}),('sketch.finish',{})]:
                c.call('execute',{'command':cmd,'params':params})
        for i,stage in enumerate(stages):
            r=c.value(c.call('batch',{'commands':stage,'verbose':False}));dump('stage_'+str(i)+'.json',r)
            print('P5 native side',i,'commands',len(stage),flush=True)
        state=c.value(c.call('inspect_design',{'measure':True,'sketches':True}));dump('final_inspect.json',state)
        bad=[f for f in state['timeline'] if f.get('error') or f.get('warning')]
        loose=[s for s in state.get('sketches',[]) if s.get('dof',0)]
        if bad or loose:raise RuntimeError('P5 health '+repr(bad)+' loose '+repr([(s.get('name'),s.get('dof')) for s in loose]))
        names=[b['name'] for b in state['bodies']]
        (ROOT/'source/geometry_P5_groups.json').write_text(json.dumps(groups(names),indent=2)+'\n',encoding='utf-8')
        c.call('execute',{'command':'document.metadata.set','params':{'values':{'project':'Fold Wing Buddy v8 P5 geometry','revision':'P5','description':'Six servos: yaw Z, shoulder pitch local Y, wrist roll local inward X. Native wrist redesign; fit trials only.'}}})
        c.call('save',{'path':str(NATIVE)})
        c.call('export',{'path':str(ROOT/'cad/fold_wing_v8_P5_geometry.step'),'format':'step'})
        old=json.loads((ROOT/'source/geometry_P4_parts.json').read_text())
        parts=[part for part in old if 'WRAP_HAND' not in part['name']]
        parts += [{'name':side+'_'+s,'body':side+'_'+s} for side in ['L','R'] for s in ['ROLL_YOKE_PALM_FRONT','ROLL_PALM_REAR','ROLL_BEARING_CAP']]
        (ROOT/'source/geometry_P5_parts.json').write_text(json.dumps(parts,indent=2)+'\n',encoding='utf-8')
        print('P5 native geometry ready',str(NATIVE),flush=True)
        if not ns.skip_export:
            for part in parts:
                for ext,folder in [('step','cad'),('stl','stl')]:
                    c.call('export',{'path':str(P5/folder/(part['name']+'.'+ext)),'format':ext,'bodies':[part['body']]})
            for ext,folder in [('step','cad'),('stl','stl')]:shutil.copyfile(ROOT/'P4'/folder/('HAND_DOWEL_4x6.'+ext),P5/folder/('HAND_DOWEL_4x6.'+ext))
            # Native STEP remains authoritative. Preserve native arm STL and
            # generate closed print meshes with explicitly logged conversion.
            from retessellate_P5_arms import retessellate_arms
            retessellate_arms()
        for view in ['iso','front','right']:
            c.call('screenshot',{'source':'model','view':view,'width':1400,'height':1000,'grid':False,'axes':False,'path':str(P5/'renders'/('P5_geometry_'+view+'.png'))})
        c.call('execute',{'command':'view.apply','params':{'view':'iso'}});c.call('save',{'path':str(NATIVE)})
        dump('complete.json',{'bodies':len(names),'unique_print_parts':len(parts)+1,'native':str(NATIVE),'input_P4_unchanged':original==hashlib.sha256(INPUT.read_bytes()).hexdigest(),'hardware_fit':'not measured','motion_verified':False})
    finally:
        c.close()
        assert original==hashlib.sha256(INPUT.read_bytes()).hexdigest(),'P4 input changed'


if __name__=='__main__':main()
