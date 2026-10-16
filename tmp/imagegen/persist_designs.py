from pathlib import Path
import json, shutil, re, hashlib
from PIL import Image
root=Path(__file__).resolve().parents[2]
data=json.loads((root/'tmp/imagegen/design-manifest.json').read_text(encoding='utf8'))
out=root/'doc/BOM/img'
out.mkdir(parents=True,exist_ok=True)
for row in data:
 src=Path(row['source']);target=out/row['file']
 if target.exists():
  assert hashlib.sha256(src.read_bytes()).digest()==hashlib.sha256(target.read_bytes()).digest(), str(target)+' exists with different content'
 else: shutil.copy2(src,target)
 with Image.open(target) as im:
  im.verify()
 with Image.open(target) as im:
  row['dimensions']=list(im.size)
 row['sha256']=hashlib.sha256(target.read_bytes()).hexdigest()
 row.pop('source')
payload={'generated_on':'2026-10-16','tool':'built-in imagegen','use_case':'product-mockup','status':'AI concept renderings; not engineering validation','images':data}
(out/'design-prompts.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf8')
md=root/'doc/BOM/design sample.md'
refs=re.findall(r'!\[[^\]]*\]\(([^)]+)\)',md.read_text(encoding='utf8'))
print('SAVED',len(data),'VALID_IMAGES',sum((md.parent/p).exists() for p in refs),'REFERENCES',len(refs))
