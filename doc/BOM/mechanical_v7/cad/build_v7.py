"""P1 embedded-servo layout / fit-trial CAD, millimetres. Not a released manufacturing design.
Run with CadQuery 2.4, numpy, matplotlib, trimesh and PyMuPDF available.
All output views are generated from the same B-rep shapes, never from AI pixels.
"""
from pathlib import Path
import sys, json, math, hashlib
ROOT = Path(__file__).resolve().parents[1]
runtime = ROOT.parents[2] / 'tmp' / 'cad-runtime'
if runtime.exists(): sys.path.insert(0, str(runtime))
import cadquery as cq
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import trimesh
import fitz
from OCP.HLRBRep import HLRBRep_Algo, HLRBRep_HLRToShape
from OCP.HLRAlgo import HLRAlgo_Projector
from OCP.gp import gp_Ax2, gp_Pnt, gp_Dir
from OCP.BRepLib import BRepLib
from cadquery.occ_impl.exporters.svg import getPaths

P = dict(revision='P1', units='mm', base_w=640., base_d=200., base_h=100.,
         wall=3., floor=4., lid=4., split_x=[-106.6666667,106.6666667],
         head_w=192., head_d=124., head_h=155., head_y=7.,
         yaw_x=275., yaw_y=40., yaw_z=130., pitch_x=220., pitch_z=315.,
         eye_window=32.8, eye_pitch=51., eye_z=180.,
         speaker_w=400., speaker_d=73., speaker_h=68., speaker_y=-60.5,
         speaker_z=50., servo_l=40.5, servo_w=20.2, servo_h=40.,
         servo_hole_x=49.5,servo_hole_y=10.,
         bearing_bore_trial=16.3,bearing_flange_trial=18.2,
         bearing_body=16.,bearing_flange=18.,bearing_id=5.,bearing_width=5.,
         camera_w=25.,camera_h=23.862,camera_holes_x=21.,camera_holes_z=12.5,
         camera_hole_d=2.2, camera_z=219., camera_aperture=10.5,
         fit_clearance_each_side=0.4, m3_clearance=3.4,
         status='P1 - fit trials required; NO final assembly release')
override = ROOT/'cad'/'parameters_override.json'
if override.exists(): raise RuntimeError('P1: external overrides disabled; edit geometry source and regenerate all drawings together')
(ROOT/'cad'/'parameters_used.json').write_text(json.dumps(P,indent=2)+'\n',encoding='utf-8')
CREAM='#e8dbb7'; OLIVE='#68724d'; BLACK='#303338'; BLUE='#346275'; AMBER='#e8a340'
components=[]; parts=[]; meshes=[]
def box(w,d,h,c): return cq.Workplane('XY').box(w,d,h).translate(c).val()
def cyl(r,h,c,axis=(0,0,1)):
    return cq.Solid.makeCylinder(r,h,cq.Vector(*c),cq.Vector(*axis))
def rounded(w,d,h,c,r=5):
    return cq.Workplane('XY').box(w,d,h).edges('|Z').fillet(r).translate(c).val()
def add(name,s,color=CREAM,kind='printed',notes=''):
    assert s.isValid(),name
    if kind=='printed': assert len(s.Solids())==1,(name,'disconnected solids',len(s.Solids()))
    components.append(dict(name=name,shape=s,color=color,kind=kind,notes=notes))
def printpart(name,s,color=CREAM,notes='P1 dimensional trial; measure hardware first'):
    add(name,s,color,'printed',notes);parts.append(components[-1])

# All dimensions are millimetres. P1 corrects topology; hardware fit remains conditional.
def ellipsoid(rx,ry,rz,c):
    return cq.Workplane('XY').sphere(1).val().transformGeometry(
        cq.Matrix([[rx,0,0,0],[0,ry,0,0],[0,0,rz,0],[0,0,0,1]])).translate(c)
def rounded_xz(w,h,d,c,r):
    return cq.Workplane('XY').box(w,d,h).edges('|Y').fillet(r).translate(c).val()
def cross_shape(cx,cy,cz,span=28,width=6,depth=2.4):
    return box(span,depth,width,(cx,cy,cz)).fuse(box(width,depth,span,(cx,cy,cz)))
def curved_profile(side,half_width,depth,y0):
    # Curved centerline, tangent-rich spline, with outward bow at mid-height.
    pts=[]
    for t in np.linspace(0,1,13):
        x=side*(275-55*t+22*math.sin(math.pi*t))
        z=130+185*t
        ww=half_width*(1-.15*math.sin(math.pi*t))
        pts.append((float(x),float(z),float(ww)))
    a=[(x-w,z) for x,z,w in pts];b=[(x+w,z) for x,z,w in reversed(pts)]
    wp=cq.Workplane('XZ',origin=(0,y0,0)).moveTo(*a[0]).spline(a[1:],includeCurrent=True)
    wp=wp.lineTo(*b[0]).spline(b[1:],includeCurrent=True).close()
    return wp.extrude(-depth).val()
