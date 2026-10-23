"""Re-read all P5 STEP, source/rotated STL and Core 3MF without changing them.

This is a mesh/solid/coordinate audit. It does not invoke a slicer or printer,
test self-intersections, validate supports, or establish mechanical strength.
"""
from pathlib import Path
import hashlib, json, sys, xml.etree.ElementTree as ET
from zipfile import ZipFile
from datetime import datetime, timezone

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parents[2]/'tmp/cad-runtime'))
import cadquery as cq
import numpy as np
import trimesh
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def audit():
    manifest_path=ROOT/'P5/print/manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    parts=manifest['parts']
    names={row['part'] for row in parts}
    assert len(names)==29 and len(parts)==29 and sum(row['quantity'] for row in parts)==32
    assert names=={p.stem for p in (ROOT/'P5/cad').glob('*.step')}
    assert names=={p.stem for p in (ROOT/'P5/stl').glob('*.stl')}
    assert names=={p.stem for p in (ROOT/'P5/print/oriented_stl').glob('*.stl')}
    assert names=={p.stem for p in (ROOT/'P5/print/single_part_3mf').glob('*.3mf')}
    rows=[];hash_checks=0
    for record in parts:
        name=record['part']
        step=ROOT/'P5/cad'/(name+'.step')
        shape=cq.importers.importStep(str(step)).val()
        assert shape.isValid() and len(shape.Solids())==1 and all(s.wrapped.Closed() for s in shape.Shells()),name
        box=Bnd_Box();BRepBndLib.AddOptimal_s(shape.wrapped,box,False,False)
        bounds=box.Get();step_bounds=np.array([bounds[:3],bounds[3:]])
        paths=[ROOT/record[key] for key in ['source_stl','oriented_stl','model_3mf']]
        for path,key in zip(paths,['source_sha256','oriented_stl_sha256','model_3mf_sha256']):
            assert sha(path)==record[key],str(path)
            hash_checks+=1
        source=trimesh.load(str(paths[0]),force='mesh',process=True)
        rotated=trimesh.load(str(paths[1]),force='mesh',process=True)
        for mesh in [source,rotated]:
            assert mesh.is_watertight and mesh.is_winding_consistent and mesh.volume>0
            assert len(mesh.split(only_watertight=False))==1
        ns={'m':'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'}
        with ZipFile(paths[2]) as package:
            assert package.testzip() is None
            model=ET.fromstring(package.read('3D/3dmodel.model'))
        assert model.attrib['unit']=='millimeter'
        assert len(model.findall('m:resources/m:object',ns))==1
        assert len(model.findall('m:build/m:item',ns))==1
        vertices=np.array([[float(v.attrib[a]) for a in 'xyz'] for v in model.findall('.//m:vertex',ns)])
        faces=np.array([[int(f.attrib['v'+str(i)]) for i in [1,2,3]] for f in model.findall('.//m:triangle',ns)])
        placed=trimesh.Trimesh(vertices=vertices,faces=faces,process=False)
        assert placed.is_watertight and placed.is_winding_consistent and placed.volume>0
        assert len(placed.split(only_watertight=False))==1
        expected=source.copy();expected.apply_transform(np.array(record['source_to_plate_transform_4x4']))
        assert vertices.shape==expected.vertices.shape and np.allclose(vertices,expected.vertices,atol=1e-7,rtol=0)
        assert np.allclose(placed.bounds,record['plate_bbox_mm'],atol=1e-7,rtol=0)
        assert np.allclose(rotated.extents,placed.extents,atol=1e-4,rtol=0)
        bbox=placed.bounds
        brim=np.array([bbox[0,:2]-5,bbox[1,:2]+5])
        assert np.allclose(brim,record['brim_bbox_xy_mm'],atol=1e-7,rtol=0)
        assert np.all(brim[0]>=1-1e-7) and np.all(brim[1]<=255+1e-7)
        overlap=bool(np.all(brim[1]>np.array([0,0])+1e-7) and np.all(np.array([18,28])>brim[0]+1e-7))
        assert not overlap and abs(bbox[0,2])<1e-7 and bbox[1,2]<=250+1e-7
        rows.append({'part':name,'quantity':record['quantity'],'step_sha256':sha(step),
                     'step_valid':True,'step_solids':1,'step_shells_closed':True,
                     'step_exact_bounds_mm':step_bounds.tolist(),'source_stl_bounds_mm':source.bounds.tolist(),
                     'source_step_bbox_max_abs_gap_mm':float(np.abs(source.bounds-step_bounds).max()),
                     'step_volume_mm3':shape.Volume(),'source_mesh_volume_mm3':source.volume,
                     'mesh_step_volume_relative_gap':abs(source.volume-shape.Volume())/shape.Volume(),
                     'source_and_oriented_stl_closed_consistent_single_positive':True,
                     'model_3mf_crc_mm_closed_consistent_single_positive':True,
                     'model_3mf_all_vertices_match_source_transform':True,
                     'manifest_hash_checks':3,'brim_bed_exclusion_height_checks':True})
    result={'checked_at_utc':datetime.now(timezone.utc).isoformat(),
            'manifest_sha256':sha(manifest_path),'unique_parts':29,'physical_parts':32,
            'step_valid_closed_single_solid_count':29,'source_stl_closed_single_mesh_count':29,
            'oriented_stl_closed_single_mesh_count':29,'model_3mf_verified_count':29,
            'manifest_hash_matches':hash_checks,
            'maximum_source_step_bbox_gap_mm':max(row['source_step_bbox_max_abs_gap_mm'] for row in rows),
            'maximum_mesh_step_volume_relative_gap':max(row['mesh_step_volume_relative_gap'] for row in rows),
            'maximum_print_height_mm':max(row['plate_bbox_mm'][1][2] for row in parts),
            'all_static_checks_pass':True,'arm_mesh_conversion_report':'arm_tessellation.json',
            'limitations':['No triangle self-intersection audit.','No slicer import or support/toolpath verification.',
                           'No physical print or hardware fit/strength verification.',
                           'Mesh/STEP volume differences are tessellation/integration differences, not print tolerances.'],
            'parts':rows}
    target=ROOT/'source/P5_geometry_files/print_geometry_QA.json'
    target.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='parts'},indent=2))
    return result


if __name__=='__main__':audit()
