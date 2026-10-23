"""Independent final SolidCraft/STEP/STL/manifest correspondence audit.

Uses a fresh isolated headless MCP process for saved-document reopening.
Never connects to or changes the desktop design, and never saves CAD files.
"""
from pathlib import Path
import hashlib
import json
import sys
from zipfile import ZipFile

REPO = Path(__file__).resolve().parents[4]
sys.dont_write_bytecode = True
sys.path.insert(0, str(REPO / 'tmp/cad-runtime'))
import cadquery as cq
import numpy as np
import trimesh
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / 'source'))
from mcp_client import Client


def volume(s):
    if s.wrapped.IsNull():
        return 0.
    prop = GProp_GProps()
    BRepGProp.VolumeProperties_s(s.wrapped, prop, 1e-9, True, False)
    return prop.Mass()


def bounds(s):
    b = s.BoundingBox()
    return np.array([[b.xmin, b.ymin, b.zmin], [b.xmax, b.ymax, b.zmax]])


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def diff(a, b):
    return [volume(a.cut(b)), volume(b.cut(a))]


assembly_path = ROOT / 'cad/fold_wing_v8_P2_assembly.step'
native_path = ROOT / 'cad/fold_wing_v8_P2.solidcraft'
assembly = cq.importers.importStep(str(assembly_path)).val()
solids = assembly.Solids()
manifest = json.loads((ROOT / 'print/manifest.json').read_text(encoding='utf-8'))
exports = json.loads((ROOT / 'evidence/13_exported_parts.json').read_text(encoding='utf-8'))
expected_names = {r['name'] for r in exports} | {'HAND_DOWEL_4x6'}
assert len(expected_names) == 25
assert {p.stem for p in (ROOT / 'stl').glob('*.stl')} == expected_names
assert {r['part'] for r in manifest['parts']} == expected_names
assert manifest['part_count'] == 25 and manifest['all_static_checks_pass']
report = {'assembly_step_sha256': sha(assembly_path), 'native_sha256': sha(native_path),
          'solid_count': len(solids), 'all_step_solids_valid': all(s.isValid() for s in solids),
          'all_step_shells_closed': all(sh.Closed() for s in solids for sh in s.Shells()),
          'all_step_volumes_positive': all(volume(s) > 0 for s in solids),
          'printed_unique_part_count': len(expected_names), 'printed_physical_part_count': 28,
          'parts': [], 'assembly_source_matches': [], 'dowel_matches': []}
assert len(solids) == 53
assert report['all_step_solids_valid'] and report['all_step_shells_closed'] and report['all_step_volumes_positive']
with ZipFile(native_path) as archive:
    assert archive.testzip() is None
    doc = json.loads(archive.read('document.json'))
    report['native_container'] = {'zip_crc': 'pass', 'features': len(doc['features']),
                                  'parameters': len(doc['params']), 'sketch_features': sum(f['type'] == 'sketch' for f in doc['features']),
                                  'format': json.loads(archive.read('container.json'))}
assert report['native_container']['features'] == 179

for name in sorted(expected_names):
    step, stl = ROOT / 'cad' / (name + '.step'), ROOT / 'stl' / (name + '.stl')
    assert step.is_file() and stl.is_file()
    s = cq.importers.importStep(str(step)).val()
    mesh = trimesh.load_mesh(str(stl))
    v, bb = volume(s), bounds(s)
    item = next(r for r in manifest['parts'] if r['part'] == name)
    checks = {'name': name, 'step_sha256': sha(step), 'stl_sha256': sha(stl),
              'valid': s.isValid(), 'closed_shells': all(sh.Closed() for sh in s.Shells()),
              'solid_count': len(s.Solids()), 'volume_mm3': v, 'bounds_mm': bb.tolist(),
              'stl_watertight': bool(mesh.is_watertight), 'stl_is_volume': bool(mesh.is_volume),
              'stl_volume_mm3': float(mesh.volume), 'stl_volume_relative_gap': float(abs(mesh.volume - v) / v),
              'stl_bounds_max_abs_gap_mm': float(np.max(np.abs(mesh.bounds - bb))),
              'manifest_source_hash_match': sha(stl) == item['source_sha256'],
              'manifest_oriented_hash_match': sha(ROOT / item['oriented_stl']) == item['oriented_stl_sha256'],
              'manifest_3mf_hash_match': sha(ROOT / item['model_3mf']) == item['model_3mf_sha256']}
    assert checks['valid'] and checks['closed_shells'] and checks['solid_count'] == 1
    assert checks['stl_watertight'] and checks['stl_is_volume']
    assert checks['stl_volume_relative_gap'] < .005, checks
    assert checks['stl_bounds_max_abs_gap_mm'] < .08, checks
    assert all(checks[k] for k in ['manifest_source_hash_match', 'manifest_oriented_hash_match', 'manifest_3mf_hash_match'])
    if name != 'HAND_DOWEL_4x6':
        candidates = [(i, other) for i, other in enumerate(solids) if np.max(np.abs(bounds(other) - bb)) < 1e-3]
        assert len(candidates) == 1, (name, len(candidates))
        idx, other = candidates[0]
        checks['assembly_solid_index'] = idx
        checks['difference_from_assembly_mm3'] = diff(s, other)
        assert max(checks['difference_from_assembly_mm3']) < 1e-3, checks
    else:
        assert np.allclose(bb, [[-2, -2, 0], [2, 2, 6]], atol=1e-5)
        assert abs(v - 24 * np.pi) < 1e-6
    report['parts'].append(checks)
