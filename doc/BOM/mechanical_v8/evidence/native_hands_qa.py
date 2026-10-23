"""Read-only independent QA of four native hand STEP and mesh exports."""
from pathlib import Path
import hashlib
import json
import math
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
CAD = HERE.parent / 'source/cad'


def volume(shape):
    if shape.wrapped.IsNull():
        return 0.
    prop = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape.wrapped, prop, 1e-9, True, False)
    return prop.Mass()


def bounds(shape):
    b = shape.BoundingBox()
    return np.array([[b.xmin, b.ymin, b.zmin], [b.xmax, b.ymax, b.zmax]])


base = cq.importers.importStep(str(HERE.parent / 'cad/base_P2.step')).val().Solids()
report = {'method': 'Independent OCCT and trimesh STEP/STL import; high precision adaptive volume integration eps=1e-9; mirror, point, fit and static-interference checks',
          'parts': [], 'symmetry': [], 'static_intersections': [], 'dowels': []}
hands = {}
for side in ['L', 'R']:
    for half in ['FRONT', 'REAR']:
        name = side + '_WRAP_HAND_' + half
        step = CAD / (name + '.step')
        native = CAD / (name + '.solidcraft')
        stl = CAD / (name + '.stl')
        shape = cq.importers.importStep(str(step)).val()
        mesh = trimesh.load_mesh(str(stl))
        hands[name] = shape
        bb = bounds(shape)
        v = volume(shape)
        with ZipFile(native) as archive:
            assert archive.testzip() is None
            doc = json.loads(archive.read('document.json'))
            params = {p['name']: p['expr'] for p in doc['params']}
        rec = {'name': name, 'step_sha256': hashlib.sha256(step.read_bytes()).hexdigest(),
               'native_sha256': hashlib.sha256(native.read_bytes()).hexdigest(),
               'stl_sha256': hashlib.sha256(stl.read_bytes()).hexdigest(),
               'valid': shape.isValid(), 'closed_shells': all(s.Closed() for s in shape.Shells()),
               'solid_count': len(shape.Solids()), 'volume_mm3': v, 'bounds_mm': bb.tolist(),
               'stl_watertight': bool(mesh.is_watertight), 'stl_is_volume': bool(mesh.is_volume),
               'stl_volume_mm3': float(mesh.volume), 'stl_volume_relative_gap': float(abs(mesh.volume - v) / v),
               'stl_bbox_max_abs_gap_mm': float(np.max(np.abs(mesh.bounds - bb))),
               'native_zip_crc': 'pass', 'native_features': len(doc['features']),
               'native_parameters': params}
        assert rec['valid'] and rec['closed_shells'] and rec['solid_count'] == 1
        assert v > 0 and rec['stl_watertight'] and rec['stl_is_volume']
        assert rec['stl_volume_relative_gap'] < .002
        assert rec['stl_bbox_max_abs_gap_mm'] < .05
        # Each bridge has the specified two free through-bores and two blind
        # alignment sockets; check actual material on both sides of each bore.
        sg = -1 if side == 'L' else 1
        probes = []
        for z in [310, 320]:
            p = (sg * 170, 25 if half == 'FRONT' else 55, z)
            probes.append({'point_mm': p, 'role': 'M3 bore free centre', 'inside': shape.isInside(cq.Vector(*p))})
            material = (sg * 170, p[1], z + 2.0)
            probes.append({'point_mm': material, 'role': 'material beside M3 bore', 'inside': shape.isInside(cq.Vector(*material))})
        for z in [311, 319]:
            p = (sg * 160, 38.5 if half == 'FRONT' else 41.5, z)
            probes.append({'point_mm': p, 'role': 'blind socket free centre', 'inside': shape.isInside(cq.Vector(*p))})
            closed = (sg * 160, 36.6 if half == 'FRONT' else 43.4, z)
            probes.append({'point_mm': closed, 'role': 'socket blind bottom material', 'inside': shape.isInside(cq.Vector(*closed))})
        for probe in probes:
            assert probe['inside'] == ('material' in probe['role']), (name, probe)
        rec['feature_probes'] = probes
        report['parts'].append(rec)
        for idx, other in enumerate(base):
            overlap = volume(shape.intersect(other))
            if overlap > 1e-4:
                report['static_intersections'].append({'hand': name, 'base_solid_index': idx, 'overlap_mm3': overlap})
for half in ['FRONT', 'REAR']:
    left = hands['L_WRAP_HAND_' + half].mirror('YZ')
    right = hands['R_WRAP_HAND_' + half]
    delta = {'half': half, 'mirrored_left_minus_right_mm3': volume(left.cut(right)),
             'right_minus_mirrored_left_mm3': volume(right.cut(left))}
    assert max(delta['mirrored_left_minus_right_mm3'], delta['right_minus_mirrored_left_mm3']) < 1e-4
    report['symmetry'].append(delta)
for side in ['L', 'R']:
    front, rear = [hands[side + '_WRAP_HAND_' + half] for half in ['FRONT', 'REAR']]
    assert volume(front.intersect(rear)) < 1e-4
    sg = -1 if side == 'L' else 1
    for n, z in enumerate([311, 319], 1):
        peg = cq.Solid.makeCylinder(2, 6, cq.Vector(sg * 160, 37, z), cq.Vector(0, 1, 0))
        overlaps = [volume(peg.intersect(h)) for h in [front, rear]]
        assert max(overlaps) < 1e-4
        report['dowels'].append({'name': side + '_HAND_DOWEL_' + str(n), 'analytic_volume_mm3': 24 * math.pi,
                                 'diameter_mm': 4, 'length_mm': 6,
                                 'front_rear_intersection_mm3': overlaps,
                                 'nominal_diametral_clearance_mm': .4, 'total_axial_blind_bottom_clearance_mm': .4})
assert not report['static_intersections'], report['static_intersections']
report['accepted'] = True
report['limitations'] = ['Static CAD/mesh checks only; material strength, dynamic servo sweep, physical hardware fit and actual slicing/printing are unverified.']
(HERE / 'native_hands_qa.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print('PASS: native hand solids, STL meshes, mirror equivalence, bores, blind dowel pockets, dowel assembly clearance and static interference.')
