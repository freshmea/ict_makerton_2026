"""Independent nonpersistent motion QA of the saved SolidCraft P3 assembly.

All drives occur in a fresh isolated headless process. No CAD source, shared
session or saved design is modified. Writes only native_motion_P3_qa.* evidence.
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

FILE = ROOT / 'cad/fold_wing_v8_P3_motion.solidcraft'
NAMES = [s + '_' + j for s in ['L', 'R'] for j in ['J1_YAW', 'J2_PITCH']]
OCC = {s: {'arm': s + '_CURVED_ARM_CORE_FRONT_part:1', 'hand': 'P3_' + s + '_HAND:1'} for s in ['L', 'R']}
REPORT = HERE / 'native_motion_P3_qa.json'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def xyz_error(a, b):
    return math.sqrt(sum((x-y)**2 for x, y in zip(a, b)))


def rotate(p, pivot, axis, deg):
    norm = math.sqrt(sum(x*x for x in axis))
    axis = [x/norm for x in axis]
    angle = math.radians(deg)
    v = [p[i]-pivot[i] for i in range(3)]
    dot = sum(v[i]*axis[i] for i in range(3))
    cross = [axis[1]*v[2]-axis[2]*v[1], axis[2]*v[0]-axis[0]*v[2], axis[0]*v[1]-axis[1]*v[0]]
    return [pivot[i] + v[i]*math.cos(angle) + cross[i]*math.sin(angle) + axis[i]*dot*(1-math.cos(angle)) for i in range(3)]


def execute(c, name, **params):
    return Client.value(c.call('execute', {'command': name, 'params': params}))


def healthy(c):
    result = execute(c, 'joint.list')
    assert not result['errors'] and not result['conflicts'] and not result['floating'], result
    return result


def moving_properties(c):
    return {s: {k: execute(c, 'occurrence.properties', occurrence=v) for k, v in group.items()} for s, group in OCC.items()}


def centre(prop):
    return prop['total']['center_of_mass']


def zero(c):
    for name in NAMES:
        execute(c, 'joint.drive', joint=name, value=0)


assert FILE.is_file(), FILE
before = sha(FILE)
report = {'file': str(FILE.relative_to(ROOT)), 'native_sha256': before, 'qa_scope': 'Fresh headless isolated in-memory drives; no saved-design mutation',
          'analytic_COM_tolerance_mm': 1e-4, 'joint_frame_origin_tolerance_mm': 1e-5,
          'direct_drives': [], 'parent_child': [], 'study_checks': [], 'P2_geometry_baseline': []}
with ZipFile(FILE) as archive:
    assert archive.testzip() is None
    document = json.loads(archive.read('document.json'))
    report['native_zip_crc'] = 'pass'
    report['native_feature_count'] = len(document['features'])
c = Client(headless=True)
try:
    c.call('inspect_design', {'measure': False, 'sketches': False})
    report['first_open'] = Client.value(c.call('open', {'path': str(FILE.resolve())}))
    assert not report['first_open'].get('errors') and not report['first_open'].get('warnings')
    joints = healthy(c)
    revolute = [j for j in joints['joints'] if j['type'] == 'revolute']
    assert {j['name'] for j in revolute} == set(NAMES)
    assert all(abs(j['values'][0]['value']) < 1e-8 for j in revolute), revolute
    assert all(max(abs(x-y) for x,y in zip(j['values'][0]['limits'], [-15,15])) < 1e-8 for j in revolute)
    report['initial_joint_list'] = joints
    report['initial_joint_inspect'] = execute(c, 'joint.inspect')
    report['initial_motion_list'] = execute(c, 'motion.list')
    report['initial_components'] = execute(c, 'component.list', compact=True, bodies=True)
    state = Client.value(c.call('inspect_design', {'measure': True, 'sketches': False, 'joints': False}))
    assert len(state['bodies']) == 53
    assert not [f for f in state['timeline'] if f.get('error') or f.get('warning')]
    old = json.loads((HERE / 'native_motion_P3_qa.P2_diagnosis.json').read_text(encoding='utf-8'))
    old_bodies = {b['name']: b for b in old['P2_baseline_bodies']}
    assert set(old_bodies) == {b['name'] for b in state['bodies']}
    for b in state['bodies']:
        p = old_bodies[b['name']]
        volume_gap = abs(b['volume_mm3']-p['volume_mm3'])
        bbox_gap = max(abs(x-y) for a in ['min', 'max'] for x, y in zip(b['bbox'][a], p['bbox'][a]))
        com_gap = xyz_error(b['center_of_mass'], p['center_of_mass'])
        assert volume_gap < 1e-3 and bbox_gap < 1e-6 and com_gap < 1e-6, (b['name'], volume_gap, bbox_gap, com_gap)
        report['P2_geometry_baseline'].append({'name': b['name'], 'volume_gap_mm3': volume_gap, 'bbox_max_gap_mm': bbox_gap, 'com_gap_mm': com_gap})
    baseline = moving_properties(c)
    report['baseline_properties'] = baseline
    base_reference = execute(c, 'occurrence.properties', occurrence='PILL_BASE_TRAY_2_part:1')
    print('PASS: saved P3 has four neutral revolute joints, grounded chains and unchanged 53-body baseline', flush=True)
    for name in NAMES:
        side = name[0]
        sgn = -1 if side == 'L' else 1
        yaw = name.endswith('YAW')
        pivot, axis = ([sgn*275, 40, 130], [0, 0, 1]) if yaw else ([sgn*220, 40, 315], [0, 1, 0])
        for angle in [10, -10]:
            zero(c)
            driven = execute(c, 'joint.drive', joint=name, value=angle)
            assert driven.get('moved'), (name, angle, driven)
            assert not driven.get('reason') and not driven.get('stopped_by_loop'), driven
            jl = healthy(c)
            actual_value = next(j for j in jl['joints'] if j['name'] == name)['values'][0]['value']
            assert abs(actual_value-angle) < 1e-7
            props = moving_properties(c)
            errors = {}
            for s in ['L', 'R']:
                for role in ['arm', 'hand']:
                    original = centre(baseline[s][role])
                    expected = rotate(original, pivot, axis, angle) if s == side and (yaw or role == 'hand') else original
                    gap = xyz_error(centre(props[s][role]), expected)
                    errors[s+'_'+role] = gap
                    assert gap < 1e-4, (name, angle, s, role, gap, centre(props[s][role]), expected)
            fixed = execute(c, 'occurrence.properties', occurrence='PILL_BASE_TRAY_2_part:1')
            fixed_gap = xyz_error(centre(fixed), centre(base_reference))
            assert fixed_gap < 1e-7
            report['direct_drives'].append({'joint': name, 'command_deg': angle, 'actual_deg': actual_value, 'drive': driven, 'analytic_com_error_mm': errors, 'grounded_tray_com_error_mm': fixed_gap})
    zero(c)
    for side in ['L', 'R']:
        sgn = -1 if side == 'L' else 1
        execute(c, 'joint.drive', joint=side+'_J1_YAW', value=10)
        inspector = execute(c, 'joint.inspect', joint=side+'_J2_PITCH')['joints'][0]
        expected_origin = rotate([sgn*220,40,315], [sgn*275,40,130], [0,0,1], 10)
        frame = inspector['a']['frame']
        axis_expected = [-math.sin(math.radians(10)), math.cos(math.radians(10)), 0]
        pivot_error = xyz_error(frame['origin'], expected_origin)
        axis_error = xyz_error(frame['z'], axis_expected)
        assert pivot_error < 1e-5 and axis_error < 1e-7, (side, frame, expected_origin)
        # Drive the wrist after the yaw. Its physical axis must follow the arm.
        prior = moving_properties(c)
        second = execute(c, 'joint.drive', joint=side+'_J2_PITCH', value=10)
        assert second.get('moved')
        after_props = moving_properties(c)
        expected_hand = rotate(centre(prior[side]['hand']), expected_origin, axis_expected, 10)
        nested_error = xyz_error(centre(after_props[side]['hand']), expected_hand)
        assert nested_error < 1e-4
        healthy(c)
        report['parent_child'].append({'side': side, 'parent_yaw_deg': 10, 'child_pitch_deg': 10, 'world_pitch_joint_origin_error_mm': pivot_error, 'world_pitch_joint_axis_vector_error': axis_error, 'nested_hand_com_error_mm': nested_error})
        zero(c)
    neutral = moving_properties(c)
    report['neutral_return_max_com_error_mm'] = max(xyz_error(centre(neutral[s][role]), centre(baseline[s][role])) for s in ['L','R'] for role in ['arm','hand'])
    assert report['neutral_return_max_com_error_mm'] < 1e-4
    # A real saved motion study must play and return to the neutral endpoint.
    for step in [5, 10, 25, 30, 45, 50, 65, 70, 80]:
        result = execute(c, 'motion.play', study='P3_FOUR_JOINT_DEMO', step=step, quiet=True)
        jl = healthy(c)
        values = {j['name']: j['values'][0]['value'] for j in jl['joints'] if j['type'] == 'revolute'}
        target = next((name for name, offset in zip(NAMES,[0,20,40,60]) if step in [offset+5,offset+10]), None)
        for name, value in values.items():
            expected = (10 if step % 20 == 5 else -10) if name == target else 0
            assert abs(value-expected) < 1e-7, (step, values)
        assert step == 80 or result.get('moved'), (step,result)
        assert not result.get('unmoved'), result
        report['study_checks'].append({'step': step, 'values_deg': values, 'moved': result.get('moved'), 'unmoved': result.get('unmoved',[])})
    report['final_joint_list'] = healthy(c)
    print('PASS: eight +/-10-degree drives, analytical movement, parent/child following, neutral return and real motion-study playback', flush=True)
finally:
    c.close()
assert sha(FILE) == before, 'Saved P3 file changed during nonpersistent QA'

# Reopen in another new process to prove joints, grounding and studies survive
# closure independently of the in-memory drive session.
c = Client(headless=True)
try:
    c.call('inspect_design', {'measure':False, 'sketches':False})
    report['second_open'] = Client.value(c.call('open', {'path':str(FILE.resolve())}))
    persisted = healthy(c)
    revolute = [j for j in persisted['joints'] if j['type'] == 'revolute']
    assert {j['name'] for j in revolute} == set(NAMES)
    assert all(abs(j['values'][0]['value']) < 1e-8 and max(abs(x-y) for x,y in zip(j['values'][0]['limits'], [-15,15])) < 1e-8 for j in revolute)
    studies = execute(c,'motion.list')
    assert studies == report['initial_motion_list']
    report['persisted_joint_list'] = persisted
    report['persisted_motion_list'] = studies
finally:
    c.close()
assert sha(FILE) == before
report['saved_file_unchanged'] = True
report['accepted'] = True
report['limitations'] = ['Joint limits +/-15 deg and demonstration drives +/-10 deg are CAD examples, not physical servo or collision-safe limits.', 'No actuator simulation, material strength, dynamic contact/load or actual hardware motion proof.']
REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('PASS: fresh reopen preserves neutral joints, grounding and motion studies; saved file unchanged', flush=True)
