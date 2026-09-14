"""无窗口启动入口，并把异常写入 data/startup.log。"""
import os
import sys
import traceback
from pathlib import Path
from bootstrap import DATA_ROOT

# 统一把当前工作目录切到软件目录，确保相对路径始终指向项目自身。
root=Path(__file__).resolve().parent
os.chdir(root)
DATA_ROOT.mkdir(exist_ok=True)
with (DATA_ROOT/'startup.log').open('a',encoding='utf-8') as log:
    sys.stdout=log;sys.stderr=log
    try:
        if len(sys.argv) >= 2 and sys.argv[1] == '--runtime-test':
            # 仅供安装包自检：逐个加载本地扩展，日志会指出具体失败模块。
            from bootstrap import setup_runtime
            setup_runtime()
            checks = [
                ('numpy', lambda: __import__('numpy')),
                ('av._core', lambda: __import__('av._core')),
                ('ctranslate2._ext', lambda: __import__('ctranslate2._ext')),
                ('faster_whisper', lambda: __import__('faster_whisper')),
                ('sherpa_onnx', lambda: __import__('sherpa_onnx')),
            ]
            for name, check in checks:
                try:
                    check()
                    print('OK ' + name, flush=True)
                except Exception:
                    print('FAILED ' + name, flush=True)
                    traceback.print_exc()
                    raise
        elif len(sys.argv) >= 3 and sys.argv[1] == '--worker':
            from worker import main as worker_main
            worker_main(sys.argv[2])
        else:
            from server import main
            main()
    except Exception:
        traceback.print_exc()
        if os.name=='nt':
            import ctypes
            ctypes.windll.user32.MessageBoxW(0,'启动失败，请查看软件 data 文件夹中的 startup.log。','HearNotes',16)
