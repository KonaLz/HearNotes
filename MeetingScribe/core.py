"""转写文字与说话人对齐、编辑校验和导出。"""
import json
import math
import os
import threading
import time
import uuid
from pathlib import Path

UNKNOWN = '?'

def atomic_json(path, data):
    """并发安全地保存 JSON；Windows 短暂占用目标文件时自动重试。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f'.{path.name}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp')
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        for attempt in range(8):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == 7:
                    raise
                time.sleep(.025 * (attempt + 1))
    finally:
        tmp.unlink(missing_ok=True)

def letter(index):
    text = ''
    while index >= 0:
        text = chr(65 + index % 26) + text
        index = index // 26 - 1
    return text

def speaker_map(turns):
    # 模型返回的说话人编号可能不连续；按首次出现顺序统一映射为 A、B、C。
    ordered = sorted(turns, key=lambda t: t['start'])
    ids = list(dict.fromkeys(t['speaker'] for t in ordered))
    return {identity: letter(i) for i, identity in enumerate(ids)}

def assign_speaker(start, end, turns):
    """Use temporal coverage; never infer a person's identity from the text."""
    end = max(end, start + .02)
    scores = {}
    # 用时间重叠长度判断归属，不根据文字内容猜测说话人身份。
    for turn in turns:
        overlap = max(0., min(end, turn['end']) - max(start, turn['start']))
        if overlap:
            key = turn['speaker']
            scores[key] = scores.get(key, 0.) + overlap
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    if not ranked:
        return UNKNOWN, True
    best, overlap = ranked[0]
    ambiguous = overlap / (end - start) < .5 or (len(ranked) > 1 and ranked[1][1] > .25 * (end - start))
    return best, ambiguous

def align_segments(segments, turns):
    # 将 Whisper 的词级时间戳切成适合校对的短段，并附上待核标记。
    mapping = speaker_map(turns)
    canonical = [dict(t, speaker=mapping[t['speaker']]) for t in turns]
    blocks = []
    for seg in segments:
        words = seg.get('words') or [{'start': seg['start'], 'end': seg['end'], 'word': seg['text'], 'probability': 0.5}]
        for word in words:
            text = word['word']
            if not text.strip():
                continue
            start, end = float(word['start']), float(word['end'])
            sp, uncertain = assign_speaker(start, end, canonical)
            reasons = []
            if uncertain:
                reasons.append('说话人边界或重叠不确定')
            if seg.get('avg_logprob', 0) < -.6 or word.get('probability', 1) < .35:
                reasons.append('文字需回听核对')
            previous = blocks[-1] if blocks else None
            if (previous and previous['speaker'] == sp and start - previous['end'] < 1.3
                    and end - previous['start'] < 28 and len(previous['text']) < 260):
                previous['text'] += text
                previous['end'] = max(previous['end'], end)
                previous['flags'] = list(dict.fromkeys(previous['flags'] + reasons))
            else:
                blocks.append({'id': len(blocks), 'start': start, 'end': max(start + .02, end),
                               'speaker': sp, 'text': text, 'flags': reasons, 'reviewed': False})
    for block in blocks:
        block['text'] = block['text'].strip()
    names = {sp: '说话人 ' + sp for sp in mapping.values()}
    if any(b['speaker'] == UNKNOWN for b in blocks):
        names[UNKNOWN] = '待确认'
    return blocks, names, canonical

def apply_edits(result, payload):
    """Names are a single global map; segment identity never contains a name."""
    # revision 用来防止两个页面同时保存时互相覆盖。
    if payload.get('revision') != result.get('revision', 0):
        raise ValueError('这份记录已在另一个页面更新。请刷新后再修改，避免覆盖。')
    names = payload.get('speakers')
    edits = payload.get('segments')
    if not isinstance(names, dict) or not 1 <= len(names) <= 53:
        raise ValueError('说话人列表无效。')
    allowed = {letter(i) for i in range(52)} | {UNKNOWN}
    if any(k not in allowed or not isinstance(v, str) or not 1 <= len(v.strip()) <= 60 for k, v in names.items()):
        raise ValueError('说话人名称请填写1到60个字。')
    if not isinstance(edits, list) or len(edits) != len(result['segments']):
        raise ValueError('段落数量发生变化，请刷新重试。')
    by_id = {s['id']: s for s in edits if isinstance(s, dict)}
    if len(by_id) != len(edits):
        raise ValueError('段落编号重复。')
    updated = json.loads(json.dumps(result))
    for segment in updated['segments']:
        edit = by_id.get(segment['id'], {})
        text = edit.get('text')
        if edit.get('speaker') not in names or not isinstance(text, str) or len(text) > 20000:
            raise ValueError('段落内容或说话人无效。')
        segment.update(text=text, speaker=edit['speaker'], reviewed=bool(edit.get('reviewed', False)))
    updated['speakers'] = {k: v.strip() for k, v in names.items()}
    updated['revision'] = result.get('revision', 0) + 1
    return updated

def timestamp(seconds, subtitle=False):
    ms = max(0, round(float(seconds) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f'{h:02}:{m:02}:{s:02},{ms:03}' if subtitle else f'{h:02}:{m:02}:{s:02}'

def export(result, kind):
    # 导出使用保存后的全局名字，因此一次改名即可同步所有格式。
    if kind == 'json':
        return json.dumps(result, ensure_ascii=False, indent=2)
    lines = []
    if kind != 'srt':
        lines = [('# ' if kind == 'md' else '') + result['filename'], '',
                 '本地自动转写与声音分组；时间、文字及说话人可能有误，未标记已校对的内容请回听确认。', '']
    for i, seg in enumerate(result['segments'], 1):
        name = result['speakers'].get(seg['speaker'], seg['speaker'])
        if kind == 'srt':
            lines.extend([str(i), timestamp(seg['start'], True) + ' --> ' + timestamp(seg['end'], True),
                          f'[{name}] {seg["text"]}', ''])
        else:
            label = f'[{timestamp(seg["start"])}–{timestamp(seg["end"])}] {name}（{seg["speaker"]}）'
            if kind == 'md': label = '**' + label.replace('*', '\\*') + '**'
            lines.extend([label, seg['text']])
            if seg.get('flags') and not seg.get('reviewed'):
                lines.append('［待核：' + '；'.join(seg['flags']) + '］')
            lines.append('')
    return '\n'.join(lines)
