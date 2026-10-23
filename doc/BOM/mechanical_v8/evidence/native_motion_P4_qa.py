"""Independent isolated headless six-axis SolidCraft P4 motion QA.

Writes only native_motion_P4_qa.* evidence. Never saves or connects to GUI.
"""
from pathlib import Path
import hashlib
import json
import math
import sys
from zipfile import ZipFile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / 'source'))
from mcp_client import Client

FILE = ROOT / 'cad/fold_wing_v8_P4_6servo.solidcraft'
SUFFIXES = ['J1_YAW', 'J2_SHOULDER_PITCH', 'J3_WRIST_PITCH']
NAMES = [s + '_' + n for s in ['L', 'R'] for n in SUFFIXES]
COM_TOLERANCE = 1e-3
FRAME_TOLERANCE = 1e-6


def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def error(a,b): return math.sqrt(sum((x-y)**2 for x,y in zip(a,b)))
def centre(p): return p['total']['center_of_mass']


def rotate(p, pivot, axis, deg):
    norm = math.sqrt(sum(v*v for v in axis))
    axis = [v/norm for v in axis]
    a = math.radians(deg)
    v = [p[i]-pivot[i] for i in range(3)]
    dot = sum(v[i]*axis[i] for i in range(3))
    cross = [axis[1]*v[2]-axis[2]*v[1], axis[2]*v[0]-axis[0]*v[2], axis[0]*v[1]-axis[1]*v[0]]
    return [pivot[i]+v[i]*math.cos(a)+cross[i]*math.sin(a)+axis[i]*dot*(1-math.cos(a)) for i in range(3)]


def execute(c,cmd,**params):
    return Client.value(c.call('execute',{'command':cmd,'params':params}))


def healthy(c):
    d=execute(c,'joint.list')
    assert not d['errors'] and not d['conflicts'] and not d['floating'], d
    return d


def zero(c):
    for name in NAMES: execute(c,'joint.drive',joint=name,value=0)


def forward(point,side,level,values):
    """World point of stage 1/2/3 after serial rotations; independent math."""
    sg=-1 if side=='L' else 1
    pivots=[[sg*275,40,130],[sg*275,40,180],[sg*220,40,315]]
    axes=[[0,0,1],[0,1,0],[0,1,0]]
    frames=[]
    p=list(point)
    for i in range(3):
        frames.append({'origin':pivots[i][:],'z':axes[i][:]})
        a=values[side+'_'+SUFFIXES[i]]
        if i<level: p=rotate(p,pivots[i],axes[i],a)
        for j in range(i+1,3):
            pivots[j]=rotate(pivots[j],pivots[i],axes[i],a)
            axes[j]=rotate(axes[j],[0,0,0],axes[i],a)
    return p,frames


def occurrences(c,ids):
    props={name:execute(c,'occurrence.properties',occurrence=occ,descendants=False) for name,occ in ids.items()}
    assert all(p['body_count']>0 for p in props.values()), props
    return props


def verify_pose(c,ids,baseline,values):
    props=occurrences(c,ids)
    com_errors={}
    for name in NAMES:
        level=SUFFIXES.index(name[2:])+1
        expected,_=forward(centre(baseline[name]),name[0],level,values)
        gap=error(centre(props[name]),expected)
        assert gap<COM_TOLERANCE,(name,values,gap,centre(props[name]),expected)
        com_errors[name]=gap
    inspect=execute(c,'joint.inspect')
    frame_errors={}
    for j in inspect['joints']:
        if j['name'] not in NAMES: continue
        name=j['name'];side=name[0];ix=SUFFIXES.index(name[2:])
        _,frames=forward([0,0,0],side,3,values)
        expected=frames[ix]
        assert j['a']['resolves'] and j['b']['resolves']
        gaps={}
        for endpoint in ['a','b']:
            gaps['origin_'+endpoint+'_mm']=error(j[endpoint]['frame']['origin'],expected['origin'])
            gaps['axis_'+endpoint+'_vector']=error(j[endpoint]['frame']['z'],expected['z'])
        assert max(gaps.values())<FRAME_TOLERANCE,(name,values,j['a']['frame'],expected,gaps)
        frame_errors[name]=gaps
    jl=healthy(c)
    actual={j['name']:j['values'][0]['value'] for j in jl['joints'] if j['type']=='revolute'}
    assert set(actual)==set(NAMES)
    assert max(abs(actual[n]-values[n]) for n in NAMES)<1e-7,(actual,values)
    return {'actual_values_deg':actual,'analytic_COM_error_mm':com_errors,'serial_joint_frame_errors':frame_errors}


