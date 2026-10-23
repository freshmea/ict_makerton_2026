"""Freeze the reviewable files and a portable ZIP; never include backups or caches."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]
NAME='Fold_Wing_Buddy_v8_P2.zip'


def files():
    return sorted(p for p in ROOT.rglob('*') if p.is_file()
        and p.name not in [NAME,'verification.json']
        and p.suffix not in ['.bak','.pyc'] and '__pycache__' not in p.parts)


entries=[{'path':p.relative_to(ROOT).as_posix(),'bytes':p.stat().st_size,
          'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files()]
state=json.loads((ROOT/'evidence/12_final_inspect.json').read_text(encoding='utf-8'))
manifest=json.loads((ROOT/'print/manifest.json').read_text(encoding='utf-8'))
summary={'revision':'P2','units':'mm','date_kst':'2026-10-23',
    'native_file':'cad/fold_wing_v8_P2.solidcraft',
    'solidcraft_version':'0.20.0','bodies':len(state['bodies']),
    'features':len(state['timeline']),'sketches':len(state['sketches']),
    'feature_errors':len([x for x in state['timeline'] if x.get('error')]),
    'feature_warnings':len([x for x in state['timeline'] if x.get('warning')]),
    'all_sketch_dof_zero':all(s.get('dof')==0 for s in state['sketches']),
    'print_designs':len(manifest['parts']),
    'print_quantity':sum(p['quantity'] for p in manifest['parts']),
    'sliced':False,'physical_print_verified':False,'files':entries}
(ROOT/'verification.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
with ZipFile(ROOT/NAME,'w',ZIP_DEFLATED,compresslevel=6) as z:
    for p in files()+[ROOT/'verification.json']:
        z.write(p,'Fold_Wing_Buddy_v8_P2/'+p.relative_to(ROOT).as_posix())
with ZipFile(ROOT/NAME) as z:
    assert z.testzip() is None
    print(json.dumps({'zip':str(ROOT/NAME),'bytes':(ROOT/NAME).stat().st_size,
                      'files':len(z.namelist()),'crc':'pass'},ensure_ascii=False))
