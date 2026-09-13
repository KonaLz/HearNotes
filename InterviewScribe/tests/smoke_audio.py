"""Run the actual CPU diarizer and GPU ASR on a public four-speaker fixture."""
import sys
import urllib.request
import subprocess
import json
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core import atomic_json
job=ROOT/'test-data'/'four-speakers'
job.mkdir(parents=True,exist_ok=True)
audio=job/'source.wav'
if not audio.exists():
    urllib.request.urlretrieve('https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/0-four-speakers-zh.wav',audio)
atomic_json(job/'job.json',{'filename':'官方四人中文测试.wav','audio':'source.wav','speakers':4,'language':'zh','device':'auto','glossary':'','created':time.time()})
completed=subprocess.run([sys.executable,str(ROOT/'worker.py'),str(job)],cwd=ROOT)
if completed.returncode: raise SystemExit(completed.returncode)
result=json.loads((job/'result.json').read_text(encoding='utf-8'))
assert len([s for s in result['speakers'] if s!='?'])==4,result['speakers']
assert len(result['segments'])>=4
assert sum(len(s['text']) for s in result['segments'])>40
assert all(s['start']<=s['end']<=result['duration']+.5 for s in result['segments'])
print(json.dumps({'test':'actual four-speaker audio','speakers':result['speakers'],'duration':result['duration'],
 'segments':len(result['segments']),'device':result['device'],'sample':result['segments'][:3]},ensure_ascii=False),flush=True)
