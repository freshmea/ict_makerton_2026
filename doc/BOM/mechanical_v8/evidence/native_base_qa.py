"""Independent read-only OCCT QA of the SolidCraft native base export.

Writes this agent's QA report only. Does not create or modify CAD geometry.
Run from repository root with the pre-existing Python 3.9 CAD runtime.
"""
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
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'cad/base_P2.step'
OLD = REPO / 'doc/BOM/mechanical_v7/cad'


def volume(s):
    if s.wrapped.IsNull():
        return 0.0
    prop = GProp_GProps()
    BRepGProp.VolumeProperties_s(s.wrapped, prop, 1e-9, True, False)
    return prop.Mass()


def bbox(s):
    b = s.BoundingBox()
    return [b.xmin, b.ymin, b.zmin, b.xmax, b.ymax, b.zmax]


def box(w, d, h, c):
    return cq.Workplane('XY').box(w, d, h).translate(c).val()


def cylinder(d, h, b):
    return cq.Solid.makeCylinder(d / 2, h, cq.Vector(*b))


def difference(a, b):
    return {'a_minus_b_mm3': volume(a.cut(b)), 'b_minus_a_mm3': volume(b.cut(a))}


solids = cq.importers.importStep(str(BASE)).val().Solids()
old_assembly = cq.importers.importStep(str(OLD / 'fold_wing_v7_P1_assembly.step')).val().Solids()
assert len(solids) == 45, len(solids)
report = {
    'source': str(BASE.relative_to(REPO)),
    'source_sha256': hashlib.sha256(BASE.read_bytes()).hexdigest(),
    'method': 'Independent OCCT import; BRep validity and adaptive volume integration eps=1e-9; Boolean comparisons to world-coordinate v7 assembly STEP with expected native cuts. Closedness checks each solid shell, since OCCT solid Closed flags are unset for both source and export.',
    'solid_count': len(solids),
    'all_solids_valid': all(s.isValid() for s in solids),
    'all_solid_shells_closed': all(sh.Closed() for s in solids for sh in s.Shells()),
    'all_volumes_positive': all(volume(s) > 0 for s in solids),
    'trays': [], 'lids': [], 'splices': [], 'interferences_mm3': [],
}
native_path = BASE.with_suffix('.solidcraft')
with ZipFile(native_path) as archive:
    assert archive.testzip() is None
    document = json.loads(archive.read('document.json'))
    report['native_container'] = {
        'path': str(native_path.relative_to(REPO)),
        'sha256': hashlib.sha256(native_path.read_bytes()).hexdigest(),
        'zip_crc': 'pass', 'format': json.loads(archive.read('container.json')),
        'feature_count': len(document['features']),
        'parameters': document['params'],
        'all_features_unsuppressed': all(not f.get('suppressed', False) for f in document['features']),
    }
    assert len(document['params']) == 8
    assert {p['name']: p['expr'] for p in document['params']}['splice_L'] == '48 mm'

for i, idx in enumerate([0, 2, 4], 1):
    original = old_assembly[idx]
    expected = original
    for seam_i, sx in enumerate([-106.6666667, 106.6666667], 1):
        if i not in [seam_i, seam_i + 1]:
            continue
        dx = -12 if i == seam_i else 12
        key_dx = -8 if i == seam_i else 8
        for side, yy in [('FRONT', -62), ('REAR', 62)]:
            for dy in [-14, 14]:
                x, y = sx + dx, yy + dy
                if side == 'FRONT':
                    expected = expected.cut(cylinder(3.4, 6, (x, y, -1)))
                expected = expected.cut(box(6.4, 6.4, 3.2, (x, y, .6)))
            expected = expected.cut(cylinder(4.4, 3.3, (sx + key_dx, yy, 1.7)))
    actual = solids[idx]
    change = original.cut(actual)
    entry = {'name': 'PILL_BASE_TRAY_' + str(i), 'valid': actual.isValid(),
             'closed_shells': all(sh.Closed() for sh in actual.Shells()), 'solids': len(actual.Solids()),
             'volume_mm3': volume(actual), 'removed_mm3': volume(change),
             'added_mm3': volume(actual.cut(original)),
             'difference_from_expected': difference(actual, expected)}
    report['trays'].append(entry)
    assert entry['added_mm3'] < 1e-3
    assert max(entry['difference_from_expected'].values()) < 1e-3, entry
    lid = solids[idx + 1]
    lid_old = old_assembly[idx + 1]
    delta = difference(lid, lid_old)
    report['lids'].append({'name': 'PILL_BASE_LID_' + str(i), 'difference_from_v7': delta})
    assert max(delta.values()) < 1e-3

