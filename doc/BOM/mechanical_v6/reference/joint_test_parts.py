"""Make removable fit trials; dimensions in mm. Not final lamp robot parts."""
import sys,json,pathlib,hashlib,struct
HERE=pathlib.Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'tmp/cad-runtime'))
import cadquery as cq
OUT=HERE/'joint_test_parts';OUT.mkdir(exist_ok=True)
def measure(name,s,params):
    bb=s.val().BoundingBox()
    result={'name':name,'purpose':'fit coupon only; physical fit, fasteners, printer compensation and servo mounting pattern must be measured before final design','parameters_mm':params,'valid':s.val().isValid(),'solids':len(s.val().Solids()),'bbox_mm':[bb.xlen,bb.ylen,bb.zlen],'volume_mm3':s.val().Volume(),'files':[]}
    for ext in ['step','stl']:
        p=OUT/(name+'.'+ext);cq.exporters.export(s,str(p));result['files'].append({'name':p.name,'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    assert result['valid'] and result['solids']==1
    def inside(x,y,z):return s.val().isInside(cq.Vector(x,y,z),1e-6)
    if name=='servo_fit_trial':
        checks={'slot_center_is_open':not inside(0,0,2),'slot_end_is_open':not inside(20.64,0,2),'slot_adjacent_material_exists':inside(21,0,2),'all_4_holes_are_open':all(not inside(x,y,2)for x in[-24.75,24.75]for y in[-5,5]),'plate_edge_material_exists':inside(29,0,2)}
    else:
        tests=[(-33,15.9),(-11,16),(11,16.1),(33,16.3)]
        checks={'all_4_bore_centers_are_open':all(not inside(x,0,2)for x,d in tests),'bores_have_specified_edge':all(not inside(x+d/2-.02,0,2)and inside(x+d/2+.02,0,2)for x,d in tests),'all_4_flange_counterbores_are_open':all(not inside(x+9.08,0,5.5)for x,d in tests),'material_beyond_counterbores_exists':all(inside(x+9.12,0,5.5)for x,d in tests),'counterbore_bottom_material_exists':all(inside(x+8.9,0,4.7)for x,d in tests)}
    assert all(checks.values()),checks
    result['geometric_checks']=checks
    svg=OUT/(name+'.svg');cq.exporters.export(s,str(svg),opt={'projectionDir':(0,0,1),'showHidden':False,'showAxes':False,'width':1000,'height':400})
    return result
servo=cq.Workplane('XY').box(60,35,4,centered=(True,True,False)).faces('>Z').workplane().rect(41.3,21.0).cutThruAll()
servo=servo.faces('>Z').workplane().pushPoints([(x,y)for x in [-24.75,24.75]for y in[-5,5]]).hole(3.4)
# Labels on wide margins; engraved0.35mm deep, no protruding geometry.
servo=servo.cut(cq.Workplane('XY').workplane(offset=4).center(0,14.3).text('41.3 x 21.0',2.8,-.35,combine=True,font='Arial'))
servo=servo.cut(cq.Workplane('XY').workplane(offset=4).center(0,-14.3).text('49.5 x 10 VERIFY',2.2,-.35,combine=True,font='Arial'))
results=[measure('servo_fit_trial',servo,{'plate':[60,35,4],'opening':[41.3,21.0],'servo_nominal_body':[40.5,20.2],'total_opening_clearance':.8,'holes_diameter':3.4,'mounting_hole_centers':[[-24.75,-5],[-24.75,5],[24.75,-5],[24.75,5]],'supplier_mounting_pitch':[49.5,10],'minimum_nominal_ligament_hole_to_opening':2.4})]
bearing=cq.Workplane('XY').box(94,30,6,centered=(True,True,False))
for x,diam in [(-33,15.9),(-11,16.0),(11,16.1),(33,16.3)]:
    #Use global origin to avoid faceworkplane relative origin shifts.
    bore=cq.Workplane('XY').center(x,0).circle(diam/2).extrude(6)
    seat=cq.Workplane('XY').workplane(offset=4.8).center(x,0).circle(9.1).extrude(1.2)
    bearing=bearing.cut(bore).cut(seat)
    label=cq.Workplane('XY').workplane(offset=6).center(x,12).text(str(diam),2.6,-.35,combine=True,font='Arial')
    bearing=bearing.cut(label)
results.append(measure('F625ZZ_bearing_fit_trial',bearing,{'plate':[94,30,6],'bore_diameters':[15.9,16.0,16.1,16.3],'bore_x_centers':[-33,-11,11,33],'flange_seat_diameter':18.2,'flange_seat_depth':1.2,'nominal_bearing':[5,16,5],'nominal_flange':[18,1],'original_cover_bore_diameter':16.3,'original_cover_flange_seat_diameter':18.2,'original_cover_flange_seat_depth':1,'through_bores_not_axial_stops':True}))
(OUT/'verification.json').write_text(json.dumps(results,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps(results,indent=2,ensure_ascii=False))
