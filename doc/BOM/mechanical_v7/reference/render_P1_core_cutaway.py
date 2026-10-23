"""Actual P1 STEP axial sections and source-vs-trial horn geometry. No AI pixels."""
from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'tmp/cad-runtime'))
import cadquery as cq, numpy as np, trimesh
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Rectangle,Patch,Polygon
HERE=Path(__file__).resolve().parent
CAD=HERE.parent/'cad'
font_manager.fontManager.addfont('C:/Windows/Fonts/malgun.ttf')
plt.rcParams['font.family']='Malgun Gothic';plt.rcParams['axes.unicode_minus']=False

def shape_mesh(s):
    v,f=s.tessellate(.04,.08)
    return trimesh.Trimesh(np.array([p.toTuple() for p in v]),np.array(f))

# Individual STEP files are translated to positive print coordinates. Use the
# whole assembly instead so the true assembly frame and axis are retained.
solids=cq.importers.importStep(str(CAD/'fold_wing_v7_P1_assembly.step')).val().Solids()
fixed=[];moving=[]
for s in solids:
    b=s.BoundingBox()
    if abs(b.xmin+311)<.01 and abs(b.xmax+180)<.01 and abs(b.zmax-355)<.01:fixed.append(s)
    if abs(b.xmin+265)<.01 and abs(b.xmax+93)<.01 and abs(b.zmax-360)<.01:moving.append(s)
assert len(fixed)==2 and len(moving)==2,(len(fixed),len(moving))
def sections(shapes,z=315):
    res=[]
    for s in shapes:
        sc=shape_mesh(s).section(plane_normal=(0,0,1),plane_origin=(0,0,z))
        if sc is not None:res.extend(sc.discrete)
    return res

fig=plt.figure(figsize=(15,9),layout='constrained');gs=fig.add_gridspec(2,2,width_ratios=[1.7,1])
ax=fig.add_subplot(gs[:,0])
for collection,color,label in [(fixed,'#687c45','실제 STEP 고정 코어'),(moving,'#b49d68','실제 STEP 감싸는 앞뒤 판')]:
    for q in sections(collection):ax.plot(q[:,1],q[:,0]+220,color=color,lw=1.4)
ax.add_patch(Rectangle((20,-30),40,40.5,facecolor='#41474a',alpha=.88))
ax.add_patch(Rectangle((10.5,-3),9.5,6,facecolor='#cf9145',alpha=.9))
ax.add_patch(Rectangle((63,-2.45),14,4.9,facecolor='#83959d',alpha=.9))
ax.add_patch(Rectangle((62,-4),2,8,facecolor='#83959d',alpha=.9))
ax.add_patch(Rectangle((69,-8),4,16,facecolor='#a1b3b7',alpha=.75))
ax.add_patch(Rectangle((73,-9),1,18,facecolor='#a1b3b7',alpha=.75))
ax.axhline(0,color='#526852',ls='-.',lw=.7)
ax.set(xlim=(0,82),ylim=(-53,53),xlabel='Y / mm (회전축 방향)',ylabel='X - 축 중심 / mm',title='P1 실제 STEP 단면: Z=315 mm\n검은 서보 외형은 케이스40.5×40×20.2 배치용 표시')
ax.set_aspect('equal');ax.grid(alpha=.2)
ax.legend(handles=[Patch(color='#687c45',label='STEP: 고정 코어 윤곽'),Patch(color='#b49d68',label='STEP: 감싸는 앞뒤 판 윤곽'),Patch(color='#41474a',label='서보 케이스 표시'),Patch(color='#a1b3b7',label='베어링·지지축 표시')],loc='lower right',fontsize=8)
for xy,xytext,s in [((40,0),(37,35),'출력축과 반대편 지지축의 공통 축선'),((40,-10),(20,-43),'서보 몸체는 코어 Ø80 안에 수납'),((10.7,15),(12,47),'앞판의 혼 포획 홈'),((71,8),(51,46),'반대편 F625ZZ'),((64,-3),(47,-46),'고정 지지축 및 코어 뒷벽 통과부')]:
    ax.annotate(s,xy=xy,xytext=xytext,fontsize=7.5,arrowprops=dict(arrowstyle='-',lw=.6),ha='center')

data=json.loads((HERE/'original_joint_sections.json').read_text(encoding='utf-8'))
src=next(r for r in data['records'] if 'O_shoulder' in r['source_path'])
sec=next(s for s in src['sections'] if s['plane_y_mm']==2.5)
ax1=fig.add_subplot(gs[0,1])
for loop in sec['loops']:
    b=np.array(loop['xz_bounds_mm'])
    if b[0,0]>0 and b[1,0]<32 and b[0,1]>9 and b[1,1]<43:
        q=np.array(loop['xz_points_mm']);ax1.plot(q[:,0]-16,q[:,1]-26,color='#687c45')
ax1.set_aspect('equal');ax1.set(xlim=(-20,20),ylim=(-20,20),title='원본 CLS STEP: 6갈래 혼 포켓\n깊이2.7 / 약28.976×32.600');ax1.grid(alpha=.2)
ax2=fig.add_subplot(gs[1,1])
# Obtain actual new STEP front-cap pocket section at Y=10.65.
s=next(s for s in moving if s.BoundingBox().ymin<10)
sc=shape_mesh(s).section(plane_normal=(0,1,0),plane_origin=(0,10.65,0))
for q in sc.discrete:
    q=q[(np.abs(q[:,0]+220)<23)&(np.abs(q[:,2]-315)<23)]
    if len(q)>3:ax2.plot(q[:,0]+220,q[:,2]-315,color='#b49d68')
ax2.set_aspect('equal');ax2.set(xlim=(-20,20),ylim=(-20,20),title='P1 실제 STEP: 4갈래 교환형 시험 자리\nspan30 / 팔폭6.4 / 깊이2.7 (실측 전)');ax2.grid(alpha=.2)
fig.suptitle('내장 서보와 감싸는 관절 - CAD에서 추출한 단면 검토',fontsize=17)
fig.savefig(HERE/'P1_core_cutaway.svg')
fig.savefig(HERE/'P1_core_cutaway.png',dpi=160)
print('Saved P1_core_cutaway.svg/.png (actual STEP section outlines + marked hardware envelope)')
