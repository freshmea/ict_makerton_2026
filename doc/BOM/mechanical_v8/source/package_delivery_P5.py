"""Deliver P5 six-motor files, editable source and independently verified evidence."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
NAME='Fold_Wing_Buddy_v8_P5_RPY.zip'
def files():
    return sorted(p for p in ROOT.rglob('*') if p.is_file() and p.name not in [NAME,'verification_P5.json'] and p.suffix not in ['.zip','.bak','.pyc'] and 'user_snapshot' not in p.name and '__pycache__' not in p.parts)
def main():
    native=ROOT/'cad/fold_wing_v8_P5_RPY.solidcraft'
    with ZipFile(native) as z:assert z.testzip() is None
    joints=json.loads((ROOT/'source/P5_files/final_joints.json').read_text(encoding='utf-8'))
    servos=json.loads((ROOT/'source/P5_files/servo_inventory.json').read_text(encoding='utf-8'))
    assert len(servos)==6
    revolute=[j['name'] for j in joints['joints'] if j['type']=='revolute']
    assert len(revolute)==6 and not joints['errors'] and not joints['conflicts'] and not joints['floating']
    qa=json.loads((ROOT/'evidence/native_motion_P5_qa.json').read_text(encoding='utf-8'))
    assert qa['accepted'] and qa['saved_file_unchanged']
    assert qa['native_sha256']==hashlib.sha256(native.read_bytes()).hexdigest()
    manifest=json.loads((ROOT/'P5/print/manifest.json').read_text(encoding='utf-8'))
    summary={'revision':'P5','units':'mm','date_kst':'2026-10-23','native_file':native.relative_to(ROOT).as_posix(),'native_sha256':hashlib.sha256(native.read_bytes()).hexdigest(),'servo_count':6,'servo_bodies':servos,'revolute_count':6,'revolute_joints':revolute,'serial_chain_per_side':['J1 yaw','J2 shoulder pitch','J3 wrist roll'],'cad_demonstration_limits_deg':[-15,15],'print_designs':len(manifest['parts']),'print_quantity':sum(p['quantity'] for p in manifest['parts']),'physical_assembly_tested':False,'files':[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files()]}
    (ROOT/'verification_P5.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    with ZipFile(ROOT/NAME,'w',ZIP_DEFLATED,compresslevel=6) as z:
        for p in files()+[ROOT/'verification_P5.json']:z.write(p,'Fold_Wing_Buddy_v8_P5/'+p.relative_to(ROOT).as_posix())
    with ZipFile(ROOT/NAME) as z:
        assert z.testzip() is None
        for row in summary['files']:
            assert hashlib.sha256(z.read('Fold_Wing_Buddy_v8_P5/'+row['path'])).hexdigest()==row['sha256']
        print(json.dumps({'zip':NAME,'bytes':(ROOT/NAME).stat().st_size,'files':len(z.namelist()),'sha256_verified':True}))
if __name__=='__main__':main()

