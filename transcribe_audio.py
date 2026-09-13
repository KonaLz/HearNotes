import sys, os, json, time
from pathlib import Path
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root/'.audio-tools'))
dll_handles=[]
for p in (root/'.audio-tools'/'nvidia').rglob('bin'):
    os.environ['PATH']=str(p)+os.pathsep+os.environ.get('PATH','')
    dll_handles.append(os.add_dll_directory(str(p)))
import av
from faster_whisper import WhisperModel
src=r'C:\Users\joe00\AppData\Local\Temp\codex-file-preview-dIOkE9\20260912 三協商事.MP3'
c=av.open(src)
print('AUDIO',c.duration/av.time_base,[(s.type,s.codec_context.name,s.codec_context.channels) for s in c.streams],flush=True)
c.close()
model=WhisperModel(str(root/'.audio-model'),device='cuda',compute_type='float16')
review='--review' in sys.argv
extra={}
if review:
    extra={'clip_timestamps':'124,166,2160,2268,3104,3135,3230,3508,3615,3708,4032,4082,4240,4335,4480,4540,4620,4705,4888,5140,5190,5225,5350,5438','initial_prompt':'面接。食品工学、商社、営業、調達、納期、輸入、粗利益、長所、短所。Power Apps、Python、ガントチャート、DX、基幹システム、Google Workspace、Slack、Salesforce、Agentforce、Gemini、ChatGPT、Claude。商品部、管理部、有給休暇。'}
segments,info=model.transcribe(src,language='ja',beam_size=5,vad_filter=not review,word_timestamps=True,condition_on_previous_text=False,**extra)
out=root/('interview_review.jsonl' if review else 'interview_raw.jsonl')
with out.open('w',encoding='utf-8') as f:
    for seg in segments:
        row=seg._asdict(); row['words']=[w._asdict() for w in seg.words] if seg.words else []
        f.write(json.dumps(row,ensure_ascii=False)+'\n'); f.flush()
        print(f'{seg.start:.1f}-{seg.end:.1f} {seg.text}',flush=True)
print('DONE',flush=True)
