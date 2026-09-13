"""每条录音使用一个可取消的子进程处理；处理阶段不访问网络。"""
import sys
import json
import time
import traceback
import gc
import os
import threading
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from dataclasses import asdict
from bootstrap import ROOT, WORKSPACE, setup_runtime
from core import atomic_json, align_segments
from models import state as model_state

def run(job):
    # 处理顺序：解码音频 → 说话人分离 → Whisper 转写 → 时间对齐 → 保存结果。
    setup_runtime()
    import numpy as np
    from faster_whisper.audio import decode_audio
    import sherpa_onnx
    folder = Path(job)
    options = json.loads((folder / 'job.json').read_text(encoding='utf-8'))
    started = time.time()
    active = model_state()['active']
    voice_path = Path(active['voices']['path'])
    asr_path = active['asr']['path']
    progress_lock = threading.Lock()
    progress_value = 0
    def progress(stage, value, **kwargs):
        nonlocal progress_value
        with progress_lock:
            progress_value = max(progress_value, value)
            atomic_json(folder / 'progress.json', {'status': 'running', 'stage': stage,
                'progress': round(progress_value, 1), 'elapsed': round(time.time() - started), **kwargs})
    progress('读取录音', 2)
    audio = decode_audio(str(folder / options['audio']), sampling_rate=16000)
    duration = len(audio) / 16000
    if duration < .4:
        raise ValueError('录音太短，请选择包含完整讲话的录音。')
    if duration > 4 * 3600:
        raise ValueError('当前版本支持4小时以内的录音，请先分段。')
    # Standard WAV makes M4A/FLAC and other input formats seekable in any browser.
    with wave.open(str(folder / 'playback.wav'), 'wb') as output:
        output.setnchannels(1); output.setsampwidth(2); output.setframerate(16000)
        for i in range(0, len(audio), 16000 * 60):
            output.writeframes((np.clip(audio[i:i+16000*60], -1, 1) * 32767).astype('<i2').tobytes())

    quality = options.get('quality', 'balanced')
    profiles = {
        'accurate': {'window_shift': .1, 'beam_size': 5},
        'balanced': {'window_shift': .2, 'beam_size': 3},
        'fast': {'window_shift': .3, 'beam_size': 1},
    }
    profile = profiles.get(quality, profiles['balanced'])
    inference_threads = min(8, max(2, os.cpu_count() or 4))

    def run_asr():
        from faster_whisper import WhisperModel
        device = options.get('device', 'auto')
        fallback = ''
        if device in {'auto', 'cuda', 'cuda_all'}:
            try:
                model = WhisperModel(asr_path, device='cuda', compute_type='float16')
                device = 'cuda'
            except Exception:
                fallback = '显卡暂不可用，已切换为CPU；处理速度会较慢。'
                device = 'cpu'
                model = WhisperModel(asr_path, device='cpu', compute_type='int8', cpu_threads=inference_threads)
        else:
            model = WhisperModel(asr_path, device='cpu', compute_type='int8', cpu_threads=inference_threads)
        language = options['language'] or None

        def consume():
            parts, info = model.transcribe(
                audio, language=language, beam_size=profile['beam_size'], vad_filter=True,
                word_timestamps=True, condition_on_previous_text=False,
                initial_prompt=options.get('glossary', '') or None)
            rows = []
            with (folder / 'raw_segments.jsonl').open('w', encoding='utf-8') as stream:
                for part in parts:
                    row = asdict(part)
                    rows.append(row)
                    stream.write(json.dumps(row, ensure_ascii=False) + '\n')
                    stream.flush()
                    progress('转写文字', 8 + 44 * min(part.end / duration, 1), duration=duration,
                             processed=part.end, device=device, asr_device=device, note=fallback)
            return rows, info
        try:
            rows, info = consume()
        except RuntimeError as error:
            if device != 'cuda' or not any(x in str(error).lower() for x in ['cuda', 'cublas', 'cudnn', 'memory']):
                raise
            del model
            gc.collect()
            fallback = '显卡执行失败，已切换为CPU重新转写。'
            device = 'cpu'
            model = WhisperModel(asr_path, device='cpu', compute_type='int8', cpu_threads=inference_threads)
            rows, info = consume()
        return rows, info, device, fallback

    # 两个模型处理同一份内存音频：CPU/GPU 可并行工作，最后再按时间戳对齐。
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='whisper')
    asr_future = executor.submit(run_asr)
    progress('按声音区分说话人', 6, duration=duration)
    count = options['speakers']
    turns = []
    speaker_device = 'cpu'
    speaker_fallback = ''
    if count == 1:
        turns = [{'start': 0., 'end': duration, 'speaker': 0}]
    else:
        main_device = options.get('device', 'auto')
        requested_device = options.get('speaker_device', 'cuda' if main_device == 'cuda_all' else 'cpu')
        provider = 'cuda' if requested_device in {'auto', 'cuda'} else 'cpu'
        def create_diarizer(provider):
            cfg = sherpa_onnx.OfflineSpeakerDiarizationConfig(
                segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
                    pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                        model=str(voice_path / 'segmentation.onnx'), window_shift_ratio=profile['window_shift']),
                    num_threads=inference_threads, provider=provider),
                embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(
                    model=str(voice_path / 'speaker.onnx'), num_threads=inference_threads, provider=provider),
                clustering=sherpa_onnx.FastClusteringConfig(num_clusters=count if count else -1, threshold=.5),
                min_duration_on=.25, min_duration_off=.3)
            if not cfg.validate():
                raise RuntimeError('说话人模型无法加载，请检查 models 目录。')
            return sherpa_onnx.OfflineSpeakerDiarization(cfg)
        try:
            diarizer = create_diarizer(provider)
            speaker_device = provider
        except Exception:
            if provider != 'cuda': raise
            speaker_fallback = '说话人分离显卡不可用，已切换为CPU。'
            diarizer = create_diarizer('cpu')
        
        def callback(done, total):
            progress('按声音区分说话人', 8 + 44 * done / max(1, total), duration=duration,
                     speaker_device=speaker_device, note=speaker_fallback)
            return 0
        try:
            result = diarizer.process(audio, callback=callback)
        except Exception:
            if speaker_device != 'cuda': raise
            del diarizer; gc.collect()
            speaker_device = 'cpu'
            speaker_fallback = '说话人分离显卡执行失败，已切换为CPU。'
            diarizer = create_diarizer('cpu')
            result = diarizer.process(audio, callback=callback)
        for t in result.sort_by_start_time():
            turns.append({'start': float(t.start), 'end': float(t.end), 'speaker': int(t.speaker)})
        del diarizer
        gc.collect()
    atomic_json(folder / 'voice_turns.json', turns)
    try:
        rows, info, device, fallback = asr_future.result()
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
    progress('对齐文字与说话人', 97, duration=duration)
    blocks, names, canonical = align_segments(rows, turns)
    warnings = []
    if not blocks:
        warnings.append('没有识别出讲话内容。请检查音量、语言和录音。')
    elif not turns:
        warnings.append('没有可靠区分出声音，文字暂标为待确认。')
    if count and len({t['speaker'] for t in turns}) != count:
        warnings.append('实际分出的声音数量与指定人数不同，请回听确认。')
    result = {'version': 1, 'revision': 0, 'filename': options['filename'], 'duration': duration,
              'language': info.language, 'device': device, 'asr_device': device,
              'speaker_device': speaker_device, 'speaker_fallback': speaker_fallback,
              'quality': quality,
              'speakers': names or {'?': '待确认'},
              'segments': blocks, 'warnings': warnings, 'created': options['created'],
              'model_versions': active,
              'method': 'Whisper large-v3 + sherpa-onnx segmentation-3.0 / 3D-Speaker; word-time alignment'}
    atomic_json(folder / 'result.json', result)
    atomic_json(folder / 'progress.json', {'status': 'complete', 'stage': '已完成', 'progress': 100,
                'elapsed': round(time.time()-started), 'duration': duration, 'segments': len(blocks),
                'speaker_count': len(names), 'device': device, 'asr_device': device,
                'speaker_device': speaker_device,
                'note': '; '.join(x for x in [fallback, speaker_fallback] if x)})

if __name__ == '__main__':
    try:
        run(sys.argv[1])
    except BaseException as exc:
        folder = Path(sys.argv[1])
        (folder / 'error.log').write_text(traceback.format_exc(), encoding='utf-8')
        atomic_json(folder / 'progress.json', {'status': 'error', 'stage': '处理未完成',
            'progress': 0, 'error': str(exc) or type(exc).__name__})
        sys.exit(1)
