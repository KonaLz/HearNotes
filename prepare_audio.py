import sys, os
from pathlib import Path
root = Path(__file__).resolve().parent
sys.path.insert(0, str(root / '.audio-tools'))
os.environ['HF_HUB_DISABLE_XET'] = '1'
from huggingface_hub import snapshot_download
snapshot_download('Systran/faster-whisper-large-v3', local_dir=str(root / '.audio-model'), allow_patterns=['config.json', 'model.bin', 'tokenizer.json', 'vocabulary.json', 'preprocessor_config.json'])
