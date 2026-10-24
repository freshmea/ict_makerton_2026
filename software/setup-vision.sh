#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'sudo bash software/setup-vision.sh'; exit 1; }
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
install -d -m 0755 /opt/300seconds/models
python3 - "$repo" <<'PY'
from pathlib import Path
import hashlib,json,sys,urllib.request
repo=Path(sys.argv[1]);root=Path('/opt/300seconds/models')
for filename,manifest in [('yolox_nano.onnx','yolox.manifest.json'),('yunet.onnx','yunet.manifest.json')]:
    m=json.loads((repo/'software/models'/manifest).read_text());p=root/filename
    if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=m['sha256']:
        with urllib.request.urlopen(m['source'],timeout=30) as r:data=r.read(16*1024*1024)
        if hashlib.sha256(data).hexdigest()!=m['sha256']:raise ValueError('model SHA mismatch: '+filename)
        temp=p.with_suffix('.new');temp.write_bytes(data);temp.chmod(0o644);temp.replace(p)
    (root/manifest).write_text(json.dumps(m,indent=2))
PY
# Build on the actual Nano / TensorRT8 / CUDA10.2. No downloaded engine files.
/usr/src/tensorrt/bin/trtexec --onnx=/opt/300seconds/models/yolox_nano.onnx --saveEngine=/opt/300seconds/models/yolox_nano.engine --fp16 --workspace=128 --buildOnly
python3 - <<'PY'
from pathlib import Path
import hashlib,json,platform
r=Path('/opt/300seconds/models');p=r/'yolox_nano.engine'
(r/'engine.manifest.json').write_text(json.dumps({'engine_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'onnx_sha256':hashlib.sha256((r/'yolox_nano.onnx').read_bytes()).hexdigest(),'platform':platform.machine(),'precision':'FP16+FP32','sm':'5.3','tensorrt':'8.0.1','cuda':'10.2'},indent=2))
PY
