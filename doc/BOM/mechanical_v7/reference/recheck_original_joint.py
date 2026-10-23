"""Read-only re-audit of original SpotMicro geometry; model coordinates are mm.
Run from repository root with the existing tmp/cad-runtime available.
"""
from pathlib import Path
import sys, json, hashlib
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'tmp/cad-runtime'))
import cadquery as cq
import numpy as np
import trimesh
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
HERE=Path(__file__).resolve().parent
SOURCE=ROOT/'doc/BOM/mechanical_v6/reference/SpotMicro_parts'

def mesh(path):
    if path.suffix.lower()=='.stl': return trimesh.load(str(path))
    s=cq.importers.importStep(str(path)).val()
    v,t=s.tessellate(.02,.05)
    return trimesh.Trimesh(vertices=np.array([p.toTuple() for p in v]),faces=np.array(t))

records=[]
for rel,planes in [
    ('STEP_Files/O_shoulder_cls_grooved_modi.stp',[1.5,2.5,4.5]),
    ('STEP_Files/I_shoulder_cls_modi.stp',[.5,2.25,4.5,15,35]),
    ('STL/files/L_arm.stl',[-9,-7,0,15,23]),
    ('STL/files/L_arm_cover.stl',[1,15,30,40.5,43]),
    ('STL/files/L_arm_joint.stl',[-6,0,10,18,22]),
    ('STL/files/L_wrist.stl',[-59,-50,-42,-35,-31])]:
    p=SOURCE/rel;m=mesh(p)
    rec={'source_path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
         'bbox_xyz_mm':m.bounds.tolist(),'sections':[]}
    fig,axs=plt.subplots(1,len(planes),figsize=(16,5),layout='constrained')
    for ax,y in zip(np.atleast_1d(axs),planes):
        sc=m.section(plane_origin=(0,y,0),plane_normal=(0,1,0))
        loops=[]
        if sc is not None:
            for q in sc.discrete:
                ax.plot(q[:,0],q[:,2],lw=1)
                loops.append({'xz_bounds_mm':np.array([q.min(0),q.max(0)])[:,[0,2]].tolist(),
                              'xz_points_mm':q[:,[0,2]].tolist()})
        rec['sections'].append({'plane_y_mm':y,'loops':loops})
        ax.set_aspect('equal');ax.set_title('Y='+str(y)+' mm');ax.grid(alpha=.2)
        ax.set_xlabel('X / mm');ax.set_ylabel('Z / mm')
    fig.suptitle(p.stem+' : original mesh/STEP sections (source coordinates)')
    target=HERE/(p.stem+'_sections.png');fig.savefig(target,dpi=160);plt.close(fig)
    records.append(rec)
(HERE/'original_joint_sections.json').write_text(json.dumps({'date':'2026-10-23','units_note':'STEP specifies mm; STL mm inferred from original URDF scale 0.001. Not physical measurements.','records':records},indent=2),encoding='utf-8')
print('Saved original_joint_sections.json and six source-section images')
