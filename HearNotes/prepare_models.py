"""One-time model download. Only official public model files are requested."""
from pathlib import Path
import urllib.request
import tarfile
import hashlib

# 本脚本只负责准备/检查本地模型；正式转写由 worker.py 执行。
import json
import shutil

ROOT = Path(__file__).resolve().parent
MODELS = ROOT / 'models'
MODELS.mkdir(exist_ok=True)
SOURCES = {
    'segmentation.tar.bz2': 'https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2',
    'speaker.onnx': 'https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx',
}
manifest = {}
for name, url in SOURCES.items():
    target = MODELS / name
    if not target.exists():
        print('Downloading', name, flush=True)
        req = urllib.request.Request(url, headers={'User-Agent': 'HearNotes/1.0'})
        with urllib.request.urlopen(req, timeout=90) as response, target.with_suffix('.part').open('wb') as out:
            shutil.copyfileobj(response, out, 1024 * 1024)
        target.with_suffix('.part').replace(target)
    manifest[name] = {'source': url, 'sha256': hashlib.file_digest(target.open('rb'), 'sha256').hexdigest()}
with tarfile.open(MODELS / 'segmentation.tar.bz2') as archive:
    for member in archive.getmembers():
        name = Path(member.name).name
        if name in {'model.onnx', 'LICENSE', 'README.md'} and member.isfile():
            target = MODELS / ('segmentation.onnx' if name == 'model.onnx' else 'segmentation-' + name)
            with archive.extractfile(member) as src, target.open('wb') as out:
                shutil.copyfileobj(src, out)
(MODELS / 'sources.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
print('Models ready', flush=True)
