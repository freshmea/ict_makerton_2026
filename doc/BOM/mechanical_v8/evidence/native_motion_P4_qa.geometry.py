"""Independent static shoulder fit QA via isolated native exports and OCCT.

Run after motion QA. Saved CAD files and the desktop session are not changed.
Exports only this agent's evidence files under native_motion_P4_qa.*.
"""
from pathlib import Path
import hashlib
import json
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
REPO=ROOT.parents[2]
sys.path.insert(0,str(ROOT/'source'))
sys.path.insert(0,str(REPO/'tmp/cad-runtime'))
from mcp_client import Client
import cadquery as cq
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

FILE=ROOT/'cad/fold_wing_v8_P4_6servo.solidcraft'


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def volume(s):
    if s.wrapped.IsNull():return 0.
    p=GProp_GProps();BRepGProp.VolumeProperties_s(s.wrapped,p,1e-9,True,False)
    return p.Mass()


names=[s+'_'+suffix for s in ['L','R'] for suffix in ['SHOULDER_YAW_TURRET','SHOULDER_SERVO_TRIAL','CURVED_ARM_CORE_FRONT_part','CURVED_ARM_CORE_REAR_part','ROUND_YAW_COLLAR_TRIAL_part']]
before=sha(FILE)
paths={name:HERE/('native_motion_P4_qa.geometry_'+name+'.step') for name in names}
bundle_path=HERE/'native_motion_P4_qa.geometry_exports.json'
reused=False
if bundle_path.is_file():
    bundle=json.loads(bundle_path.read_text(encoding='utf-8'))
    reused=bundle['native_sha256']==before and set(bundle['exports'])==set(names) and all(paths[n].is_file() and sha(paths[n])==bundle['exports'][n]['sha256'] for n in names)
if not reused:
    c=Client(headless=True,timeout=240)
    try:
        c.call('inspect_design',{'measure':False,'sketches':False})
        opened=Client.value(c.call('open',{'path':str(FILE.resolve())}))
        assert not opened.get('errors') and not opened.get('warnings')
        for name,p in paths.items():
            c.call('export',{'path':str(p.resolve()),'format':'step','bodies':[name]})
    finally:c.close()
assert sha(FILE)==before
shapes={name:cq.importers.importStep(str(p)).val() for name,p in paths.items()}
report={'native_sha256':before,'saved_native_unchanged':True,'reused_hashed_exports_from_second_fresh_motion_QA_reopen':reused,'independent_native_exports':[],'shoulders':[]}
for name,s in shapes.items():
    assert s.isValid() and len(s.Solids())==1 and all(sh.Closed() for sh in s.Shells()) and volume(s)>0,name
    report['independent_native_exports'].append({'name':name,'step_sha256':sha(paths[name]),'valid':True,'one_closed_solid':True,'volume_mm3':volume(s)})
for side,sg in [('L',-1),('R',1)]:
    turret=shapes[side+'_SHOULDER_YAW_TURRET']
    servo=shapes[side+'_SHOULDER_SERVO_TRIAL']
    collar=shapes[side+'_ROUND_YAW_COLLAR_TRIAL_part']
    reference=cq.Solid.makeCylinder(40,54,cq.Vector(sg*275,13,180),cq.Vector(0,1,0))
    middle=cq.Workplane('XY').box(1000,54,1000).translate((0,40,400)).val()
    rec={'side':side,'servo_vs_turret_intersection_mm3':volume(servo.intersect(turret)),
         'turret_vs_yaw_collar_intersection_mm3':volume(turret.intersect(collar)),
         'yaw_collar_top_z_mm':collar.BoundingBox().zmax,'moving_halves':[]}
    assert rec['servo_vs_turret_intersection_mm3']<1e-4
    assert rec['turret_vs_yaw_collar_intersection_mm3']<1e-4
    for half in ['FRONT','REAR']:
        arm=shapes[side+'_CURVED_ARM_CORE_'+half+'_part']
        bridge_band=arm.intersect(middle)
        bridge_overlap=volume(bridge_band.intersect(reference))
        radial_gap=bridge_band.distance(reference)
        bottom=arm.BoundingBox().zmin
        item={'half':half,'fixed_turret_intersection_mm3':volume(arm.intersect(turret)),
              'servo_case_intersection_mm3':volume(arm.intersect(servo)),
              'yaw_collar_intersection_mm3':volume(arm.intersect(collar)),
              'moving_cap_bottom_z_mm':bottom,'cap_to_yaw_collar_vertical_gap_mm':bottom-collar.BoundingBox().zmax,
              'bridge_band_y_range_mm':[13,67],'reference_core_radius_mm':40,
              'bridge_vs_reference_core_intersection_mm3':bridge_overlap,
              'bridge_to_R40_core_gap_mm':radial_gap,'bridge_min_radial_distance_mm':40+radial_gap}
        assert max(item[k] for k in ['fixed_turret_intersection_mm3','servo_case_intersection_mm3','yaw_collar_intersection_mm3','bridge_vs_reference_core_intersection_mm3'])<1e-4,item
        assert abs(bottom-136)<1e-5 and abs(item['cap_to_yaw_collar_vertical_gap_mm']-1)<1e-5,item
        assert abs(radial_gap-1)<1e-5,item
        rec['moving_halves'].append(item)
    report['shoulders'].append(rec)
report['accepted']=True
report['limitations']=['Neutral CAD pose only; nominal geometric gaps do not prove printed fit, fastener retention, collision-free motion, load capacity or physical assembly.']
(HERE/'native_motion_P4_qa.geometry.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('PASS: native shoulders closed; zero static fixed/moving and servo intersections; 1 mm radial and cap/collar clearances',flush=True)
