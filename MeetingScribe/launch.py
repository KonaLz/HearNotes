"""无窗口启动入口，并把异常写入 data/startup.log。"""
import os
import sys
import traceback
from pathlib import Path

# 统一把当前工作目录切到软件目录，确保相对路径始终指向项目自身。
root=Path(__file__).resolve().parent
os.chdir(root)
(root/'data').mkdir(exist_ok=True)
with (root/'data'/'startup.log').open('a',encoding='utf-8') as log:
    sys.stdout=log;sys.stderr=log
    try:
        from server import main
        main()
    except Exception:
        traceback.print_exc()
        if os.name=='nt':
            import ctypes
            ctypes.windll.user32.MessageBoxW(0,'启动失败，请查看软件 data 文件夹中的 startup.log。','HearNotes',16)
