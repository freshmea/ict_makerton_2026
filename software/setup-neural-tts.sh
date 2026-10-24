#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'sudo bash software/setup-neural-tts.sh'; exit 1; }
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
# Keep the system Python/OpenCV/CUDA installation intact.
/opt/300seconds/ai/venv/bin/pip install --only-binary=:all: sherpa-onnx==2.0.0 sherpa-onnx-core==2.0.0
python3 - "$repo" <<'PY'
from pathlib import Path
import hashlib,json,tarfile,urllib.request,sys
root=Path('/opt/300seconds/models');root.mkdir(parents=True,exist_ok=True)
m=json.loads((Path(sys.argv[1])/'software/models/supertonic.manifest.json').read_text(encoding='utf-8-sig'))
archive=root/m['artifact'];folder=root/'sherpa-onnx-supertonic-3-tts-int8-2026-05-11'
if not archive.exists() or hashlib.sha256(archive.read_bytes()).hexdigest()!=m['sha256']:
    temporary=archive.with_suffix('.download')
    with urllib.request.urlopen(m['source'],timeout=40) as r,temporary.open('wb') as out:
        total=0
        while True:
            b=r.read(1024*1024)
            if not b:break
            total+=len(b)
            if total>m['bytes']:raise ValueError('TTS archive too large')
            out.write(b)
    if total!=m['bytes'] or hashlib.sha256(temporary.read_bytes()).hexdigest()!=m['sha256']:
        raise ValueError('TTS model SHA mismatch')
    temporary.chmod(0o644);temporary.replace(archive)
if not (folder/'vocoder.int8.onnx').exists():
    with tarfile.open(archive) as tar:
        for entry in tar.getmembers():
            p=(root/entry.name).resolve()
            if root.resolve() not in p.parents or entry.issym() or entry.islnk() or not (entry.isdir() or entry.isfile()):
                raise ValueError('invalid TTS archive path')
        tar.extractall(root)
for p in folder.rglob('*'):p.chmod(0o755 if p.is_dir() else 0o644)
folder.chmod(0o755)
m['files']={str(p.relative_to(folder)):hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()}
(root/'supertonic.manifest.json').write_text(json.dumps(m,indent=2))
print(json.dumps({'model_ready':str(folder),'sha256':m['sha256'],'files':len(m['files'])}))
PY