def split_y(name,s,notes):
    for suffix,lo,hi in [('FRONT',-40,40),('REAR',40,120)]:
        half=s.intersect(box(1000,hi-lo,500,(0,(hi+lo)/2,200)))
        printpart(name+'_'+suffix,half,CREAM,notes)

# Deeply rounded pill base, nominal W/D/H retained for the actual 400mm soundbar.
outer=rounded(640,200,96,(0,0,48),45)
inner=rounded(634,194,96,(0,0,52),42)
tray=outer.cut(inner).cut(box(406,12,88,(0,-99,58))).cut(box(48,12,18,(0,99,26)))
seams=[-106.6666667,106.6666667]
for sx in seams:
    for dx in [-12,12]:
        for yy in [48,76]:tray=tray.cut(cyl(1.7,8,(sx+dx,yy,-1)))
# Grounded tabs; corners stay inside the pill outline, away from speaker.
for x in [-290,-94,94,290]:
    for yy in [-72,78]:
        if yy<0 and abs(x)<205:continue
        tab=box(12,30,12,(x,yy,90)).intersect(outer)
        # Connect each tab to the back wall without floating solids.
        if yy>0:tab=box(12,27,12,(x,86,90)).intersect(outer)
        else:tab=box(12,40,12,(x,-80,90)).intersect(outer)
        tray=tray.fuse(tab).cut(cyl(1.7,16,(x,yy,82)))
lid=rounded(640,200,4,(0,0,98),45)
for x,yy,w,d in [(25,5,45,25),(-275,40,64,24),(275,40,64,24)]:
    lid=lid.cut(box(w,d,12,(x,yy,98)))
for x in [-290,-94,94,290]:
    for yy in [-72,78]:
        if yy<0 and abs(x)<205:continue
        lid=lid.cut(cyl(1.7,10,(x,yy,94)))
cuts=[-320]+seams+[320]
for i in range(3):
    lo,hi=cuts[i],cuts[i+1];sl=box(hi-lo,220,120,((lo+hi)/2,0,50))
    printpart('PILL_BASE_TRAY_'+str(i+1),tray.intersect(sl),OLIVE)
    printpart('PILL_BASE_LID_'+str(i+1),lid.intersect(sl),CREAM)
for i,sx in enumerate(seams):
    plate=box(44,42,4,(sx,62,6))
    for dx in [-12,12]:
        for yy in [48,76]:plate=plate.cut(cyl(1.7,8,(sx+dx,yy,3)))
    printpart('SEAM_PLATE_'+str(i+1),plate,OLIVE)
add('BA_R9_ENVELOPE',box(400,73,68,(0,-60.5,50)),BLACK,'hardware','Official nominal, cable and knob still measured separately')

# Domed pebble, curved in all three axes. Split along a front service plane.
pebble=ellipsoid(96,62,84,(25,7,171)).intersect(box(220,150,155,(25,7,177.5)))
hollow=ellipsoid(92.8,58.8,80.8,(25,7,171))
head_shell=pebble.cut(hollow).cut(box(42,30,10,(25,7,102)))
for xx in [-5,10,25,40,55]:head_shell=head_shell.cut(box(5,20,22,(xx,64,155)))
# One dark capsule visor restores the original character face.
visor_mask=rounded_xz(144,67,70,(25,-52,181),30)
visor=head_shell.intersect(visor_mask)
head_shell=head_shell.cut(visor_mask)
for xx in [-.5,50.5]:
    head_shell=head_shell.cut(box(33.0,90,33.0,(xx,-43,180)))
    visor=visor.cut(box(32.8,12,32.8,(xx,-49,180)))
