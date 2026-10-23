"""Package the motion revision while preserving the earlier P2 ZIP/manifest."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]
NAME='Fold_Wing_Buddy_v8_P3_motion.zip'


def files():
    return sorted(p for p in ROOT.rglob('*') if p.is_file()
        and p.name not in [NAME,'verification_P3.json']
        and p.suffix not in ['.zip','.bak','.pyc']
        and 'user_snapshot' not in p.name and '__pycache__' not in p.parts)


def main():
    native=ROOT/'cad/fold_wing_v8_P3_motion.solidcraft'
    with ZipFile(native) as z:
        assert z.testzip() is None
        doc=json.loads(z.read('document.json'))
    joints=doc['assembly']['joints']
    # The on-disk typed enum is version-specific; recorded joint.list is canonical.
    canonical=json.loads((ROOT/'source/P3_files/final_joints.json').read_text(encoding='utf-8'))
    revolute=[j for j in canonical['joints'] if j['type']=='revolute']
    assert len(revolute)==4 and not canonical['conflicts'] and not canonical['errors']
    entries=[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,
              'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files()]
    manifest=json.loads((ROOT/'print/manifest.json').read_text(encoding='utf-8'))
    summary={'revision':'P3','date_kst':'2026-10-23','units':'mm',
        'native_file':native.relative_to(ROOT).as_posix(),
        'native_sha256':hashlib.sha256(native.read_bytes()).hexdigest(),
        'revolute_joints':[j['name'] for j in revolute],
        'total_joints':len(joints),'provisional_CAD_joint_limits_deg':[-15,15],
        'physical_servo_limits_verified':False,
        'print_geometry_revision':'P2; unchanged by joint setup',
        'print_designs':len(manifest['parts']),
        'print_quantity':sum(p['quantity'] for p in manifest['parts']),
        'files':entries}
    (ROOT/'verification_P3.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    with ZipFile(ROOT/NAME,'w',ZIP_DEFLATED,compresslevel=6) as z:
        for p in files()+[ROOT/'verification_P3.json']:
            z.write(p,'Fold_Wing_Buddy_v8_P3/'+p.relative_to(ROOT).as_posix())
    with ZipFile(ROOT/NAME) as z:
        assert z.testzip() is None
        print(json.dumps({'zip':str(ROOT/NAME),'bytes':(ROOT/NAME).stat().st_size,
            'files':len(z.namelist()),'revolute':len(revolute),'crc':'pass'},ensure_ascii=False))


if __name__=='__main__':main()