def study_values(study,step,joint_by_id):
    values={n:0 for n in NAMES}
    for key in study['keys']:
        points=key['points']; name=joint_by_id[key['joint']]['name']
        value=points[-1][1]
        for (x0,y0),(x1,y1) in zip(points,points[1:]):
            if x0<=step<=x1:
                value=y0+(y1-y0)*(step-x0)/(x1-x0) if x1!=x0 else y1
                break
        values[name]=math.degrees(value)
    return values


assert FILE.is_file(),FILE
file_hash=sha(FILE)
report={'file':str(FILE.relative_to(ROOT)),'native_sha256':file_hash,'COM_tolerance_mm':COM_TOLERANCE,
        'joint_frame_tolerance':FRAME_TOLERANCE,'direct_drives':[],'serial_nested_poses':[],'study_playback':[]}
with ZipFile(FILE) as z:
    assert z.testzip() is None
    doc=json.loads(z.read('document.json'))
    report['native_zip_crc']='pass';report['feature_count']=len(doc['features'])
c=Client(headless=True,timeout=240)
try:
    c.call('inspect_design',{'measure':False,'sketches':False})
    report['first_open']=Client.value(c.call('open',{'path':str(FILE.resolve())}))
    assert not report['first_open'].get('errors') and not report['first_open'].get('warnings')
    jl=healthy(c);rev=[j for j in jl['joints'] if j['type']=='revolute']
    assert {j['name'] for j in rev}==set(NAMES) and len(rev)==6
    assert all(not j['suppressed'] and abs(j['values'][0]['value'])<1e-8 for j in rev)
    assert all(j['values'][0]['limits'][0]<=-10 and j['values'][0]['limits'][1]>=10 for j in rev)
    initial=execute(c,'joint.inspect'); report['initial_joints']=jl;report['initial_joint_inspect']=initial
    ids={j['name']:j['b']['occurrence'] for j in initial['joints'] if j['name'] in NAMES}
    assert len(set(ids.values()))==6
    baseline=occurrences(c,ids);report['driven_occurrence_ids']=ids;report['baseline_properties']=baseline
    state=Client.value(c.call('inspect_design',{'measure':True,'sketches':True,'joints':False}))
    assert not [f for f in state['timeline'] if f.get('error') or f.get('warning')]
    assert not [s for s in state['sketches'] if s.get('dof')!=0]
    report['body_count']=len(state['bodies'])
    motors=[b for b in state['bodies'] if 'SERVO' in b['name'] and 20000<b['volume_mm3']<50000]
    assert len(motors)==6,[(b['name'],b['volume_mm3']) for b in motors]
    expected_motor_names={s+'_'+suffix for s in ['L','R'] for suffix in ['YAW_SERVO_INSIDE_BASE_part','SHOULDER_SERVO_TRIAL','PITCH_SERVO_EMBEDDED_part']}
    assert {b['name'] for b in motors}==expected_motor_names
    report['six_servo_bodies']=[{'name':b['name'],'volume_mm3':b['volume_mm3'],'bbox':b['bbox']} for b in motors]
    studies=execute(c,'motion.list');report['initial_studies']=studies
    assert len(studies['studies'])==7
    combined=[s for s in studies['studies'] if len(s['keys'])==6]
    assert len(combined)==1
    combined=combined[0]
    assert {k['joint'] for k in combined['keys']}=={j['id'] for j in rev}
    assert len([s for s in studies['studies'] if len(s['keys'])==1])==6
    neutral={name:0 for name in NAMES}
    report['neutral_initial']=verify_pose(c,ids,baseline,neutral)
    fixed=execute(c,'occurrence.properties',occurrence='PILL_BASE_TRAY_2_part:1')
    print('PASS: six real neutral revolute axes, six servo envelopes, seven saved studies and healthy grounded assembly',flush=True)
    for name in NAMES:
        for angle in [10,-10]:
            zero(c)
            drive=execute(c,'joint.drive',joint=name,value=angle)
            assert drive.get('moved') and not drive.get('reason') and not drive.get('stopped_by_loop'),drive
            values=dict(neutral);values[name]=angle
            result=verify_pose(c,ids,baseline,values)
            still=execute(c,'occurrence.properties',occurrence='PILL_BASE_TRAY_2_part:1')
            assert error(centre(fixed),centre(still))<1e-7
            report['direct_drives'].append({'joint':name,'command_deg':angle,'drive':drive,**result})
    for side in ['L','R']:
        zero(c);values=dict(neutral)
        for suffix in SUFFIXES:
            name=side+'_'+suffix;values[name]=10
            moved=execute(c,'joint.drive',joint=name,value=10)
            assert moved.get('moved')
            result=verify_pose(c,ids,baseline,values)
            report['serial_nested_poses'].append({'side':side,'stage_added':name,**result})
    zero(c)
    restored=occurrences(c,ids)
    report['neutral_return_max_COM_error_mm']=max(error(centre(restored[n]),centre(baseline[n])) for n in NAMES)
    assert report['neutral_return_max_COM_error_mm']<COM_TOLERANCE
    print('PASS: 12 independent +/-10 degree drives and six cumulative serial poses with child-axis following',flush=True)
    joint_by_id={j['id']:j for j in rev}
    sample_steps=sorted({p[0] for k in combined['keys'] for p in k['points'] if abs(p[1])>1e-8}|{combined['steps']})
    assert len(sample_steps)>=13
    for step in sample_steps:
        play=execute(c,'motion.play',study=combined['name'],step=step,quiet=True)
        assert not play.get('unmoved'),play
        expected=study_values(combined,step,joint_by_id)
        result=verify_pose(c,ids,baseline,expected)
        report['study_playback'].append({'step':step,'moved':play.get('moved'),**result})
    assert all(abs(v)<1e-8 for v in report['study_playback'][-1]['actual_values_deg'].values())
    report['final_joints']=healthy(c)