analytic = 48 * 44 * 8 - 4 * math.pi * 1.7 ** 2 * 8 - 4 * (5.8 ** 2 - math.pi * 1.7 ** 2) * 2.2 + 2 * math.pi * 2 ** 2 * 2
for ix, sx in enumerate([-106.6666667, 106.6666667]):
    for j, (side, yy) in enumerate([('FRONT', -62), ('REAR', 62)]):
        name = 'SEAM_SPLICE_' + str(ix + 1) + '_' + side
        actual = solids[41 + ix * 2 + j]
        expected = box(48, 44, 8, (sx, yy, 8))
        for dx in [-12, 12]:
            for dy in [-14, 14]:
                x, y = sx + dx, yy + dy
                expected = expected.cut(cylinder(3.4, 10, (x, y, 3)))
                expected = expected.cut(box(5.8, 5.8, 3.2, (x, y, 11.4)))
        for dx in [-8, 8]:
            expected = expected.fuse(cylinder(4, 3, (sx + dx, yy, 2)))
        v = volume(actual)
        delta = difference(actual, expected)
        report['splices'].append({'name': name, 'valid': actual.isValid(), 'closed_shells': all(sh.Closed() for sh in actual.Shells()),
             'solid_count': len(actual.Solids()), 'bbox_mm': bbox(actual), 'volume_mm3': v,
             'analytic_mm3': analytic, 'analytic_error_mm3': v - analytic,
             'difference_from_expected': delta})
        assert actual.isValid() and all(sh.Closed() for sh in actual.Shells()) and len(actual.Solids()) == 1
        assert abs(v - analytic) < 1e-6
        assert max(delta.values()) < 1e-3
        for k, other in enumerate(solids[:41]):
            common = volume(actual.intersect(other))
            if common > 1e-3:
                report['interferences_mm3'].append({'splice': name, 'other_solid_index': k, 'overlap_mm3': common})

report['speaker_envelope_bounds_mm'] = bbox(solids[6])
report['splice_top_z_mm'] = 12
report['speaker_bottom_z_mm'] = 16
report['speaker_bottom_clearance_mm'] = 4
report['power_reserved_bounds_mm'] = bbox(solids[14])
report['battery_reserved_bounds_mm'] = bbox(solids[15])
report['power_reserved_bottom_clearance_mm'] = bbox(solids[14])[2] - 12
report['battery_reserved_bottom_clearance_mm'] = bbox(solids[15])[2] - 12
assert len(report['interferences_mm3']) == 0, report['interferences_mm3']
assert abs(report['power_reserved_bottom_clearance_mm'] - 2) < 1e-5
assert abs(report['battery_reserved_bottom_clearance_mm'] - 2) < 1e-5
report['notes'] = [
    'Indices 14 and 15 in base_P2 STEP are the POWER_RESERVED_ZONE and BATTERY_RESERVED_ZONE conceptual box placeholders, not printable geometry or verified hardware.',
    'Power/battery reserved envelopes raised 6 mm from P1; bottom Z=14 leaves 2 mm above the rear splice Z=12. Actual hardware/support layout still needs physical fit review.',
    'Checks prove CAD topology and geometric equivalence only, not physical screw engagement, material strength, slicer success or printed fit.',
]
(HERE / 'native_base_qa.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
print(json.dumps(report, indent=2))