# Avoid pretending unknown camera mount coordinates are final.
head_shell=head_shell.cut(cyl(5.25,40,(25,-70,216),(0,1,0)))
head_shell=head_shell.cut(cyl(1.8,40,(-32,-70,210),(0,1,0)))
front_half=head_shell.intersect(box(240,28,170,(25,-41,170)))
rear_half=head_shell.intersect(box(240,110,170,(25,28,170)))
printpart('PEBBLE_HEAD_FRONT_TRIAL',front_half,CREAM,'Ellipsoid front shell; unknown matrix/camera mount coordinates remain trial')
printpart('PEBBLE_HEAD_REAR_TRIAL',rear_half,CREAM,'Domed service shell; detachable fastener details pending')
printpart('CAPSULE_VISOR_TRIAL',visor,BLACK,'A dark trim/frame, not a transparent optical window')
for i,xx in enumerate([-.5,50.5]):
    add('EYE_'+str(i+1)+'_DISPLAY_ONLY',box(32,7,32,(xx,-45,180)),BLACK,'hardware','32mm face trial, full module PCB unknown')
    for row in range(8):
        for col in range(8):
            active=(row==2 and col in [2,3,4,5]) or (row==3 and col in [1,6]) or (row==4 and col in [0,7])
            if active:add('EYE_'+str(i+1)+'_PIXEL_'+str(row)+'_'+str(col),cyl(1.25,1,(xx+(col-3.5)*3.6,-50,180+(3.5-row)*3.6),(0,-1,0)),AMBER,'pixel')
add('CAMERA_LENS_TRIAL',cyl(5,10,(25,-54,216),(0,1,0)),BLACK,'hardware','Lens clearance trial')
add('JETSON_RESERVED_ZONE',box(110,90,68,(20,48,46)),BLUE,'reserved','Reserved zone, not physical board dimensions')
add('POWER_RESERVED_ZONE',box(110,70,30,(-135,48,23)),BLUE,'reserved','Unmeasured')
add('BATTERY_RESERVED_ZONE',box(140,50,30,(160,60,23)),BLUE,'reserved','Unmeasured')

