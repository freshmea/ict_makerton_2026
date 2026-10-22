"""P0 layout / fit-trial CAD, millimetres. Not a released manufacturing design.
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

P = dict(revision='P0', units='mm', base_w=640., base_d=200., base_h=100.,
         wall=3., floor=4., lid=4., split_x=[-106.6666667,106.6666667],
         head_w=176., head_d=100., head_h=138., head_y=5.,
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
         status='P0 - fit trials required; NO final assembly release')
override = ROOT/'cad'/'parameters_override.json'
if override.exists(): raise RuntimeError('P0: external overrides disabled; edit geometry source and regenerate all drawings together')
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
def printpart(name,s,color=CREAM,notes='P0 dimensional trial; measure hardware first'):
    add(name,s,color,'printed',notes);parts.append(components[-1])

# A soundbar tray in three build-volume-sized sections. No invented OEM screw holes.
outer=rounded(P['base_w'],P['base_d'],96,(0,0,48),12)
inner=rounded(634,194,96,(0,0,52),9)
tray=outer.cut(inner)
# Entire speaker front is open; restraint is a removable strap, not a fake precision fit.
tray=tray.cut(box(406,12,88,(0,-99,58)))
# Rear cable exit in centre section.
tray=tray.cut(box(48,12,18,(0,99,26)))
# Joint strap holes in floor. Seam plates are separate below, do not obstruct speaker.
seams=P['split_x']
for sx in seams:
    for dx in [-12,12]:
        for y in [48,76]: tray=tray.cut(cyl(1.7,8,(sx+dx,y,-1)))
# Lid fasteners: corner tabs in each section, M3 nut/insert specification still pending.
for x in [-306,-94,94,306]:
    for y in [-88,88]:
        # Front tabs outside speaker width only. Others rear, to avoid soundbar envelope.
        if y<0 and abs(x)<205: continue
        tab=box(12,24,12,(x,y,90)).cut(cyl(1.7,15,(x,y,82)))
        tray=tray.fuse(tab)
lid=rounded(640,200,4,(0,0,98),12)
# Cabling through lids into upper enclosures / yaw modules.
for x,y,w,d in [(0,5,45,25),(-275,40,42,22),(275,40,42,22)]:
    lid=lid.cut(box(w,d,10,(x,y,98)))
for x in [-306,-94,94,306]:
    for y in [-88,88]:
        if y<0 and abs(x)<205:continue
        lid=lid.cut(cyl(1.7,10,(x,y,94)))
edges=[-320]+seams+[320]
for i in range(3):
    lo,hi=edges[i],edges[i+1]
    slicer=box(hi-lo,220,120,((lo+hi)/2,0,50))
    printpart('BASE_TRAY_'+str(i+1),tray.intersect(slicer),OLIVE)
    printpart('BASE_LID_'+str(i+1),lid.intersect(slicer),CREAM)
for i,sx in enumerate(seams):
    plate=box(44,42,4,(sx,62,6))
    for dx in [-12,12]:
        for y in [48,76]:plate=plate.cut(cyl(1.7,8,(sx+dx,y,3)))
    printpart('SEAM_PLATE_'+str(i+1),plate,OLIVE)
# Nominal supplied speaker envelope, exact nominal W/D/H from official manual.
add('BA_R9_ENVELOPE',box(400,73,68,(0,-60.5,50)),BLACK,'hardware','Official nominal 400x73x68; knobs/cables require actual check')
# Head enclosure open at front, separately removable face, side/top corner radii.
head=cq.Workplane('XY').box(176,100,138).edges('|Y').fillet(22).translate((30,5,169)).val()
head=head.cut(cq.Workplane('XY').box(170,104,132).edges('|Y').fillet(19).translate((30,0,169)).val())
# Small rear vents and cable exit; not a thermal validation.
for x in [0,12,24,36,48,60]:head=head.cut(box(5,12,28,(x,54,155)))
head=head.cut(box(42,25,12,(30,5,102)))
printpart('HEAD_CASE',head)
# Faceplate with exactly two eye windows; module PCB sizes intentionally NOT assigned.
face=rounded(170,132,3,(0,0,0),19).rotate((0,0,0),(1,0,0),90).translate((30,-44.5,169))
for x in [30-25.5,30+25.5]:face=face.cut(box(32.8,12,32.8,(x,-44.5,180)))
face=face.cut(cyl(5.25,12,(30,-50,219),(0,1,0)))
face=face.cut(cyl(1.8,12,(-22,-50,216),(0,1,0)))
printpart('HEAD_FACE_TRIAL',face,CREAM,'Eye/camera openings are design trials; module measurement required')
for i,x in enumerate([4.5,55.5]):
    add('EYE_'+str(i+1)+'_DISPLAY_ONLY',box(32,7,32,(x,-41,180)),BLACK,'hardware','Display face nominal; complete PCB envelope UNKNOWN')
    for row in range(8):
        for col in range(8):
            active=(row==2 and col in [2,3,4,5]) or (row==3 and col in [1,6]) or (row==4 and col in [0,7])
            if active:add('EYE_'+str(i+1)+'_PIXEL_'+str(row)+'_'+str(col),cyl(1.25,0.8,(x+(col-3.5)*3.6,-45,180+(3.5-row)*3.6),(0,-1,0)),AMBER,'pixel')
# Official camera V2 PCB dimensions, clearance model only.
add('CAMERA_V2_PCB',box(25,1.6,23.862,(30,-37,219)),OLIVE,'hardware','Official PCB plan only; 1.6 thickness is a trial allowance, lens/connector keepouts unverified')
add('CAMERA_LENS',cyl(5,8,(30,-46,219),(0,1,0)),BLACK,'hardware','Diameter10 and length8 are trial placeholders, not manufacturer values')
# Non-final electronics keep-outs use generous adjustable zones; no mounting hole claims.
add('JETSON_RESERVED_ZONE',box(110,90,68,(20,48,46)),BLUE,'reserved','Reserved zone 110x90x68 is design allowance, NOT Nano dimensions')
add('POWER_RESERVED_ZONE',box(110,70,30,(-135,48,23)),BLUE,'reserved','Unmeasured modules, connectors and wires; design zone only')
add('BATTERY_RESERVED_ZONE',box(140,50,30,(160,60,23)),BLUE,'reserved','Battery dimensions unknown; design zone, must measure')
# Modular arm envelopes with long slotted links. Motor interface is not final released.
L=math.hypot(55,185)
for side in [-1,1]:
    tag='L' if side<0 else 'R';px=side*275;qx=side*220
    # Static yaw support pedestal and servo-envelope kept out of the speaker.
    pedestal=box(58,54,24,(px,40,112)).cut(box(42,22,28,(px,40,112)))
    printpart(tag+'_YAW_PEDESTAL_TRIAL',pedestal,OLIVE,'Servo output offset/flange and bearing support pending measurement')
    add(tag+'_YAW_SERVO_ENVELOPE',box(40.5,20.2,40,(px,40,100)),BLACK,'hardware','Vendor nominal; no spline geometry')
    # Rotation ring is a visual datum, not a spline coupling.
    add(tag+'_YAW_AXIS_DATUM',cyl(22,10,(px,40,124)),OLIVE,'datum')
    # Local beam along Z then rotate toward the central head.
    beam=box(28,26,L,(0,0,L/2)).cut(box(20,18,L-20,(0,0,L/2)))
    # Slotted fastening at each end; nominal M3 through holes, actual bracket TBD.
    for z in [8,L-8]:beam=beam.cut(cyl(1.7,40,(0,-20,z),(0,1,0)))
    angle=side*(-math.degrees(math.atan2(55,185)))
    beam=beam.rotate((0,0,0),(0,1,0),angle).translate((px,40,130))
    # Pitch fork visual/fit trial with opposite bearing seat and removable horn interface.
    # Axis Y at x=qx,z=315. Clear gap26 between the cheeks.
    fork=box(60,38,6,(qx,40,289))
    for yy in [24,56]:fork=fork.fuse(box(60,6,42,(qx,yy,309)))
    fork=fork.cut(cyl(8.15,8,(qx,52,315),(0,1,0)))
    fork=fork.cut(cyl(9.1,1.2,(qx,58,315),(0,1,0)))
    # Opposite side only a clearance pass, metal horn mount bolt pattern remains unknown.
    fork=fork.cut(cyl(10.8,8,(qx,20,315),(0,1,0)))
    printpart(tag+'_ARM_FORK_TRIAL',beam.fuse(fork),CREAM,'Axis distance193.0026; F625 seats16.3/18.2 trial; horn adapter NOT released')
    add(tag+'_PITCH_SERVO_ENVELOPE',box(40.5,40,20.2,(qx+9.75,0,315)),BLACK,'hardware','Axis offset9.75mm in this layout is provisional')
    # Hollow palm shell, fixed fingers, clip-in LED diffuser visual only.
    pcx=side*168
    palm=rounded(72,24,44,(pcx,40,315),10).cut(rounded(66,18,42,(pcx,40,312),7))
    palm=palm.cut(cyl(8.5,12,(pcx,40,327)))
    for yy in [24,40,56]: palm=palm.fuse(rounded(20,12,14,(pcx-side*36,yy,315),4))
    printpart(tag+'_PALM_SHELL_TRIAL',palm,CREAM,'LED installation and horn adapter require measured dimensions')
    add(tag+'_LED_DIFFUSER',cyl(8.5,2,(pcx,40,335)),AMBER,'reserved','Diffuser material and retention TBD')
    # Six touch targets total, implemented as trial face markers (PCB hidden/unmeasured).
    for i in range(3):add(tag+'_TOUCH_TARGET_'+str(i),cyl(5,0.8,(side*(210+i*18),-35,100)),OLIVE,'datum')
    # 6 decorative neopixel indicators on each beam, no 12V work light implied.
    for i in range(6):
        a=(i+1)/7; xx=px+(qx-px)*a;zz=130+185*a
        add(tag+'_STATUS_'+str(i),cyl(2.4,1,(xx,25,zz),(0,-1,0)),AMBER,'pixel')
# Phone cradle, adjustable small object support, no charging electronics claimed.
cradle=box(78,46,5,(-156,-18,103)).fuse(box(78,5,38,(-156,3,120)))
printpart('PHONE_CRADLE_TRIAL',cradle,OLIVE)

# Targeted static interference checks, NOT full dynamic collision verification.
byname={c['name']:c for c in components}
static_checks=[]
for side in ['L','R']:
    for a,b in [(side+'_YAW_SERVO_ENVELOPE',side+'_YAW_PEDESTAL_TRIAL'),
                (side+'_YAW_SERVO_ENVELOPE','BASE_LID_'+('1' if side=='L' else '3')),
                (side+'_PITCH_SERVO_ENVELOPE',side+'_ARM_FORK_TRIAL'),
                (side+'_PALM_SHELL_TRIAL',side+'_ARM_FORK_TRIAL')]:
        volume=byname[a]['shape'].intersect(byname[b]['shape']).Volume()
        static_checks.append(dict(a=a,b=b,intersection_mm3=volume))
        assert volume<1e-5,(a,b,volume)
for c in parts:
    if c['name'].startswith('BASE_'):
        volume=c['shape'].intersect(byname['BA_R9_ENVELOPE']['shape']).Volume()
        static_checks.append(dict(a=c['name'],b='BA_R9_ENVELOPE',intersection_mm3=volume))
        assert volume<1e-5,(c['name'],'speaker collision',volume)

assembly=cq.Assembly(name='Fold_Wing_Buddy_v6_P0')
for c in components:
    if c['kind']!='pixel':assembly.add(c['shape'],name=c['name'],color=cq.Color(*matplotlib.colors.to_rgb(c['color'])))
assembly.save(str(ROOT/'cad'/'fold_wing_v6_P0_assembly.step'))
records=[]
for c in parts:
    s=c['shape'];b=s.BoundingBox()
    # Export parts translated to their own positive XYZ, never slicer-scale the source.
    local=s.translate((-b.xmin,-b.ymin,-b.zmin))
    cq.exporters.export(local,str(ROOT/'stl'/(c['name']+'.stl')),tolerance=0.12,angularTolerance=0.15)
    cq.exporters.export(local,str(ROOT/'cad'/(c['name']+'.step')))
    mesh=trimesh.load_mesh(str(ROOT/'stl'/(c['name']+'.stl')))
    assert mesh.is_watertight,c['name']
    dims=[b.xlen,b.ylen,b.zlen]
    assert all(x<=256.001 for x in dims), (c['name'],dims)
    records.append(dict(part=c['name'],bbox_mm=dims,valid=s.isValid(),watertight=bool(mesh.is_watertight),volume_mm3=s.Volume(),notes=c['notes']))

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
front=ax_mm(12,140,700/3,400/3);draw_view(front,'front');front.set_xlim(-350,350);front.set_ylim(-35,365)
dim(front,(-320,0),(320,0),'640 DESIGN',-22)
dim(front,(-320,0),(-320,100),'100',-338,False)
dim(front,(320,0),(212,337),'337 POSE',338,False)
dim(front,(-275,130),(275,130),'550 YAW AXES',351)
front.text(-325,340,'FRONT / SCALE 1:3',fontsize=9,fontweight='bold')
side=ax_mm(278,140,290/3,400/3);draw_view(side,'side');side.set_xlim(-145,145);side.set_ylim(-35,365)
dim(side,(-100,0),(100,0),'200 DESIGN',-22)
dim(side,(55,100),(55,238),'138 HEAD',110,False)
side.text(-138,340,'RIGHT / 1:3',fontsize=9,fontweight='bold')
top=ax_mm(12,36,700/3,270/3);draw_view(top,'top');top.set_xlim(-350,350);top.set_ylim(-135,135)
dim(top,(-320,-100),(320,-100),'640',-122)
dim(top,(320,-100),(320,100),'200',338,False)
top.text(-325,115,'TOP / SCALE 1:3',fontsize=9,fontweight='bold')
fig.text(.665,.42,'P0 - LAYOUT / FIT TRIAL',fontsize=13,fontweight='bold',color='#ac5530')
notes=['All dimensions in mm. Independent orthographic views.',
       'Geometry from parametric B-rep, NOT AI imagery.',
       'Design dimensions are chosen, not measured parts.',
       'Speaker envelope: 400 W x 73 D x 68 H (official).',
       'Base: 3 sections, each about 213.33 x 200 mm.',
       'Arm axes: J1 vertical yaw, J2 horizontal pitch.',
       'J1 datum Z130; J2 datum Z315, delta X55.',
       'Axis distance sqrt(55^2+185^2) = 193.0026.',
       'Servo hole pattern 49.5 x 10: supplier drawing.',
       'Horn / shaft offset / eye PCB: MEASURE FIRST.',
       'No final servo-horn adapter or motion clearance release.',
       'Only static pose shown. Travel and load not verified.',
       'Print FIT COUPONS before the large enclosure.',
       'Do not use this concept PDF as a drill jig.']
for i,line in enumerate(notes):fig.text(.665,.392-i*.017,line,fontsize=7)
fig.text(.03,.965,'300 SECONDS / FOLD WING BUDDY - V6',fontsize=16,fontweight='bold')
fig.text(.03,.025,'FWB-ASM-001 | Rev P0 | 2026-10-23 | A3 landscape | Print at 100% / no fit-to-page | Manufacturing release: PENDING',fontsize=8)
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
ax.set_title('Fold Wing Buddy v6 | CAD layout P0 | mm | interfaces pending measurement',fontsize=12)
fig.tight_layout();fig.savefig(ROOT/'renders'/'v6_CAD_isometric.png',dpi=180);plt.close(fig)
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
draw.text((40,30),'FOLD WING BUDDY V6 / P0 CAD GEOMETRY / FIT INTERFACES PENDING',fill=(50,50,50))
img.save(ROOT/'renders'/'v6_CAD_isometric.png')
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
out=dict(revision='P0',units='mm',parts=records,all_solids_valid=all(c['shape'].isValid() for c in components),
         all_print_parts_within_256_cube=True,STL_scale='mm assumed; STL has no unit metadata; STEP declares mm',
         assembly_components=len(components),parts_count=len(parts),motion_check='not performed',hardware_fit='not measured',
         release='PENDING',base_nominal=[640,200,100],arm_axis_distance=math.hypot(55,185),
         static_checks=static_checks,all_print_parts_single_solid=True)
(ROOT/'cad'/'validation.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in out.items() if k!='parts'},indent=2))
