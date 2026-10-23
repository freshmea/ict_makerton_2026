"""Make printable meshes from unchanged, valid native-exported P5 STEP arms.

SolidCraft's four modified-arm STL meshes have nonmanifold triangles. Preserve
them and tessellate the exact STEP solids through OpenCascade. A single tiny
triangle hole may be filled only after area and source-surface distance checks.
No CAD shape, parameter, STEP or native SolidCraft file is changed.
"""
from pathlib import Path
import hashlib, json, shutil, sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
RUNTIME=ROOT.parents[2]/'tmp/cad-runtime'
sys.path.insert(0,str(RUNTIME))
import cadquery as cq
import trimesh
import numpy as np
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib

OUT=ROOT/'source/P5_geometry_files'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def retessellate_arms():
    for folder in ['native_stl_original','occt_stl','occt_print_stl']:(OUT/folder).mkdir(parents=True,exist_ok=True)
    report_path=OUT/'arm_tessellation.json'
    previous=json.loads(report_path.read_text()) if report_path.exists() else {'parts':[]}
    prior={row['part']:row for row in previous['parts']}
    rows=[];prepared=[]
    for step in sorted((ROOT/'P5/cad').glob('*CURVED_ARM*.step')):
        name=step.stem;target=ROOT/'P5/stl'/(name+'.stl')
        source_sha=sha(step);current_sha=sha(target)
        if name in prior and current_sha==prior[name]['print_stl_sha256'] and source_sha==prior[name]['source_step_sha256']:
            original=Path(prior[name]['native_stl_original'])
        else:
            original=OUT/'native_stl_original'/(name+'_'+current_sha[:12]+'.stl')
            if not original.exists():shutil.copyfile(target,original)
        shape=cq.importers.importStep(str(step)).val()
        assert shape.isValid() and len(shape.Solids())==1 and all(s.wrapped.Closed() for s in shape.Shells())
        raw=OUT/'occt_stl'/(name+'.stl')
        cq.exporters.export(shape,str(raw),tolerance=0.08,angularTolerance=0.1)
        mesh=trimesh.load(str(raw),force='mesh',process=True)
        raw_closed=bool(mesh.is_watertight)
        before=len(mesh.faces)
        if not raw_closed:mesh.fill_holes()
        added=mesh.vertices[mesh.faces[before:]]
        areas=trimesh.triangles.area(added).tolist() if len(added) else []
        assert len(added)<=1 and (not areas or max(areas)<0.01),'Unexpected mesh hole: do not bridge model openings'
        surface=cq.Compound.makeCompound(shape.Faces())
        distances=[]
        for triangle in added:
            # Vertices, edge midpoints and centroid must remain on the same
            # exact CAD surface, within a stricter 0.01 mm local tolerance.
            samples=list(triangle)+[(triangle[i]+triangle[(i+1)%3])/2 for i in range(3)]+[triangle.mean(axis=0)]
            for point in samples:
                query=BRepExtrema_DistShapeShape(cq.Vertex.makeVertex(*map(float,point)).wrapped,surface.wrapped)
                query.Perform();assert query.IsDone()
                distances.append(query.Value())
        assert not distances or max(distances)<0.01
        assert mesh.is_watertight and mesh.is_winding_consistent and mesh.volume>0 and len(mesh.split(only_watertight=False))==1
        gap=abs(mesh.volume-shape.Volume())/shape.Volume()
        assert gap<0.005,'Excess mesh/source volume difference'
        # After tessellation, CQ's default bbox uses cached triangulation and
        # its deflection margin (over 1 mm for trimmed NURBS here). Compute the
        # exact surface-extrema bounds without that triangulation cache.
        b=Bnd_Box();BRepBndLib.AddOptimal_s(shape.wrapped,b,False,False)
        bounds=b.Get();source_bounds=np.array([bounds[:3],bounds[3:]])
        bbox_gap=float(np.max(np.abs(mesh.bounds-source_bounds)))
        assert bbox_gap<0.15,'Excess tessellation bounds difference'
        processed=OUT/'occt_print_stl'/(name+'.stl')
        mesh.export(str(processed))
        check=trimesh.load(str(processed),force='mesh',process=True)
        assert check.is_watertight and check.is_winding_consistent and len(check.split(only_watertight=False))==1
        rows.append({'part':name,'source_step':str(step),'source_step_sha256':source_sha,
                     'native_stl_original':str(original),'native_stl_sha256':sha(original),
                     'occt_raw_stl':str(raw),'occt_raw_watertight':raw_closed,
                     'linear_deflection_setting_mm':0.08,'angular_deflection_radians':0.1,
                     'filled_triangle_count':len(added),'filled_triangle_areas_mm2':areas,
                     'filled_triangle_surface_sample_distances_mm':distances,
                     'step_volume_mm3':shape.Volume(),'print_mesh_volume_mm3':check.volume,
                     'mesh_step_volume_relative_gap':gap,'mesh_step_bbox_max_abs_gap_mm':bbox_gap,
                     'step_bbox_method':'BRepBndLib.AddOptimal(useTriangulation=False,useShapeTolerance=False)',
                     'print_stl_sha256':sha(processed),'watertight':True,'connected_components':1,
                     'CAD_geometry_modified':False})
        prepared.append((processed,target))
    assert len(rows)==4
    # Only replace destinations once all four independent source tests pass.
    for processed,target in prepared:shutil.copyfile(processed,target)
    result={'method':'Native SolidCraft STEP -> OpenCascade tessellation; bounded triangle-only mesh closure',
            'native_and_STEP_unchanged':True,'parts':rows,'sliced':False,'physically_printed':False}
    report_path.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('P5 four-arm printable tessellation verified and saved',flush=True)
    return result


if __name__=='__main__':retessellate_arms()