joint_metadata=[]
for side in [-1,1]:
    tag='L' if side<0 else 'R';px=side*275;qx=side*220;yy=40;zz=315
    # YAW motor is recessed inside the base and circular collar.
    yaw_shell=cyl(41,35,(px,40,100)).cut(cyl(36.5,39,(px,40,98)))
    printpart(tag+'_ROUND_YAW_COLLAR_TRIAL',yaw_shell,OLIVE,'Motor inside base/collar; rotary bearing carrier still needs as-built shaft offsets')
    add(tag+'_YAW_SERVO_INSIDE_BASE',box(40.5,20.2,40,(px+side*9.75,40,106)),BLACK,'hardware','40height and9.75axis offset are provisional envelopes')
    yaw_rotor=cyl(36,6,(px,40,129)).cut(cyl(1.7,10,(px,40,127)))
    # Recess for cross horn, not a printed replacement spline.
    hc=box(30,6.4,2.7,(px,40,130.35)).fuse(box(6.4,30,2.7,(px,40,130.35)))
    yaw_rotor=yaw_rotor.cut(hc)
    # The yaw rotor is fused to the curved arm halves, not left as overlapping parts.

    # FIXED inner core contains motor, with curved arm integrated into its walls.
    arm=curved_profile(side,21,34,23).cut(curved_profile(side,17.8,28,26))
    core=cyl(40,54,(qx,13,zz),(0,1,0)).cut(cyl(37,48,(qx,16,zz),(0,1,0)))
    fixed=arm.fuse(core).fuse(yaw_rotor)
    # Motor body inside barrel, offset relative to output axis, never outside yoke.
    scx=qx+side*9.75
    motor=box(40.5,40,20.2,(scx,40,zz))
    pocket=box(41.3,44,21.0,(scx,40,zz))
    fixed=fixed.cut(pocket)
    # Flange support rails are outside the case ends, tied to inner shell.
    for off in [-24.75,24.75]:
        ex=scx+off
        rail=box(6,10,48,(ex,21,zz-14))
        fixed=fixed.fuse(rail.intersect(cyl(40,54,(qx,13,zz),(0,1,0))))
        for dz in [-5,5]:fixed=fixed.cut(cyl(1.7,16,(ex,12,zz+dz),(0,1,0)))
    # Small drive-shaft opening in fixed front wall.
    fixed=fixed.cut(cyl(4.5,8,(qx,10,zz),(0,1,0)))
    fixed=fixed.cut(cyl(2.5,8,(qx,61,zz),(0,1,0)))
    # Four radial assembly screw bosses and through holes, separate from case.
    for dx in [-26,26]:
        for dz in [-24,24]:
            boss=cyl(4,54,(qx+dx,13,zz+dz),(0,1,0))
            fixed=fixed.fuse(boss).cut(cyl(1.7,60,(qx+dx,10,zz+dz),(0,1,0)))
    split_y(tag+'_CURVED_ARM_CORE',fixed,'Embedded servo pocket + source-inspired crossed horn/wrap/bearing; actual flange/shaft fit pending')
    add(tag+'_PITCH_SERVO_EMBEDDED',motor,BLACK,'hardware','Fully inside fixed core envelope and wrap; unknown shaft offset9.75 is trial')
    add(tag+'_SHORT_SERVO_SHAFT_TRIAL',cyl(3,9.5,(qx,10.5,zz),(0,1,0)),BLACK,'hardware','No fabricated spline details')

    # MOVING wrap surrounds both ends of fixed core. Drive cap and rear bearing cap.
    drive=cyl(45,6,(qx,6,zz),(0,1,0))
    socket=cross_shape(qx,10.65,zz,30,6.4,2.7)
    drive=drive.cut(socket).cut(cyl(2.65,10,(qx,4,zz),(0,1,0)))
    rear=cyl(45,6,(qx,68,zz),(0,1,0))
    rear=rear.cut(cyl(8.15,8,(qx,67,zz),(0,1,0))).cut(cyl(9.1,1.05,(qx,73,zz),(0,1,0)))
    # Bridge on the inward radial side, 1mm clear of fixed Ø80 barrel.
    bridge=box(8,64,20,(qx-side*45,40,zz))
    moving=drive.fuse(rear).fuse(bridge)
    # Cupped oval palm, fixed fingers point inward; rear curve blends into wrap.
    pcx=qx-side*81
    palm_outer=ellipsoid(40,27,21,(pcx,40,zz))
    palm_inner=ellipsoid(36.8,23.8,17.8,(pcx,40,zz))
    palm=palm_outer.cut(palm_inner)
    # Palm diffuser aperture on the underside, no unsupported moving zoom lens.
    aperture=cq.Workplane('XY').ellipse(20,13).extrude(16).translate((pcx,40,zz-28)).val()
    palm=palm.cut(aperture)
    moving=moving.fuse(palm)
    for fy in [22,40,58]:
        tip=ellipsoid(12,9,9,(pcx-side*34,fy,zz+1))
        moving=moving.fuse(tip)
    # Service split exposes hidden servo, crossed horn recess and bearing pocket.
    split_y(tag+'_WRAP_HAND',moving,'Moving wrap captures cross horn on front and F625ZZ on rear; bearing stub fixed to core')
    # Visual metal cross horn (not printed); actual horn fit not asserted.
    horn=cross_shape(qx,10.8,zz,29.6,6.0,2.2).cut(cyl(1.6,6,(qx,8,zz),(0,1,0)))
    add(tag+'_ACTUAL_CROSS_HORN_PLACEHOLDER',horn,'#8d969b','hardware','Metal/plastic cross horn envelope trial, not spline reproduction')
    bearing=cyl(8,4,(qx,69,zz),(0,1,0)).fuse(cyl(9,1,(qx,73,zz),(0,1,0))).cut(cyl(2.5,7,(qx,67,zz),(0,1,0)))
    add(tag+'_F625ZZ_BEARING',bearing,'#83959d','hardware','Nominal F625ZZ5x16x5 flange18x1')
    add(tag+'_FIXED_SUPPORT_STUB_TRIAL',cyl(2.45,14,(qx,63,zz),(0,1,0)).fuse(cyl(4,2,(qx,62,zz),(0,1,0))),'#8d969b','hardware','Illustrative5mm-classfixed stub; fit/retention measured separately')
    # Six RGB windows following the curved arm.
    for i in range(6):
        t=.18+i*.11; xx=side*(275-55*t+22*math.sin(math.pi*t));z=130+185*t
        add(tag+'_RGB_'+str(i),cyl(3,1.2,(xx,22,z),(0,-1,0)),AMBER,'pixel')
    for i in range(3):add(tag+'_TOUCH_'+str(i),cyl(5,1,(side*(205+i*18),-35,100)),OLIVE,'datum')
    joint_metadata.append(dict(side=tag,pivot=[qx,40,315],axis=[0,1,0],fixed_core_diameter=80,fixed_core_y=[13,67],
                               motor_bbox_inside_core=True,cross_recess_trial=[30,6.4,2.7],bearing_bore=16.3,flange_bore=18.2,
                               drive_cap_y=[6,12],rear_cap_y=[68,74],fixed_vs_moving_clearance_nominal=1.0))

# Rounded cradle trough and gently tilted rounded back.
foot=rounded(82,52,6,(-157,-18,103),14)
back=rounded_xz(78,52,6,(-157,3,128),12).rotate((-157,3,103),(-156,3,103),-12)
cradle=foot.fuse(back)
printpart('ROUNDED_PHONE_CRADLE_TRIAL',cradle,OLIVE)

