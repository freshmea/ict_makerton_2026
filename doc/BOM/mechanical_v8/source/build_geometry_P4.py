"""Native SolidCraft geometry retrofit: six servos / three joints per arm.

Preserves P2/P3. Creates a shoulder pitch stage between the base yaw and the
retained wrist pitch. All new geometry and imported-arm cuts are SolidCraft
timeline commands. Hardware dimensions remain unmeasured fit trials.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math

from mcp_client import Client

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'source' / 'P4_geometry_files'
P4 = ROOT / 'P4'
INPUT = ROOT / 'cad' / 'fold_wing_v8_P2.solidcraft'
NATIVE = ROOT / 'cad' / 'fold_wing_v8_P4_geometry.solidcraft'


def commands():
    result = []
    def add(command, **params):
        result.append({'command': command, 'params': params})
    # Favourites expose the dimensions that are actually used below.
    for name, value, comment in [
        ('p4_shoulder_z',180,'Shoulder pitch world Z; CAD layout, mm'),
        ('p4_core_d',80,'Shoulder fixed core OD; verify loaded bearing fit'),
        ('p4_cap_d',88,'Moving shoulder cap OD; bottom Z136, 1 mm above yaw collar'),
        ('p4_arm_cut_z',225,'Retained curved arm lower cut plane'),
        ('p4_servo_offset',9.75,'Provisional servo output-axis offset; measure actual servo'),
        ('p4_servo_l',40.5,'Provisional servo case X size'),
        ('p4_servo_d',40,'Provisional servo case Y size'),
        ('p4_servo_h',20.2,'Provisional servo case Z size'),
    ]:
        add('parameters.add',name=name,expression=str(value)+' mm',comment=comment,favorite=True)
    for side, sign in [('L',-1),('R',1)]:
        sx = sign*275
        turret = side+'_SHOULDER_YAW_TURRET'
        # Removing the lower arm removes its old integrated yaw rotor too.
        for half in ['FRONT','REAR']:
            body = side+'_CURVED_ARM_CORE_'+half+'_part'
            add('solid.box',length=1000,width=200,height='p4_arm_cut_z+100',
                corner=[-500,-60,-100],operation='cut',targets=[body],name=side+'_TrimArm_'+half)
        # Fixed relative to yaw, but rotates as a whole under the J1 yaw joint.
        add('solid.cylinder',diameter=72,height=6,base=[sx,40,129],axis='Z',operation='new',
            body_name=turret,name=side+'_YawRotor')
        add('solid.box',length=50,width=34,height=9,center=[sx,40,137.5],operation='join',
            targets=[turret],name=side+'_YawShoulderPedestal')
        add('solid.cylinder',diameter='p4_core_d',height=54,base=[sx,13,'p4_shoulder_z'],axis='Y',
            operation='join',targets=[turret],name=side+'_FixedShoulderCore')
        add('solid.cylinder',diameter=74,height=48,base=[sx,16,'p4_shoulder_z'],axis='Y',
            operation='cut',targets=[turret],name=side+'_ShoulderCoreCavity')
        # Opening in the front wall permits case insertion after the cap is off.
        add('solid.box',length=41.3,width=8,height=21,center=[sx+sign*9.75,16,180],
            operation='cut',targets=[turret],name=side+'_ServoServiceOpening')
        # Compact rails lie wholly inside the OD and overlap the front wall by
        # 1 mm. Avoid clipping against the same curved wall before a union.
        for index, off in enumerate([-24.75,24.75],1):
            ex=sx+sign*9.75+off
            add('solid.box',length=6,width=11,height=20,center=[ex,20.5,180],operation='join',
                targets=[turret],name=side+'_ServoRail_'+str(index))
            for dz in [-5,5]:
                add('solid.cylinder',diameter=3.4,height=16,base=[ex,12,180+dz],axis='Y',
                    operation='cut',targets=[turret],name=side+'_ServoFlangeHole_'+str(index)+'_'+str(dz))
        # Rear fixed pin opening. Pin shoulder sits inside the core.
        add('solid.cylinder',diameter=5,height=8,base=[sx,61,180],axis='Y',
            operation='cut',targets=[turret],name=side+'_FixedStubOpening')
        # Original yaw horn recess is retained on the underside of the new rotor.
        for w,d in [(30,6.4),(6.4,30)]:
            add('solid.box',length=w,width=d,height=2.7,center=[sx,40,130.35],operation='cut',
                targets=[turret],name=side+'_YawCross_'+str(w))
        add('solid.cylinder',diameter=3.4,height=10,base=[sx,40,127],axis='Z',operation='cut',
            targets=[turret],name=side+'_YawHornCentre')
        # Moving shoulder front/rear caps are fused to the retained arm halves.
        for half, base_y, bridge_y in [('FRONT',6,25.45),('REAR',68,54.55)]:
            moving=side+'_ShoulderCapTemp_'+half
            arm=side+'_CURVED_ARM_CORE_'+half+'_part'
            add('solid.cylinder',diameter='p4_cap_d',height=6,base=[sx,base_y,180],axis='Y',
                operation='new',body_name=moving,name=side+'_MovingShoulderCap_'+half)
            # 0.1 mm relief each side avoids coincident imported seam faces;
            # the existing arm walls still meet at Y40 above the Z225 cut.
            add('solid.box',length=48,width=28.9,height=20,center=[sx,bridge_y,231],
                operation='join',targets=[moving],name=side+'_ShoulderTopBridge_'+half)
            add('solid.combine',target=arm,tools=[moving],operation='join',keep_tools=False)
            if half=='FRONT':
                # One outline avoids two coplanar subtractors in a cross cut.
                sketch=side+'_ShoulderCrossProfile'
                cross=[(-15,-3.2),(-3.2,-3.2),(-3.2,-15),(3.2,-15),(3.2,-3.2),(15,-3.2),
                       (15,3.2),(3.2,3.2),(3.2,15),(-3.2,15),(-3.2,3.2),(-15,3.2)]
                add('sketch.create',plane='XZ',offset='9.3',name=sketch)
                add('sketch.line',points=[[str(sx+dx),str(-180-dz)] for dx,dz in cross],closed=True,infer=False)
                add('sketch.constraint.fix',entities=['l'+str(i) for i in range(1,13)],fixed=True)
                add('sketch.solve')
                add('sketch.finish')
                add('solid.extrude',sketch=sketch,distance='3.7',operation='cut',targets=[arm],name=side+'_ShoulderHornCrossPocket')
                add('solid.cylinder',diameter=5.3,height=10,base=[sx,4,180],axis='Y',
                    operation='cut',targets=[arm],name=side+'_ShoulderHornScrew')
            else:
                add('solid.cylinder',diameter=16.3,height=8,base=[sx,67,180],axis='Y',
                    operation='cut',targets=[arm],name=side+'_ShoulderBearingSeat')
                add('solid.cylinder',diameter=18.2,height=1.05,base=[sx,73,180],axis='Y',
                    operation='cut',targets=[arm],name=side+'_ShoulderBearingFlange')
            # Accessible upper bridge fasteners; never bolt the rotating caps
            # through the fixed core. Nut/head seats are provisional M3 fits.
            for dx in [-14,14]:
                add('solid.cylinder',diameter=3.4,height=64,base=[sx+dx,9,232],axis='Y',
                    operation='cut',targets=[arm],name=side+'_ShoulderBridgeBolt_'+half+'_'+str(dx))
                add('solid.box',length=6.4,width=3.2,height=6.4,
                    center=[sx+dx,12.1 if half=='FRONT' else 67.9,232],
                    operation='cut',targets=[arm],name=side+'_BridgeFastenerSeat_'+half+'_'+str(dx))
        # New real third servo case in the torque chain, plus drive/bearing
        # envelopes. The shapes carry no fabricated spline or measured rating.
        servo=side+'_SHOULDER_SERVO_TRIAL'
        add('solid.box',length='p4_servo_l',width='p4_servo_d',height='p4_servo_h',
            center=[sx+sign*9.75,40,180],operation='new',body_name=servo,name=servo)
        shaft=side+'_SHOULDER_SHAFT_TRIAL'
        add('solid.cylinder',diameter=6,height=9.5,base=[sx,10.5,180],axis='Y',operation='new',body_name=shaft,name=shaft)
        horn=side+'_SHOULDER_HORN_TRIAL'
        add('solid.box',length=29.6,width=2.2,height=6,center=[sx,10.8,180],operation='new',body_name=horn,name=horn)
        add('solid.box',length=6,width=2.2,height=29.6,center=[sx,10.8,180],operation='join',targets=[horn],name=horn+'_Cross')
        add('solid.cylinder',diameter=3.2,height=6,base=[sx,8,180],axis='Y',operation='cut',targets=[horn],name=horn+'_Centre')
        bearing=side+'_SHOULDER_BEARING_TRIAL'
        add('solid.cylinder',diameter=16,height=4,base=[sx,69,180],axis='Y',operation='new',body_name=bearing,name=bearing)
        add('solid.cylinder',diameter=18,height=1,base=[sx,73,180],axis='Y',operation='join',targets=[bearing],name=bearing+'_Flange')
        add('solid.cylinder',diameter=5,height=7,base=[sx,67,180],axis='Y',operation='cut',targets=[bearing],name=bearing+'_Bore')
        stub=side+'_SHOULDER_FIXED_STUB_TRIAL'
        add('solid.cylinder',diameter=4.9,height=14,base=[sx,63,180],axis='Y',operation='new',body_name=stub,name=stub)
        add('solid.cylinder',diameter=8,height=2,base=[sx,62,180],axis='Y',operation='join',targets=[stub],name=stub+'_Shoulder')
        # The STEP base omitted v7's RGB preview bodies. Keep the six-per-arm
        # visual intent on the retained upper link, not on removed lower tube.
        for i in range(6):
            z=244+i*12
            t=(z-130)/185
            x=sign*(275-55*t+22*math.sin(math.pi*t))
            rgb=side+'_RGB_'+str(i)
            add('solid.cylinder',diameter=6,height=1.2,base=[x,22,z],axis=[0,-1,0],operation='new',body_name=rgb,name=rgb)
        add('appearance.assign',bodies=[turret],color='#68724d')
        add('appearance.assign',bodies=[side+'_CURVED_ARM_CORE_'+h+'_part' for h in ['FRONT','REAR']],color='#e8dbb7')
        add('appearance.assign',bodies=[servo,shaft],color='#303338')
        add('appearance.assign',bodies=[horn,bearing,stub],color='#8d969b')
        add('appearance.assign',bodies=[side+'_RGB_'+str(i) for i in range(6)],color='#e8a340')
    return result


def groups(body_names):
    result={'fixed':[],'L_yaw_carrier':[],'R_yaw_carrier':[],'L_arm':[],'R_arm':[],'L_hand':[],'R_hand':[]}
    for side in ['L','R']:
        result[side+'_yaw_carrier']=[side+'_'+s for s in ['SHOULDER_YAW_TURRET','SHOULDER_SERVO_TRIAL','SHOULDER_FIXED_STUB_TRIAL']]
        result[side+'_arm']=[side+'_'+s+'_part' for s in ['CURVED_ARM_CORE_FRONT','CURVED_ARM_CORE_REAR','PITCH_SERVO_EMBEDDED','FIXED_SUPPORT_STUB_TRIAL']]
        result[side+'_arm'] += [side+'_'+s for s in ['SHOULDER_SHAFT_TRIAL','SHOULDER_HORN_TRIAL','SHOULDER_BEARING_TRIAL']]
        result[side+'_arm'] += [side+'_RGB_'+str(i) for i in range(6)]
        result[side+'_hand']=[side+'_WRAP_HAND_'+h for h in ['FRONT','REAR']]+[side+'_HAND_DOWEL_'+str(i) for i in [1,2]]
        result[side+'_hand'] += [side+'_'+s+'_part' for s in ['SHORT_SERVO_SHAFT_TRIAL','ACTUAL_CROSS_HORN_PLACEHOLDER','F625ZZ_BEARING']]
    moving={name for key,names in result.items() if key!='fixed' for name in names}
    missing=moving-set(body_names)
    if missing:raise RuntimeError('Missing grouping bodies: '+repr(missing))
    result['fixed']=sorted(set(body_names)-moving)
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--skip-export',action='store_true');args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    for folder in ['cad','stl','renders']:(P4/folder).mkdir(parents=True,exist_ok=True)
    before=hashlib.sha256(INPUT.read_bytes()).hexdigest()
    script={'commands':commands()}
    (ROOT/'source/geometry_P4.json').write_text(json.dumps(script,indent=2)+'\n',encoding='utf-8')
    def dump(name,data):(OUT/name).write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    c=Client(headless=True)
    try:
        c.call('inspect_design',{'measure':False,'sketches':False})
        dump('open_P2.json',c.value(c.call('open',{'path':str(INPUT)})))
        dump('checkpoint.json',c.value(c.call('execute',{'command':'edit.checkpoint','params':{}})))
        # Three independent batches make failed geometry stages inspectable.
        right_index=next(i for i,x in enumerate(script['commands']) if x['params'].get('name')=='R_TrimArm_FRONT')
        stages=[script['commands'][:8],script['commands'][8:right_index],script['commands'][right_index:]]
        if sum(map(len,stages))!=len(script['commands']):raise RuntimeError('Unassigned native commands')
        for i,stage in enumerate(stages):
            response=c.value(c.call('batch',{'commands':stage,'verbose':False}));dump('stage_'+str(i)+'.json',response)
            print('native geometry stage',i,'commands',len(stage),flush=True)
        state=c.value(c.call('inspect_design',{'measure':True,'sketches':True}));dump('final_inspect.json',state)
        bad=[x for x in state['timeline'] if x.get('error') or x.get('warning')]
        if bad:raise RuntimeError('Timeline health: '+repr(bad))
        names=[x['name'] for x in state['bodies']]
        grouping=groups(names)
        (ROOT/'source/geometry_P4_groups.json').write_text(json.dumps(grouping,indent=2)+'\n',encoding='utf-8')
        c.call('execute',{'command':'document.metadata.set','params':{'values':{'project':'Fold Wing Buddy v8 P4 geometry','revision':'P4','description':'Six-servo native shoulder retrofit; yaw Z, shoulder Y, wrist Y per arm. All hardware fits provisional.'}}})
        c.call('save',{'path':str(NATIVE)})
        c.call('export',{'path':str(ROOT/'cad/fold_wing_v8_P4_geometry.step'),'format':'step'})
        parts=json.loads((ROOT/'evidence/13_exported_parts.json').read_text(encoding='utf-8'))
        parts += [{'name':s+'_SHOULDER_YAW_TURRET','body':s+'_SHOULDER_YAW_TURRET'} for s in ['L','R']]
        if not args.skip_export:
            for part in parts:
                for ext,folder in [('step','cad'),('stl','stl')]:
                    c.call('export',{'path':str(P4/folder/(part['name']+'.'+ext)),'format':ext,'bodies':[part['body']]})
            for ext,folder in [('step','cad'),('stl','stl')]:
                import shutil
                shutil.copyfile(ROOT/folder/('HAND_DOWEL_4x6.'+ext),P4/folder/('HAND_DOWEL_4x6.'+ext))
        (ROOT/'source/geometry_P4_parts.json').write_text(json.dumps(parts,indent=2)+'\n',encoding='utf-8')
        for view in ['iso','front','right']:
            c.call('screenshot',{'source':'model','view':view,'width':1400,'height':1000,'grid':False,'axes':False,'path':str(P4/'renders'/('P4_geometry_'+view+'.png'))})
        c.call('execute',{'command':'view.apply','params':{'view':'iso'}})
        c.call('save',{'path':str(NATIVE)})
        dump('complete.json',{'native':str(NATIVE),'bodies':len(names),'printed_unique':len(parts)+1,'servo_case_bodies':[s+'_'+n for s in ['L','R'] for n in ['YAW_SERVO_INSIDE_BASE_part','SHOULDER_SERVO_TRIAL','PITCH_SERVO_EMBEDDED_part']],'P2_sha256_unchanged':before==hashlib.sha256(INPUT.read_bytes()).hexdigest(),'status':'CAD trial, motion and interference checks separate'})
        print('P4 native geometry saved:',NATIVE,flush=True)
    finally:
        c.close()
        assert before==hashlib.sha256(INPUT.read_bytes()).hexdigest(),'P2 changed'


if __name__=='__main__':main()
