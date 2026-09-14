"""可选的官方模型更新；采用版本目录，不覆盖正在使用的旧模型。"""
import json
import hashlib
import shutil
import tarfile
import time
import urllib.request
from pathlib import Path
from bootstrap import ROOT, WORKSPACE, DATA_ROOT
from core import atomic_json

STATE = DATA_ROOT / 'models.json'
REPO = 'Systran/faster-whisper-large-v3'
FILES = {'model.bin', 'config.json', 'tokenizer.json', 'vocabulary.json', 'preprocessor_config.json'}

def defaults():
    revision = 'bundled'
    metadata = WORKSPACE / '.audio-model' / '.cache' / 'huggingface' / 'download' / 'model.bin.metadata'
    if metadata.is_file():
        try: revision = metadata.read_text().splitlines()[0].strip()
        except (OSError, IndexError): pass
    return {'active': {'asr': {'path': str(WORKSPACE / '.audio-model'), 'revision': revision},
                       'voices': {'path': str(ROOT / 'models'), 'revision': 'bundled'}},
            'previous': None, 'check_on_start': True, 'preferences_version': 1}

def state():
    if STATE.is_file():
        current = json.loads(STATE.read_text(encoding='utf-8'))
        # 1.0.1 以前默认关闭启动检查；迁移一次后仍允许用户手动关闭。
        if current.get('preferences_version', 0) < 1:
            current['check_on_start'] = True
            current['preferences_version'] = 1
            STATE.parent.mkdir(parents=True, exist_ok=True)
            atomic_json(STATE, current)
        bundled = defaults()
        active = current.setdefault('active', {})
        asr = Path(active.get('asr', {}).get('path', ''))
        voices = Path(active.get('voices', {}).get('path', ''))
        if not (asr / 'model.bin').is_file():
            active['asr'] = bundled['active']['asr']
        if not ((voices / 'segmentation.onnx').is_file() and (voices / 'speaker.onnx').is_file()):
            active['voices'] = bundled['active']['voices']
        return current
    return defaults()

def save(data):
    STATE.parent.mkdir(exist_ok=True)
    atomic_json(STATE, data)

def fetch_json(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'HearNotes/1.0', 'Accept': 'application/json'})
    with urllib.request.urlopen(request, timeout=35) as response:
        return json.load(response)

def check():
    # 检查远端版本和文件摘要，只生成计划，不会自动下载模型。
    current = state()
    hf = fetch_json('https://huggingface.co/api/models/' + REPO + '?blobs=true')
    assets = []
    for tag, filename in [
        ('speaker-segmentation-models', 'sherpa-onnx-pyannote-segmentation-3-0.tar.bz2'),
        ('speaker-recongition-models', '3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx')]:
        release = fetch_json('https://api.github.com/repos/k2-fsa/sherpa-onnx/releases/tags/' + tag)
        asset = next(a for a in release['assets'] if a['name'] == filename)
        assets.append({k: asset.get(k) for k in ['name', 'updated_at', 'size', 'digest', 'browser_download_url']})
    voice_revision = hashlib.sha256(json.dumps(assets, sort_keys=True).encode()).hexdigest()[:16]
    asr_files = [s for s in hf['siblings'] if s['rfilename'] in FILES]
    if not {'config.json', 'model.bin', 'tokenizer.json'}.issubset({s['rfilename'] for s in asr_files}):
        raise RuntimeError('官方模型结构发生变化，当前版本不能自动更新。现有模型仍可使用。')
    voices_available = current['active']['voices']['revision'] != voice_revision
    # Establish bundled identity only if remote digests match the downloaded files.
    manifest_file = ROOT / 'models' / 'sources.json'
    if current['active']['voices']['revision'] == 'bundled' and manifest_file.is_file():
        manifest = json.loads(manifest_file.read_text())
        expected = [manifest['segmentation.tar.bz2']['sha256'], manifest['speaker.onnx']['sha256']]
        if all(a.get('digest') == 'sha256:' + digest for a, digest in zip(assets, expected)):
            current['active']['voices']['revision'] = voice_revision
            save(current)
            voices_available = False
    return {'checked': time.time(), 'asr_revision': hf['sha'], 'voice_revision': voice_revision,
            'asr_available': current['active']['asr']['revision'] != hf['sha'],
            'voices_available': voices_available, 'files': asr_files, 'assets': assets,
            'asr_bytes': sum(s.get('size', s.get('lfs', {}).get('size', 0)) for s in asr_files),
            'voice_bytes': sum(a.get('size', 0) for a in assets)}