# Exact mirrored printed wrap parts, preventing independently approximated right-hand splines.
for comp in components:
    if comp['name'].startswith('R_WRAP_HAND_'):
        source=next(c for c in components if c['name']=='L'+comp['name'][1:])
        comp['shape']=source['shape'].mirror('YZ')
# Targeted checks for the corrected topology.
byname={c['name']:c for c in components};static_checks=[]
for side in ['L','R']:
    motor=byname[side+'_PITCH_SERVO_EMBEDDED']['shape']
    for name in [side+'_CURVED_ARM_CORE_FRONT',side+'_CURVED_ARM_CORE_REAR',side+'_WRAP_HAND_FRONT',side+'_WRAP_HAND_REAR']:
        vol=motor.intersect(byname[name]['shape']).Volume();static_checks.append(dict(a=side+'_PITCH_SERVO_EMBEDDED',b=name,intersection_mm3=vol))
        assert vol<1e-5,(side,name,vol)
    for a in ['FRONT','REAR']:
        for b in ['FRONT','REAR']:
            na=side+'_CURVED_ARM_CORE_'+a;nb=side+'_WRAP_HAND_'+b
            vol=byname[na]['shape'].intersect(byname[nb]['shape']).Volume()
            static_checks.append(dict(a=na,b=nb,intersection_mm3=vol));assert vol<1e-5,(na,nb,vol)
for c in parts:
    if c['name'].startswith('PILL_BASE'):
        vol=c['shape'].intersect(byname['BA_R9_ENVELOPE']['shape']).Volume()
        static_checks.append(dict(a=c['name'],b='BA_R9_ENVELOPE',intersection_mm3=vol));assert vol<1e-5,(c['name'],vol)
(ROOT/'cad'/'joint_topology.json').write_text(json.dumps(joint_metadata,indent=2)+'\n',encoding='utf-8')

assembly=cq.Assembly(name='Fold_Wing_Buddy_v7_P1')
for c in components:
    if c['kind']!='pixel':assembly.add(c['shape'],name=c['name'],color=cq.Color(*matplotlib.colors.to_rgb(c['color'])))
assembly.save(str(ROOT/'cad'/'fold_wing_v7_P1_assembly.step'))
records=[]
for c in parts:
    s=c['shape'];b=s.BoundingBox()
    # Export parts translated to their own positive XYZ, never slicer-scale the source.
    local=s.translate((-b.xmin,-b.ymin,-b.zmin))
    cq.exporters.export(local,str(ROOT/'stl'/(c['name']+'.stl')),tolerance=0.12,angularTolerance=0.15)
    cq.exporters.export(local,str(ROOT/'cad'/(c['name']+'.step')))
    mesh=trimesh.load_mesh(str(ROOT/'stl'/(c['name']+'.stl')))
    raw_mesh_watertight=bool(mesh.is_watertight)
    if not raw_mesh_watertight:
        mesh.merge_vertices(digits_vertex=7)
        mesh.update_faces(mesh.nondegenerate_faces())
        mesh.update_faces(mesh.unique_faces())
        mesh.remove_unreferenced_vertices()
        mesh.export(str(ROOT/'stl'/(c['name']+'.stl')))
    if not mesh.is_watertight and c['name'].startswith('R_WRAP_HAND_'):
        left=ROOT/'stl'/('L'+c['name'][1:]+'.stl')
        mesh=trimesh.load_mesh(str(left))
        width=mesh.extents[0]
        mesh.apply_transform(np.array([[-1,0,0,width],[0,1,0,0],[0,0,1,0],[0,0,0,1]]))
        mesh.export(str(ROOT/'stl'/(c['name']+'.stl')))
    assert mesh.is_watertight,c['name']
    dims=[b.xlen,b.ylen,b.zlen]
    assert all(x<=256.001 for x in dims), (c['name'],dims)
    records.append(dict(part=c['name'],bbox_mm=dims,valid=s.isValid(),watertight=bool(mesh.is_watertight),raw_mesh_watertight=raw_mesh_watertight,duplicate_degenerate_cleanup=not raw_mesh_watertight,volume_mm3=s.Volume(),notes=c['notes']))

for c in components:
    verts,faces=c['shape'].tessellate(0.45,0.2)
    v=np.array([p.toTuple() for p in verts]);f=np.array(faces)
    meshes.append(dict(name=c['name'],verts=v,faces=f,color=c['color'],kind=c['kind']))

