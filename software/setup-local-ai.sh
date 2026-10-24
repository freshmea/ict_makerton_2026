#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'sudo bash software/setup-local-ai.sh'; exit 1; }
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-kor espeak-ng python3-venv unzip
install -d -o root -g root -m 0755 /opt/300seconds/models /opt/300seconds/ai
test -x /opt/300seconds/ai/venv/bin/python || python3 -m venv --system-site-packages /opt/300seconds/ai/venv
/opt/300seconds/ai/venv/bin/pip install --disable-pip-version-check 'vosk==0.3.45'
if ! test -d /opt/300seconds/models/vosk-model-small-ko-0.22; then
  archive=$(mktemp /tmp/300seconds-vosk-XXXXXX.zip)
  trap 'rm -f -- "$archive"' EXIT
  curl --fail --location --proto '=https' --tlsv1.2 --connect-timeout 15 --max-time 600 'https://alphacephei.com/vosk/models/vosk-model-small-ko-0.22.zip' -o "$archive"
  unzip -q "$archive" -d /opt/300seconds/models
fi
python3 - <<'PY'
import hashlib,json,pathlib
root=pathlib.Path('/opt/300seconds/models')
files={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted((root/'vosk-model-small-ko-0.22').rglob('*')) if p.is_file()}
(root/'vosk-ko.manifest.json').write_text(json.dumps({'source':'https://alphacephei.com/vosk/models/vosk-model-small-ko-0.22.zip','license':'Apache-2.0','sha256_observed_after_https_download':files},indent=2))
PY
echo 'Local ASR and Korean OCR installed. TTS uses Typecast; neural local TTS is optional. No service started.'
