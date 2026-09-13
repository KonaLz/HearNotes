"""解析本机已有的语音运行环境；转写时不联网。"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parent
HANDLES = []

def setup_runtime():
    # 把项目自带组件放到模块搜索路径最前面，避免使用到系统中的其他版本。
    cuda_runtime = ROOT / 'runtime-cuda'
    speaker_runtime = cuda_runtime if (cuda_runtime / 'sherpa_onnx').is_dir() else ROOT / 'runtime'
    for path in [WORKSPACE / '.audio-tools', speaker_runtime]:
        sys.path.insert(0, str(path))
    os.environ['HF_HUB_OFFLINE'] = '1'
    os.environ['TRANSFORMERS_OFFLINE'] = '1'
    os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
    if os.name == 'nt':
        dll_roots = [
            WORKSPACE / '.audio-tools' / 'nvidia',
            WORKSPACE / '.audio-cuda-libs' / 'nvidia',
            WORKSPACE / '.audio-cuda-runtime' / 'nvidia',
        ]
        for root in dll_roots:
            for path in root.rglob('bin') if root.is_dir() else []:
                os.environ['PATH'] = str(path) + os.pathsep + os.environ.get('PATH', '')
                HANDLES.append(os.add_dll_directory(str(path)))

def paths_ready():
    # 启动页用这些结果判断“开始转写”按钮是否可以使用。
    needed = {
        '日语／多语言转写模型': WORKSPACE / '.audio-model' / 'model.bin',
        '语音分段模型': ROOT / 'models' / 'segmentation.onnx',
        '说话人声音模型': ROOT / 'models' / 'speaker.onnx',
        '语音转写组件': WORKSPACE / '.audio-tools' / 'faster_whisper' / '__init__.py',
        '说话人识别组件': ((ROOT / 'runtime-cuda' / 'sherpa_onnx' / '__init__.py')
                         if (ROOT / 'runtime-cuda' / 'sherpa_onnx').is_dir()
                         else (ROOT / 'runtime' / 'sherpa_onnx' / '__init__.py')),
    }
    return {name: p.is_file() for name, p in needed.items()}
