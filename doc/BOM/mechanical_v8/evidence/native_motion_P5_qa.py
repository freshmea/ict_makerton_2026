"""Independent isolated headless six-axis SolidCraft P5 motion QA.

Writes only native_motion_P5_qa.* evidence. Never saves or connects to GUI.
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

FILE = ROOT / 'cad/fold_wing_v8_P5_RPY.solidcraft'
SUFFIXES = ['J1_YAW', 'J2_SHOULDER_PITCH', 'J3_WRIST_ROLL']
NAMES = [s + '_' + n for s in ['L', 'R'] for n in SUFFIXES]
GEOMETRY_NAMES=[s+'_'+suffix for s in ['L','R'] for suffix in ['CURVED_ARM_CORE_FRONT_part','CURVED_ARM_CORE_REAR_part','P5_WRIST_SERVO_CASE','P5_WRIST_SHAFT','P5_WRIST_HORN','P5_WRIST_BEARING','P5_WRIST_FIXED_STUB','ROLL_YOKE_PALM_FRONT','ROLL_PALM_REAR','ROLL_BEARING_CAP']]
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
    # Only reset values that changed; unchanged values need no repeated solve.
    for j in healthy(c)['joints']:
        if j['name'] in NAMES and abs(j['values'][0]['value'])>1e-8:
            execute(c,'joint.drive',joint=j['name'],value=0)


def forward(point,side,level,values):
    """World point of stage 1/2/3 after serial rotations; independent math."""
    sg=-1 if side=='L' else 1
    pivots=[[sg*275,40,130],[sg*275,40,180],[sg*220,40,315]]
    axes=[[0,0,1],[0,1,0],[-sg,0,0]]
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
        'joint_frame_tolerance':FRAME_TOLERANCE,'direct_drives':[],'serial_nested_poses':[],'study_playback':[],
        'actual_hand_surface_roll_traces':[]}


def checkpoint(phase):
    report['phase']=phase
    report['accepted']=False
    (HERE/'native_motion_P5_qa.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


checkpoint('opening_saved_native_in_fresh_headless_process')
with ZipFile(FILE) as z:
    assert z.testzip() is None
    doc=json.loads(z.read('document.json'))
    report['native_zip_crc']='pass';report['feature_count']=len(doc['features'])
c=Client(headless=True,timeout=600)
try:
    c.call('inspect_design',{'measure':False,'sketches':False})
    report['first_open']=Client.value(c.call('open',{'path':str(FILE.resolve())}))
    assert not report['first_open'].get('errors') and not report['first_open'].get('warnings')
    jl=healthy(c);rev=[j for j in jl['joints'] if j['type']=='revolute']
    assert {j['name'] for j in rev}==set(NAMES) and len(rev)==6
    assert all(not j['suppressed'] and abs(j['values'][0]['value'])<1e-8 for j in rev)
    assert all(j['values'][0]['limits'][0]<=-10 and j['values'][0]['limits'][1]>=10 for j in rev)
    initial=execute(c,'joint.inspect'); report['initial_joints']=jl;report['initial_joint_inspect']=initial
    by_name={j['name']:j for j in initial['joints'] if j['name'] in NAMES}
    report['neutral_RPY_axes']={}
    for side in ['L','R']:
        vectors=[by_name[side+'_'+n]['a']['frame']['z'] for n in SUFFIXES]
        assert all(abs(sum(vectors[i][k]*vectors[j][k] for k in range(3)))<1e-8 for i,j in [(0,1),(0,2),(1,2)])
        cross=[vectors[1][1]*vectors[2][2]-vectors[1][2]*vectors[2][1],vectors[1][2]*vectors[2][0]-vectors[1][0]*vectors[2][2],vectors[1][0]*vectors[2][1]-vectors[1][1]*vectors[2][0]]
        determinant=sum(vectors[0][k]*cross[k] for k in range(3))
        assert abs(abs(determinant)-1)<1e-8
        report['neutral_RPY_axes'][side]={'joint_order':SUFFIXES,'axis_vectors':vectors,'absolute_basis_determinant':abs(determinant)}
    ids={j['name']:j['b']['occurrence'] for j in initial['joints'] if j['name'] in NAMES}
    assert len(set(ids.values()))==6
    baseline=occurrences(c,ids);report['driven_occurrence_ids']=ids;report['baseline_properties']=baseline
    state=Client.value(c.call('inspect_design',{'measure':True,'sketches':True,'joints':False}))
    assert not [f for f in state['timeline'] if f.get('error') or f.get('warning')]
    assert not [s for s in state['sketches'] if s.get('dof')!=0]
    report['body_count']=len(state['bodies'])
    assert set(GEOMETRY_NAMES)<={b['name'] for b in state['bodies']},set(GEOMETRY_NAMES)-{b['name'] for b in state['bodies']}
    motors=[b for b in state['bodies'] if 'SERVO' in b['name'] and 20000<b['volume_mm3']<50000]
    assert len(motors)==6,[(b['name'],b['volume_mm3']) for b in motors]
    expected_motor_names={s+'_'+suffix for s in ['L','R'] for suffix in ['YAW_SERVO_INSIDE_BASE_part','SHOULDER_SERVO_TRIAL','P5_WRIST_SERVO_CASE']}
    assert {b['name'] for b in motors}==expected_motor_names
    report['six_servo_bodies']=[{'name':b['name'],'volume_mm3':b['volume_mm3'],'bbox':b['bbox']} for b in motors]
    studies=execute(c,'motion.list');report['initial_studies']=studies
    assert len(studies['studies'])==7
    combined=[s for s in studies['studies'] if len(s['keys'])==6]
    assert len(combined)==1
    combined=combined[0]
    assert combined['name']=='P5_SIX_JOINT_RPY_DEMO'
    assert {k['joint'] for k in combined['keys']}=={j['id'] for j in rev}
    assert len([s for s in studies['studies'] if len(s['keys'])==1])==6
    neutral={name:0 for name in NAMES}
    report['neutral_initial']=verify_pose(c,ids,baseline,neutral)
    # A material point away from the shaft shows actual hand roll even when
    # the hand assembly's aggregate centre of mass is close to that shaft.
    for side,sg in [('L',-1),('R',1)]:
        roll=side+'_J3_WRIST_ROLL'
        body=next(b['name'] for b in baseline[roll]['bodies'] if 'ROLL_YOKE_PALM_FRONT' in b['name'])
        topo=Client.value(c.call('body_topology',{'body':body}))
        face=max((f for f in topo['faces'] if 'point' in f),key=lambda f:(f['point'][1]-40)**2+(f['point'][2]-315)**2)
        point=face['point'];radius=math.hypot(point[1]-40,point[2]-315)
        assert radius>5
        trace=execute(c,'motion.trace',occurrence=ids[roll],point=point,joint=roll,**{'from':-10,'to':10},samples=3)
        assert len(trace['points'])==3 and not trace.get('stopped_by_loop') and not trace.get('stopped_by_contact')
        trace_errors=[error(actual,rotate(point,[sg*220,40,315],[-sg,0,0],angle)) for actual,angle in zip(trace['points'],[-10,0,10])]
        assert max(trace_errors)<FRAME_TOLERANCE
        longitudinal_change=max(abs(p[0]-point[0]) for p in trace['points'])
        assert longitudinal_change<FRAME_TOLERANCE
        assert error(trace['points'][1],trace['points'][2])>.5
        bounds=baseline[roll]['total']['bbox'];extent=[bounds['max'][i]-bounds['min'][i] for i in range(3)]
        assert extent[0]>max(extent[1:])+5,(side,extent)
        report['actual_hand_surface_roll_traces'].append({'side':side,'body':body,'face_index':face.get('index'),
            'material_face_point_mm':point,'distance_to_X_roll_axis_mm':radius,'hand_XYZ_extents_mm':extent,
            'angles_deg':[-10,0,10],'trace_points_mm':trace['points'],'analytic_point_errors_mm':trace_errors,
            'longitudinal_X_change_mm':longitudinal_change,
            'material_point_displacement_for_10deg_mm':error(trace['points'][1],trace['points'][2])})
    fixed=execute(c,'occurrence.properties',occurrence='PILL_BASE_TRAY_2_part:1')
    print('PASS: six real neutral revolute axes, six servo envelopes, seven saved studies and healthy grounded assembly',flush=True)
    checkpoint('fresh_reopen_inventory_and_real_roll_trace_passed')
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
        checkpoint('direct_drives_'+str(len(report['direct_drives'])))
    for side in ['L','R']:
        zero(c);values=dict(neutral)
        for suffix in SUFFIXES:
            name=side+'_'+suffix;values[name]=10
            moved=execute(c,'joint.drive',joint=name,value=10)
            assert moved.get('moved')
        result=verify_pose(c,ids,baseline,values)
        report['serial_nested_poses'].append({'side':side,'full_yaw_pitch_roll_pose_deg':[10,10,10],**result})
    zero(c)
    restored=occurrences(c,ids)
    report['neutral_return_max_COM_error_mm']=max(error(centre(restored[n]),centre(baseline[n])) for n in NAMES)
    assert report['neutral_return_max_COM_error_mm']<COM_TOLERANCE
    print('PASS: 12 independent +/-10 degree drives, actual X-roll surface points and two full serial RPY poses',flush=True)
    checkpoint('all_direct_drives_and_two_nested_RPY_poses_passed')
    joint_by_id={j['id']:j for j in rev}
    for key in combined['keys']:
        degrees=[math.degrees(p[1]) for p in key['points']]
        assert abs(min(degrees)+10)<1e-7 and abs(max(degrees)-10)<1e-7
        assert abs(degrees[0])<1e-8 and abs(degrees[-1])<1e-8
    # Each positive key exercises a different real joint. Negative physical
    # movement was already checked above for all six; avoid repeating it here.
    sample_steps=sorted({p[0] for k in combined['keys'] for p in k['points'] if p[1]>1e-8}|{combined['steps']})
    assert len(sample_steps)==7
    for step in sample_steps:
        play=execute(c,'motion.play',study=combined['name'],step=step,quiet=True)
        assert not play.get('unmoved'),play
        expected=study_values(combined,step,joint_by_id)
        result=verify_pose(c,ids,baseline,expected)
        report['study_playback'].append({'step':step,'moved':play.get('moved'),**result})
        checkpoint('study_keyframes_'+str(len(report['study_playback'])))
    assert all(abs(v)<1e-8 for v in report['study_playback'][-1]['actual_values_deg'].values())
    report['final_joints']=healthy(c)
    checkpoint('all_motion_checks_passed_exporting_roll_interfaces')
    # Export physical roll interfaces in this same neutral fresh session.
    geometry_exports={}
    for name in GEOMETRY_NAMES:
        target=HERE/('native_motion_P5_qa.geometry_'+name+'.step')
        c.call('export',{'path':str(target.resolve()),'format':'step','bodies':[name]})
        geometry_exports[name]={'path':target.name,'sha256':sha(target)}
    (HERE/'native_motion_P5_qa.geometry_exports.json').write_text(json.dumps({'native_sha256':file_hash,'exports':geometry_exports},indent=2)+'\n',encoding='utf-8')
except Exception as exc:
    report['failure']=repr(exc)
    checkpoint('failed')
    raise
finally:c.close()
assert sha(FILE)==file_hash,'Saved P5 design changed during isolated QA'
report['fresh_headless_open_count']=1
report['phase']='complete'
report['saved_file_unchanged']=True;report['accepted']=True
report['limitations']=['Servo shapes are CAD envelopes; six motor bodies are not proof of physical installation or actuator operation.',
 'Demo joint limits and +/-10 degree drives are CAD tests, not physical safe limits, collision/load validation or servo-control proof.',
 'COM integration tolerance is 0.001 mm; exact joint origin and axis checks use 1e-6. GUI interaction was not used.']
(HERE/'native_motion_P5_qa.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('PASS: actual X-axis roll and real saved-study playback; one fresh session, native P5 remained unchanged',flush=True)
