"""解析本机已有的语音运行环境；转写时不联网。"""
import json
import os
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parent
FROZEN = bool(getattr(sys, 'frozen', False))
# 桌面版把大型资源作为 Tauri 文件安装在 EXE 旁边，避免 PyInstaller
# 单文件格式的 4 GB 上限，也避免每次启动都把模型解压到临时目录。
APP_ROOT = Path(sys.executable).resolve().parent if FROZEN else SOURCE_ROOT
ROOT = APP_ROOT if FROZEN else SOURCE_ROOT
WORKSPACE = APP_ROOT if FROZEN else ROOT.parent
DATA_ROOT = APP_ROOT / 'data' if FROZEN else ROOT / 'data'
HANDLES = []

def setup_runtime():
    # 把项目自带组件放到模块搜索路径最前面，避免使用到系统中的其他版本。
    cuda_runtime = ROOT / 'runtime-cuda'
    speaker_runtime = cuda_runtime if (cuda_runtime / 'sherpa_onnx').is_dir() else ROOT / 'runtime'
    audio_tools = WORKSPACE / '.audio-tools'
    # 安装版把 Python 扩展作为 Tauri 资源放在 EXE 旁边。将它们放到
    # sys.path 最前面，并提前登记扩展所在目录，避免 PyInstaller 临时目录
    # 中的同名但不完整副本抢先被加载。
    for path in [audio_tools, speaker_runtime]:
        sys.path.insert(0, str(path))
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    if os.name == 'nt':
        dll_roots = [
            audio_tools,
            audio_tools / 'av.libs',
            audio_tools / 'av',
            audio_tools / 'ctranslate2',
            WORKSPACE / '.audio-tools' / 'nvidia',
            WORKSPACE / '.audio-cuda-libs' / 'nvidia',
            WORKSPACE / '.audio-cuda-runtime' / 'nvidia',
        ]
        for root in dll_roots:
            if not root.is_dir():
                continue
            candidates = [root] + list(root.rglob('bin'))
            for path in candidates:
                os.environ['PATH'] = str(path) + os.pathsep + os.environ.get('PATH', '')
                try:
                    HANDLES.append(os.add_dll_directory(str(path)))
                except OSError:
                    pass

def paths_ready():
    # 启动页用这些结果判断“开始转写”按钮是否可以使用。
    asr_path = WORKSPACE / '.audio-model'
    voice_path = ROOT / 'models'
    state_file = DATA_ROOT / 'models.json'
    if state_file.is_file():
        try:
            active = json.loads(state_file.read_text(encoding='utf-8'))['active']
            saved_asr = Path(active['asr']['path'])
            saved_voice = Path(active['voices']['path'])
            if (saved_asr / 'model.bin').is_file():
                asr_path = saved_asr
            if (saved_voice / 'segmentation.onnx').is_file() and (saved_voice / 'speaker.onnx').is_file():
                voice_path = saved_voice
        except (OSError, ValueError, KeyError, TypeError):
            pass
    needed = {
        '日语／多语言转写模型': asr_path / 'model.bin',
        '语音分段模型': voice_path / 'segmentation.onnx',
        '说话人声音模型': voice_path / 'speaker.onnx',
        '语音转写组件': WORKSPACE / '.audio-tools' / 'faster_whisper' / '__init__.py',
        '说话人识别组件': ((ROOT / 'runtime-cuda' / 'sherpa_onnx' / '__init__.py')
                         if (ROOT / 'runtime-cuda' / 'sherpa_onnx').is_dir()
                         else (ROOT / 'runtime' / 'sherpa_onnx' / '__init__.py')),
    }
    return {name: p.is_file() for name, p in needed.items()}