def download(url, dest, size, digest, notify):
    # 先写入 .part 临时文件，校验长度和 SHA-256 后才改名为正式文件。
    request = urllib.request.Request(url, headers={'User-Agent': 'HearNotes/1.0'})
    partial = dest.with_name(dest.name + '.part')
    actual = hashlib.sha256()
    done = 0
    with urllib.request.urlopen(request, timeout=90) as response, partial.open('wb') as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk); actual.update(chunk); done += len(chunk)
            notify(done, size or done)
    if size and done != size:
        raise RuntimeError('下载长度与官方文件不一致，未启用新版。')
    if digest and actual.hexdigest() != digest.removeprefix('sha256:'):
        raise RuntimeError('模型校验失败，未启用新版。请重新下载。')
    partial.replace(dest)

def install(plan, notify):
    if not plan:
        raise ValueError('请先检查更新。')
    # 新版本放在独立目录，最后只切换 models.json 中的指针。
    current = state()
    candidate = json.loads(json.dumps(current['active']))
    versions = DATA_ROOT / 'models' / 'versions'
    versions.mkdir(parents=True, exist_ok=True)
    stamp = str(time.time_ns())
    changed = False
    if plan['asr_available']:
        prefix = 'asr-' + plan['asr_revision'][:10] + '-'
        reusable = []
        for existing in versions.glob(prefix + '*'):
            if all((existing / item['rfilename']).is_file() and
                   (not item.get('size') or (existing / item['rfilename']).stat().st_size == item['size'])
                   for item in plan['files']):
                reusable.append(existing)
        if reusable:
            folder = max(reusable, key=lambda path: path.stat().st_mtime)
            notify('使用已下载的转写模型', 92)
        else:
            folder = versions / (prefix + stamp)
            folder.mkdir()
            for item in plan['files']:
                name = item['rfilename']
                notify('下载转写模型：' + name, 0)
                download('https://huggingface.co/' + REPO + '/resolve/' + plan['asr_revision'] + '/' + name,
                         folder / name, item.get('size', 0), item.get('lfs', {}).get('sha256'),
                         lambda a,b: notify('下载转写模型：' + name, round(a / b * 100, 1)))
        candidate['asr'] = {'path': str(folder), 'revision': plan['asr_revision']}
        changed = True
    if plan['voices_available']:
        reusable = [path for path in versions.glob('voices-*')
                    if (path / 'segmentation.onnx').is_file() and
                    (path / 'speaker.onnx').is_file()]
        if reusable:
            folder = max(reusable, key=lambda path: path.stat().st_mtime)
            notify('使用已下载的说话人模型', 96)
        else:
            folder = versions / ('voices-' + stamp)
            folder.mkdir()
            for i, item in enumerate(plan['assets']):
                name = 'segmentation.tar.bz2' if i == 0 else 'speaker.onnx'
                download(item['browser_download_url'], folder / name, item['size'], item.get('digest'),
                         lambda a,b: notify('下载说话人模型：' + name, round(a / b * 100, 1)))
            with tarfile.open(folder / 'segmentation.tar.bz2') as archive:
                for member in archive.getmembers():
                    name = Path(member.name).name
                    if member.isfile() and name in {'model.onnx', 'LICENSE', 'README.md'}:
                        dest = folder / ('segmentation.onnx' if name == 'model.onnx' else 'segmentation-' + name)
                        with archive.extractfile(member) as src, dest.open('wb') as output:
                            shutil.copyfileobj(src, output)
        candidate['voices'] = {'path': str(folder), 'revision': plan['voice_revision']}
        changed = True
    if not changed:
        return current
    notify('验证模型能否加载', 98)
    # Readability / inference-format check before changing the pointer.
    from bootstrap import setup_runtime
    setup_runtime()
    from faster_whisper import WhisperModel
    import sherpa_onnx
    if plan['asr_available']:
        probe = WhisperModel(candidate['asr']['path'], device='cpu', compute_type='int8', cpu_threads=2)
        del probe
    if plan['voices_available']:
        config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
            segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
                pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(
                    model=str(Path(candidate['voices']['path']) / 'segmentation.onnx'))),
            embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(Path(candidate['voices']['path']) / 'speaker.onnx')),
            # Sherpa-ONNX requires clustering even for the load-only validation.
            # Use automatic cluster estimation here; the recording job applies
            # the user's requested speaker count when it actually diarizes.
            clustering=sherpa_onnx.FastClusteringConfig(num_clusters=-1, threshold=.5))
        probe = sherpa_onnx.OfflineSpeakerDiarization(config)
        del probe
    current['previous'] = current['active']
    current['active'] = candidate
    save(current)
    return current

def rollback():
    current = state()
    if not current.get('previous'):
        raise ValueError('还没有可以退回的旧版本。')
    current['active'], current['previous'] = current['previous'], current['active']
    save(current)
    return current
