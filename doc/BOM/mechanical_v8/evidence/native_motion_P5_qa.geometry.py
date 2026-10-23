"""Read-only OCCT verification of actual P5 X-axis roll interfaces.

Consumes hashed neutral STEP exports from the same fresh motion-QA session.
Does not open or alter the GUI, CAD source, saved P4 or saved P5 files.
"""
from pathlib import Path
import hashlib
import json
import math
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
sys.path.insert(0,str(ROOT.parents[2]/'tmp/cad-runtime'))
import cadquery as cq
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps

FILE=ROOT/'cad/fold_wing_v8_P5_RPY.solidcraft'


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def volume(s):
    if s.wrapped.IsNull():return 0.
    p=GProp_GProps();BRepGProp.VolumeProperties_s(s.wrapped,p,1e-9,True,False)
    return p.Mass()


def cylinder_faces(shape,pivot):
    result=[]
    for i,face in enumerate(shape.Faces()):
        adaptor=BRepAdaptor_Surface(face.wrapped,True)
        if adaptor.GetType()!=GeomAbs_Cylinder:continue
        cyl=adaptor.Cylinder();ax=cyl.Axis();loc=ax.Location();d=ax.Direction()
        origin=[loc.X(),loc.Y(),loc.Z()];axis=[d.X(),d.Y(),d.Z()]
        v=[origin[j]-pivot[j] for j in range(3)]
        cross=[v[1]*axis[2]-v[2]*axis[1],v[2]*axis[0]-v[0]*axis[2],v[0]*axis[1]-v[1]*axis[0]]
        result.append({'face_index':i,'radius_mm':cyl.Radius(),'origin_mm':origin,'axis':axis,
                       'axis_line_distance_from_wrist_pivot_mm':math.sqrt(sum(x*x for x in cross)),
                       'parallel_to_X':abs(abs(axis[0])-1)<1e-8})
    return result


bundle=json.loads((HERE/'native_motion_P5_qa.geometry_exports.json').read_text(encoding='utf-8'))
assert sha(FILE)==bundle['native_sha256']
shapes={}
report={'native_sha256':bundle['native_sha256'],'method':'Independent OCCT B-rep topology and Boolean intersections from hashed native neutral exports',
        'parts':[],'wrist_interfaces':[]}
for name,item in bundle['exports'].items():
    path=HERE/item['path'];assert sha(path)==item['sha256']
    shape=cq.importers.importStep(str(path)).val();shapes[name]=shape
    assert shape.isValid() and len(shape.Solids())==1 and all(sh.Closed() for sh in shape.Shells()) and volume(shape)>0,name
    report['parts'].append({'name':name,'sha256':item['sha256'],'valid_closed_one_solid':True,'volume_mm3':volume(shape)})