print('PASS: 53 closed valid assembly solids and 25 native STEP/STL/manifest correspondences', flush=True)

source_base = cq.importers.importStep(str(ROOT / 'cad/base_P2.step')).val().Solids()
for i, original in enumerate(source_base):
    gap = diff(solids[i], original)
    assert max(gap) < 1e-3, (i, gap)
    report['assembly_source_matches'].append({'assembly_solid_index': i, 'source': 'cad/base_P2.step', 'source_solid_index': i, 'symmetric_difference_mm3': gap})
for ix, name in enumerate([s + '_WRAP_HAND_' + h for s in ['L', 'R'] for h in ['FRONT', 'REAR']], 45):
    source = cq.importers.importStep(str(ROOT / 'source/cad' / (name + '.step'))).val()
    gap = diff(solids[ix], source)
    assert max(gap) < 1e-3, (name, gap)
    report['assembly_source_matches'].append({'assembly_solid_index': ix, 'source': 'source/cad/' + name + '.step', 'symmetric_difference_mm3': gap})
for ix, (sg, z) in enumerate([(sg, z) for sg in [-1, 1] for z in [311, 319]], 49):
    expected = cq.Solid.makeCylinder(2, 6, cq.Vector(sg * 160, 37, z), cq.Vector(0, 1, 0))
    gap = diff(solids[ix], expected)
    assert max(gap) < 1e-3
    report['dowel_matches'].append({'assembly_solid_index': ix, 'symmetric_difference_mm3': gap})
print('PASS: full final assembly matches QA-verified base, hands and four dowels', flush=True)

client = Client(headless=True)
try:
    client.call('inspect_design', {'measure': False, 'sketches': False})
    opened = Client.value(client.call('open', {'path': str(native_path.resolve())}))
    report['native_standalone_reopen'] = opened
    assert not opened.get('warnings') and not opened.get('errors'), opened
    state = Client.value(client.call('inspect_design', {'measure': False, 'sketches': True}))
    issues = [f for f in state['timeline'] if f.get('error') or f.get('warning')]
    loose = [s for s in state['sketches'] if s.get('dof') != 0]
    report['native_standalone_inspect'] = {'body_count': len(state['bodies']), 'feature_count': len(state['timeline']),
                                         'sketch_count': len(state['sketches']), 'feature_issues': issues, 'nonzero_dof_sketches': loose}
    assert len(state['bodies']) == 53 and len(state['timeline']) == 179 and len(state['sketches']) == 38
    assert not issues and not loose
    opened_step = Client.value(client.call('open', {'path': str(assembly_path.resolve())}))
    report['assembly_step_standalone_reopen'] = opened_step
    assert not opened_step.get('warnings') and not opened_step.get('errors'), opened_step
finally:
    client.close()
report['accepted'] = True
report['native_sha256'] = sha(native_path)
report['assembly_step_sha256'] = sha(assembly_path)
report['limitations'] = ['CAD topology, native replay and print-placement geometry checks; no slicer import/slicing, material strength, servo motion or physical print/assembly validation.']
(HERE / 'native_final_qa.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print('PASS: isolated standalone SolidCraft native and STEP reopen; 53 bodies / 179 features / 38 sketches at DOF 0', flush=True)
