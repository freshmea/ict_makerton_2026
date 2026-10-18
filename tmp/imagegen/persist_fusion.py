from pathlib import Path
import json, shutil, re, hashlib
from urllib.parse import unquote
from PIL import Image
root=Path(__file__).resolve().parents[2]
out=root/'doc/BOM/img'
data=json.loads((root/'tmp/imagegen/fusion-manifest.json').read_text(encoding='utf8'))
assert len(data)==5
for row in data:
 src=Path(row.pop('source'));dest=out/row['file']
 if dest.exists():
  assert src.read_bytes()==dest.read_bytes(),dest
 else: shutil.copy2(src,dest)
 with Image.open(dest) as im:
  im.verify()
 with Image.open(dest) as im: row['dimensions']=list(im.size)
 row['sha256']=hashlib.sha256(dest.read_bytes()).hexdigest()
metadata={'date':'2026-10-18','tool':'built-in imagegen','use_case':'product-mockup','reference_images':[{'file':'design-02-pebble-buddy.png','role':'design reference: friendly companion body'}, {'file':'design-03-arch-lamp.png','role':'design reference: study arch and lighting'}],'images':data,'status':'AI concept rendering; no physical or conversational performance validation'}
(out/'design2-prompts.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf8')
md=root/'doc/BOM/design sample2.md'
s=md.read_text(encoding='utf8')
refs=re.findall(r'!\[[^\]]*\]\(([^)]+)\)',s)
assert len(refs)==5
for ref in refs: assert (md.parent/unquote(ref)).is_file(),ref
assert len({row['sha256'] for row in data})==5
print('PASS: five unique images saved, decoded, and all five gallery references resolved')