# OpenCascade hidden-line removal with an explicit orthographic coordinate frame.
# The same vector projection supplies the standalone SVG and scaled A3 PDF views.
hlr_views={}
hlr_shape=cq.Compound.makeCompound([c['shape'] for c in components if c['kind']!='reserved'])
for name,normal,right in [('front',(0,-1,0),(1,0,0)),('side',(1,0,0),(0,1,0)),('top',(0,0,1),(1,0,0))]:
    algo=HLRBRep_Algo();algo.Add(hlr_shape.wrapped)
    algo.Projector(HLRAlgo_Projector(gp_Ax2(gp_Pnt(),gp_Dir(*normal),gp_Dir(*right))))
    algo.Update();algo.Hide();tool=HLRBRep_HLRToShape(algo)
    visible=[]
    for edge in [tool.VCompound(),tool.Rg1LineVCompound(),tool.OutLineVCompound()]:
        if not edge.IsNull():
            BRepLib.BuildCurves3d_s(edge,1e-6);visible.append(cq.Shape(edge))
    _,paths=getPaths(visible,[])
    bb=cq.Compound.makeCompound(visible).BoundingBox()
    svg=(f'<svg xmlns="http://www.w3.org/2000/svg" width="1400" height="{1400*bb.ylen/bb.xlen}" '
         f'viewBox="{bb.xmin} {-bb.ymax} {bb.xlen} {bb.ylen}">'
         '<g transform="scale(1,-1)" fill="none" stroke="#20262c" stroke-width="0.48">'+
         ''.join('<path d="'+p+'"/>' for p in paths)+'</g></svg>')
    path=ROOT/'drawings'/('CAD_HLR_'+name+'.svg');path.write_text(svg,encoding='utf-8')
    doc=fitz.open(stream=svg.encode(),filetype='svg');pix=doc[0].get_pixmap(alpha=False)
    png=ROOT/'drawings'/('CAD_HLR_'+name+'.png');pix.save(png)
    hlr_views[name]=(plt.imread(png),[bb.xmin,bb.xmax,bb.ymin,bb.ymax])

def draw_view(ax,view,internal=False):
    if not internal:
        img,extent=hlr_views[view]
        ax.imshow(img,extent=extent,origin='upper',interpolation='bilinear')
        ax.set_aspect('equal');ax.axis('off');return
    # One mesh source, exact orthographic projection. The side view looks from +X.
    axes={'front':(0,2,1),'side':(1,2,0),'top':(0,1,2)}[view]
    a,b,d=axes;poly=[];cols=[];depth=[]
    for m in meshes:
        if m['kind']=='reserved' and not internal:continue
        vv=m['verts'];tri=vv[m['faces']];poly.extend(tri[:,:,[a,b]])
        cc=matplotlib.colors.to_rgb(m['color']);cols.extend([cc]*len(tri))
        dd=tri[:,:,d].mean(1);depth.extend(dd if view!='side' else -dd)
    ix=np.argsort(depth)[::-1] if view=='front' else np.argsort(depth)
    coll=PolyCollection([poly[i] for i in ix],facecolors=[cols[i] for i in ix],edgecolors='none',rasterized=False)
    ax.add_collection(coll);ax.set_aspect('equal');ax.axis('off')

def dim(ax,p1,p2,text,offset=0,horiz=True):
    x1,y1=p1;x2,y2=p2
    if horiz:
        yy=offset;ax.plot([x1,x1],[y1,yy],color='#777',lw=.45);ax.plot([x2,x2],[y2,yy],color='#777',lw=.45)
        ax.annotate('',(x1,yy),(x2,yy),arrowprops=dict(arrowstyle='<->',lw=.6,color='#333',shrinkA=0,shrinkB=0))
        ax.text((x1+x2)/2,yy+4,text,ha='center',va='bottom',fontsize=7,bbox=dict(facecolor='white',edgecolor='none',pad=.5))
    else:
        xx=offset;ax.plot([x1,xx],[y1,y1],color='#777',lw=.45);ax.plot([x2,xx],[y2,y2],color='#777',lw=.45)
        ax.annotate('',(xx,y1),(xx,y2),arrowprops=dict(arrowstyle='<->',lw=.6,color='#333',shrinkA=0,shrinkB=0))
        ax.text(xx+4,(y1+y2)/2,text,ha='left',va='center',rotation=90,fontsize=7,bbox=dict(facecolor='white',edgecolor='none',pad=.5))