for side,sg in [('L',-1),('R',1)]:
    pivot=[sg*220,40,315]
    cores=[shapes[side+'_CURVED_ARM_CORE_'+h+'_part'] for h in ['FRONT','REAR']]
    hands=[shapes[side+'_'+n] for n in ['ROLL_YOKE_PALM_FRONT','ROLL_PALM_REAR','ROLL_BEARING_CAP']]
    hardware={n:shapes[side+'_P5_WRIST_'+n] for n in ['SERVO_CASE','SHAFT','HORN','BEARING','FIXED_STUB']}
    cyls={name:cylinder_faces(shape,pivot) for name,shape in shapes.items() if name.startswith(side+'_')}
    for body,faces in cyls.items():
        for face in faces:face['body']=body
    rec={'side':side,'joint_roll_axis_inward':[ -sg,0,0],'wrist_pivot_mm':pivot,'hardware_cylinder_axes':{},'static_pairs':[]}
    for suffix,radii in [('SHAFT',[3]),('HORN',[1.6]),('BEARING',[2.5,8,9]),('FIXED_STUB',[2.45,4])]:
        candidates=cyls[side+'_P5_WRIST_'+suffix]
        selected=[]
        for radius in radii:
            matches=[f for f in candidates if abs(f['radius_mm']-radius)<1e-5 and f['parallel_to_X'] and f['axis_line_distance_from_wrist_pivot_mm']<1e-5]
            assert matches,(side,suffix,radius,candidates)
            selected.extend(matches)
        rec['hardware_cylinder_axes'][suffix]=selected
    core_faces=[f for name,faces in cyls.items() if 'CURVED_ARM_CORE_' in name for f in faces]
    rec['fixed_core_coaxial_X_faces']=[f for f in core_faces if f['parallel_to_X'] and f['axis_line_distance_from_wrist_pivot_mm']<1e-5 and f['radius_mm']>=35]
    assert any(abs(f['radius_mm']-40)<1e-5 for f in rec['fixed_core_coaxial_X_faces'])
    assert any(abs(f['radius_mm']-37)<1e-5 for f in rec['fixed_core_coaxial_X_faces'])
    assert not [f for f in core_faces if f['radius_mm']>=30 and not f['parallel_to_X'] and f['axis_line_distance_from_wrist_pivot_mm']<1e-5],(side,'Old large transverse wrist cylinder remains')
    hand_faces=[f for name,faces in cyls.items() if 'ROLL_' in name for f in faces]
    rec['moving_cap_coaxial_X_faces']=[f for f in hand_faces if f['parallel_to_X'] and f['axis_line_distance_from_wrist_pivot_mm']<1e-5 and f['radius_mm']>40]
    assert rec['moving_cap_coaxial_X_faces']
    assert any(f['parallel_to_X'] and f['axis_line_distance_from_wrist_pivot_mm']<1e-5 and abs(f['radius_mm']-8.15)<1e-5 for f in hand_faces),(side,'Missing X-axis bearing seat in moving hand')
    servo=hardware['SERVO_CASE'];bb=servo.BoundingBox()
    dims=[bb.xlen,bb.ylen,bb.zlen]
    assert max(abs(x-y) for x,y in zip(dims,[40,40.5,20.2]))<1e-5,(side,dims)
    case_centre=[(bb.xmin+bb.xmax)/2,(bb.ymin+bb.ymax)/2,(bb.zmin+bb.zmax)/2]
    assert max(abs(x-y) for x,y in zip(case_centre,[sg*220,30.25,315]))<1e-5,(side,case_centre)
    rec['servo_case_XYZ_dimensions_mm']=dims
    rec['servo_case_centre_mm']=case_centre
    # Coupled shaft/horn contact is intentional. Check them against printed
    # fixed and moving structures, where unwanted overlap would block roll.
    pairs=[]
    for i,core in enumerate(cores):
        for j,hand in enumerate(hands):pairs.append(('fixed_core_'+str(i),'moving_hand_'+str(j),core,hand))
        for name,part in hardware.items():pairs.append(('fixed_core_'+str(i),name,core,part))
    for j,hand in enumerate(hands):
        for name,part in hardware.items():pairs.append(('moving_hand_'+str(j),name,hand,part))
    pairs += [('fixed_front','fixed_rear',*cores),('bearing','fixed_stub',hardware['BEARING'],hardware['FIXED_STUB'])]
    pairs += [('moving_part_'+str(i),'moving_part_'+str(j),hands[i],hands[j]) for i in range(len(hands)) for j in range(i+1,len(hands))]
    for a,b,s1,s2 in pairs:
        common=volume(s1.intersect(s2))
        assert abs(common)<1e-4,(side,a,b,common)
        rec['static_pairs'].append({'a':a,'b':b,'intersection_mm3':common})
    rec['minimum_core_to_moving_hand_gap_mm']=min(a.distance(b) for a in cores for b in hands)
    assert rec['minimum_core_to_moving_hand_gap_mm']>=.99999,rec['minimum_core_to_moving_hand_gap_mm']
    report['wrist_interfaces'].append(rec)
assert sha(FILE)==bundle['native_sha256']
report['saved_file_unchanged']=True;report['accepted']=True
report['limitations']=['Neutral CAD fit only; no physical servo installation, print-fit, dynamic collision/load or actual actuator proof.']
(HERE/'native_motion_P5_qa.geometry.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('PASS: actual X-axis shaft/horn/bearing/core/hand-cap geometry and zero unwanted neutral wrist intersections',flush=True)