finally:c.close()
assert sha(FILE)==file_hash,'Saved P4 design changed during isolated QA'
c=Client(headless=True,timeout=240)
try:
    c.call('inspect_design',{'measure':False,'sketches':False})
    report['second_open']=Client.value(c.call('open',{'path':str(FILE.resolve())}))
    persisted=healthy(c);rev2=[j for j in persisted['joints'] if j['type']=='revolute']
    assert {j['name'] for j in rev2}==set(NAMES)
    assert all(abs(j['values'][0]['value'])<1e-8 for j in rev2)
    assert {j['name']:j['values'][0]['limits'] for j in rev2}=={j['name']:j['values'][0]['limits'] for j in rev}
    assert execute(c,'motion.list')==studies
    report['persisted_joints']=persisted
    # The second fresh reopen is neutral. Export the static shoulder evidence
    # here, so the later independent OCCT fit audit need not replay 377 native
    # features a third time. Each exported source is hashed against this file.
    geometry_names=[s+'_'+suffix for s in ['L','R'] for suffix in ['SHOULDER_YAW_TURRET','SHOULDER_SERVO_TRIAL','CURVED_ARM_CORE_FRONT_part','CURVED_ARM_CORE_REAR_part','ROUND_YAW_COLLAR_TRIAL_part']]
    geometry_exports={}
    for name in geometry_names:
        target=HERE/('native_motion_P4_qa.geometry_'+name+'.step')
        c.call('export',{'path':str(target.resolve()),'format':'step','bodies':[name]})
        geometry_exports[name]={'path':target.name,'sha256':sha(target)}
    (HERE/'native_motion_P4_qa.geometry_exports.json').write_text(json.dumps({'native_sha256':file_hash,'exports':geometry_exports},indent=2)+'\n',encoding='utf-8')
finally:c.close()
assert sha(FILE)==file_hash
report['saved_file_unchanged']=True;report['accepted']=True
report['limitations']=['Servo shapes are CAD envelopes; six motor bodies are not proof of physical installation or actuator operation.',
 'Demo joint limits and +/-10 degree drives are CAD tests, not physical safe limits, collision/load validation or servo-control proof.',
 'COM integration tolerance is 0.001 mm; exact joint origin and axis checks use 1e-6.']
(HERE/'native_motion_P4_qa.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('PASS: real saved-study playback and second fresh reopen; native P4 remained unchanged',flush=True)