MM=25.4
fig=plt.figure(figsize=(420/MM,297/MM),facecolor='white')
def ax_mm(x,y,w,h):return fig.add_axes([x/420,y/297,w/420,h/297])
front=ax_mm(12,140,700/3,425/3);draw_view(front,'front');front.set_xlim(-350,350);front.set_ylim(-35,390)
dim(front,(-320,0),(320,0),'640 DESIGN',-22)
dim(front,(-320,0),(-320,100),'100',-338,False)
dim(front,(320,0),(265,360),'360 POSE',338,False)
dim(front,(-275,130),(275,130),'550 YAW AXES',375)
front.text(-325,375,'FRONT / SCALE 1:3',fontsize=9,fontweight='bold')
side=ax_mm(278,140,290/3,425/3);draw_view(side,'side');side.set_xlim(-145,145);side.set_ylim(-35,390)
dim(side,(-100,0),(100,0),'200 DESIGN',-22)
dim(side,(55,100),(69,255),'155 HEAD',110,False)
side.text(-138,375,'RIGHT / 1:3',fontsize=9,fontweight='bold')
top=ax_mm(12,36,700/3,270/3);draw_view(top,'top');top.set_xlim(-350,350);top.set_ylim(-135,135)
dim(top,(-320,-100),(320,-100),'640',-122)
dim(top,(320,-100),(320,100),'200',338,False)
top.text(-325,115,'TOP / SCALE 1:3',fontsize=9,fontweight='bold')
fig.text(.665,.42,'P1 - LAYOUT / FIT TRIAL',fontsize=13,fontweight='bold',color='#ac5530')
notes=['All dimensions in mm. Independent orthographic views.',
       'Geometry from parametric B-rep, NOT AI imagery.',
       'Design dimensions are chosen, not measured parts.',
       'Speaker envelope: 400 W x 73 D x 68 H (official).',
       'Base: 3 sections, each about 213.33 x 200 mm.',
       'Arm axes: J1 vertical yaw, J2 horizontal pitch.',
       'J1 datum Z130; J2 datum Z315, delta X55.',
       'Axis distance sqrt(55^2+185^2) = 193.0026.',
       'Servo hole pattern 49.5 x 10: supplier drawing.',
       'Source CLS horn is 6-lobe; user requests 4-arm insert.',
       'Servo INSIDE core; wrap has cross capture + bearing.',
       'Only static pose shown. Travel and load not verified.',
       'Cross 30 x 6.4 x 2.7 is a replaceable TRIAL recess.',
       'Do not use this concept PDF as a drill jig.']
for i,line in enumerate(notes):fig.text(.665,.392-i*.017,line,fontsize=7)
fig.text(.03,.965,'300 SECONDS / FOLD WING BUDDY - V7',fontsize=16,fontweight='bold')
fig.text(.03,.025,'FWB-ASM-001 | Rev P1 | 2026-10-23 | A3 landscape | Print at 100% / no fit-to-page | Manufacturing release: PENDING',fontsize=8)
fig.savefig(ROOT/'drawings'/'FWB_ASM_001_orthographic_A3.pdf')
fig.savefig(ROOT/'drawings'/'FWB_ASM_001_orthographic_A3.png',dpi=160)
fig.savefig(ROOT/'drawings'/'FWB_ASM_001_orthographic_A3.svg')
plt.close(fig)
# A real CAD render / no optical perspective trickery. Reserved zones hidden externally.
fig=plt.figure(figsize=(14,8));ax=fig.add_subplot(111,projection='3d',computed_zorder=False)
all_tri=[];all_colors=[]
light=np.array([.3,-.6,.8]);light=light/np.linalg.norm(light)
for m in meshes:
    if m['kind']=='reserved':continue
    tri=m['verts'][m['faces']]
    normals=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);length=np.linalg.norm(normals,axis=1);length[length==0]=1
    normals=normals/length[:,None]
    shade=.68+.32*np.maximum(normals@light,0)
    colors=np.array(matplotlib.colors.to_rgb(m['color']))[None,:]*shade[:,None]
    all_tri.extend(tri);all_colors.extend(colors)
ax.add_collection3d(Poly3DCollection(all_tri,facecolors=all_colors,edgecolors='none',zsort='average'))
ax.set_xlim(-340,340);ax.set_ylim(-120,120);ax.set_zlim(0,360)
ax.set_box_aspect((680,240,360));ax.view_init(22,-65);ax.set_proj_type('ortho');ax.axis('off')
ax.set_title('Fold Wing Buddy v7 | CAD layout P1 | mm | interfaces pending measurement',fontsize=12)
fig.tight_layout();fig.savefig(ROOT/'renders'/'v7_CAD_isometric.png',dpi=180);plt.close(fig)
# Deterministic software depth buffer prevents intersecting-triangle painter artefacts.
from PIL import Image, ImageDraw
W,H=1800,1000
camera=np.array([.9,-1.6,1.0]);camera/=np.linalg.norm(camera)
screen_x=np.cross([0,0,1],camera);screen_x/=np.linalg.norm(screen_x)
screen_y=np.cross(camera,screen_x)
vertices=np.concatenate([m['verts'] for m in meshes if m['kind']!='reserved'])
uv=np.column_stack([vertices@screen_x,vertices@screen_y])
umin,vmin=uv.min(0);umax,vmax=uv.max(0)
scale=min((W-180)/(umax-umin),(H-170)/(vmax-vmin))
zbuffer=np.full((H,W),-np.inf);canvas=np.full((H,W,3),250,dtype=np.uint8)
for m in meshes:
    if m['kind']=='reserved':continue
    v=m['verts'];screen=np.column_stack([(v@screen_x-(umin+umax)/2)*scale+W/2,
                                        H/2+30-(v@screen_y-(vmin+vmax)/2)*scale])
    depths=v@camera
    for f in m['faces']:
        p=screen[f];z=depths[f]
        x0=max(0,int(np.floor(p[:,0].min())));x1=min(W-1,int(np.ceil(p[:,0].max())))
        y0=max(0,int(np.floor(p[:,1].min())));y1=min(H-1,int(np.ceil(p[:,1].max())))
        if x1<x0 or y1<y0:continue
        den=(p[1,1]-p[2,1])*(p[0,0]-p[2,0])+(p[2,0]-p[1,0])*(p[0,1]-p[2,1])
        if abs(den)<1e-9:continue
        xx,yy=np.meshgrid(np.arange(x0,x1+1)+.5,np.arange(y0,y1+1)+.5)
        a=((p[1,1]-p[2,1])*(xx-p[2,0])+(p[2,0]-p[1,0])*(yy-p[2,1]))/den
        b=((p[2,1]-p[0,1])*(xx-p[2,0])+(p[0,0]-p[2,0])*(yy-p[2,1]))/den
        c=1-a-b;zz=a*z[0]+b*z[1]+c*z[2]
        sub=zbuffer[y0:y1+1,x0:x1+1];mask=(a>=-1e-8)&(b>=-1e-8)&(c>=-1e-8)&(zz>sub)
        if not mask.any():continue
        sub[mask]=zz[mask]
        tri=v[f];normal=np.cross(tri[1]-tri[0],tri[2]-tri[0]);normal/=max(np.linalg.norm(normal),1e-12)
        shade=.64+.36*abs(float(normal@light))
        color=(np.array(matplotlib.colors.to_rgb(m['color']))*255*shade).astype(np.uint8)
        canvas[y0:y1+1,x0:x1+1][mask]=color
img=Image.fromarray(canvas);draw=ImageDraw.Draw(img)
draw.text((40,30),'FOLD WING BUDDY V7 / P1 CAD GEOMETRY / FIT INTERFACES PENDING',fill=(50,50,50))
img.save(ROOT/'renders'/'v7_CAD_isometric.png')
# Floorplan drawing exposes RESERVED zones rather than pretending exact PCB placement.
fig,ax=plt.subplots(figsize=(12,5));
for c in components:
    if c['kind']=='reserved' or c['name']=='BA_R9_ENVELOPE':
        b=c['shape'].BoundingBox();ax.add_patch(plt.Rectangle((b.xmin,b.ymin),b.xlen,b.ylen,facecolor=c['color'],alpha=.25,edgecolor=c['color']))
        ax.text((b.xmin+b.xmax)/2,(b.ymin+b.ymax)/2,c['name'].replace('_','\n'),ha='center',va='center',fontsize=8)
ax.add_patch(plt.Rectangle((-320,-100),640,200,fill=False,color='black'))
for x in seams:ax.axvline(x,color='#666',ls='--',lw=.8)
ax.set_xlim(-340,340);ax.set_ylim(-120,120);ax.set_aspect('equal');ax.set_xlabel('X / mm');ax.set_ylabel('Y / mm');ax.set_title('BASE KEEP-OUT PLAN / nominal speaker + provisional reserved zones')
fig.tight_layout();fig.savefig(ROOT/'drawings'/'FWB_BASE_internal_layout.pdf');fig.savefig(ROOT/'drawings'/'FWB_BASE_internal_layout.png',dpi=150);plt.close(fig)
out=dict(revision='P1',units='mm',parts=records,all_solids_valid=all(c['shape'].isValid() for c in components),
         all_print_parts_within_256_cube=True,STL_scale='mm assumed; STL has no unit metadata; STEP declares mm',
         assembly_components=len(components),parts_count=len(parts),motion_check='not performed',hardware_fit='not measured',
         release='PENDING',base_nominal=[640,200,100],arm_axis_distance=math.hypot(55,185),
         static_checks=static_checks,all_print_parts_single_solid=True)
(ROOT/'cad'/'validation.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in out.items() if k!='parts'},indent=2))
