"""本机网页服务：负责上传、任务管理、编辑保存、导出和模型更新。"""
import argparse
import hmac
import json
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from bootstrap import ROOT, DATA_ROOT, FROZEN, paths_ready
from core import atomic_json, apply_edits, export
import models

DATA = DATA_ROOT
JOBS = DATA / 'jobs'
INSTANCE = DATA / 'instance.json'
for folder in [DATA, JOBS]: folder.mkdir(exist_ok=True)
MAX_UPLOAD = 1024 ** 3
EXTENSIONS = {'.mp3', '.wav', '.m4a', '.mp4', '.aac', '.flac', '.ogg', '.webm', '.wma', '.opus'}
TAURI_ORIGINS = {'http://tauri.localhost', 'https://tauri.localhost', 'tauri://localhost'}

def read_json(path, default=None):
    try: return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError): return default

class Manager:
    def __init__(self):
        # Manager 只允许同时处理一条录音，避免 GPU/模型资源互相争用。
        self.lock = threading.RLock()
        self.process = None
        self.active_id = None
        self.maintenance = False
        self.update = {'status': 'idle', 'stage': '尚未检查更新', 'progress': 0}
        self.plan = None
        for folder in JOBS.iterdir():
            p = read_json(folder / 'progress.json', {})
            if p.get('status') in {'running', 'uploading'}:
                atomic_json(folder / 'progress.json', {'status': 'interrupted', 'stage': '上次运行被中断，可重新处理',
                    'stage_key': 'interrupted', 'progress': 0})

    def busy(self):
        return self.maintenance or (self.process is not None and self.process.poll() is None)

    def folder(self, identity):
        if not re.fullmatch(r'[a-f0-9]{32}', identity): raise ValueError('记录编号无效。')
        folder = JOBS / identity
        if not folder.is_dir(): raise ValueError('记录不存在。')
        return folder

    def start(self, folder):
        # 转写放在独立子进程中，取消任务时可以安全终止该进程。
        with self.lock:
            if self.busy(): raise ValueError('已有任务正在进行，请等完成后再开始。')
            log = (folder / 'worker.log').open('w', encoding='utf-8')
            try:
                command = ([sys.executable, '--worker', str(folder)] if FROZEN else
                           [sys.executable, str(ROOT / 'worker.py'), str(folder)])
                self.process = subprocess.Popen(command,
                    cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            finally: log.close()
            self.active_id = folder.name
            atomic_json(folder / 'progress.json', {'status': 'running', 'stage': '正在准备',
                'stage_key': 'preparing', 'progress': 0})

    def summary(self, folder):
        meta = read_json(folder / 'job.json', {})
        status = read_json(folder / 'progress.json', {'status': 'interrupted', 'stage': '尚未完成', 'progress': 0})
        if (folder.name == self.active_id and self.process is not None and self.process.poll() is not None
                and status.get('status') == 'running'):
            status.update(status='error', stage='任务意外退出；可重新处理', stage_key='unexpectedExit',
                          error='请重试，或改用CPU模式。日志保存在记录目录。')
            atomic_json(folder / 'progress.json', status)
        return {**meta, **status, 'id': folder.name, 'has_result': (folder / 'result.json').is_file()}

    def cancel(self, identity):
        with self.lock:
            folder = self.folder(identity)
            if identity != self.active_id or not self.process or self.process.poll() is not None:
                raise ValueError('该记录当前没有正在运行的任务。')
            self.process.terminate()
            try: self.process.wait(timeout=10)
            except subprocess.TimeoutExpired: self.process.kill(); self.process.wait()
            atomic_json(folder / 'progress.json', {'status': 'cancelled', 'stage': '已取消，可重新处理',
                'stage_key': 'cancelled', 'progress': 0})

    def delete(self, identity):
        """删除一条录音及其转写、播放文件和日志。"""
        with self.lock:
            folder = self.folder(identity)
            if identity == self.active_id and self.process is not None and self.process.poll() is None:
                raise ValueError('请先取消正在处理的任务，再删除这条记录。')
            shutil.rmtree(folder)
            if identity == self.active_id:
                self.active_id = None
                self.process = None

    def update_action(self, action):
        # 模型更新在后台线程执行，网页仍可查询进度；失败时保留旧模型。
        with self.lock:
            if self.busy(): raise ValueError('正在转写、导入或更新，请稍后再操作模型。')
            if action == 'rollback':
                models.rollback(); self.plan = None
                self.update = {'status': 'complete', 'stage': '已切换到上一版模型', 'progress': 100}
                return
            if action == 'install' and not self.plan: raise ValueError('请先检查更新。')
            self.maintenance = True
            self.update = {'status': 'running', 'stage': '正在检查可下载模型' if action in {'check', 'bootstrap'} else '准备下载', 'progress': 0}
        def task():
            try:
                if action == 'check':
                    plan = models.check()
                    with self.lock: self.plan = plan
                    stage = '有可用更新／可同步官方版本' if plan['asr_available'] or plan['voices_available'] else '当前模型已是最新版本'
                else:
                    if action == 'bootstrap':
                        plan = models.check()
                        with self.lock: self.plan = plan
                    def notify(stage, value):
                        with self.lock: self.update = {'status': 'running', 'stage': stage, 'progress': value}
                    models.install(self.plan, notify)
                    with self.lock: self.plan = None
                    stage = '模型已更新，下一次转写将使用新版'
                with self.lock: self.update = {'status': 'complete', 'stage': stage, 'progress': 100}
            except Exception as error:
                with self.lock:
                    current = models.state()
                    asr_ready = Path(current['active']['asr']['path']) / 'model.bin'
                    voice_root = Path(current['active']['voices']['path'])
                    old_ready = (asr_ready.is_file() and
                                 (voice_root / 'segmentation.onnx').is_file() and
                                 (voice_root / 'speaker.onnx').is_file())
                    stage = '更新未完成，原模型仍可使用' if old_ready else '模型安装失败，尚未启用'
                    self.update = {'status': 'error', 'stage': stage, 'error': str(error), 'progress': 0}
            finally:
                with self.lock: self.maintenance = False
        threading.Thread(target=task, daemon=True).start()

class Handler(BaseHTTPRequestHandler):
    server_version = 'HearNotes/1.0'
    def log_message(self, *args): pass

    def authenticated(self):
        # 启动时生成的随机 Cookie 只用于保护本机端口，避免被其他网页调用。
        cookie = self.headers.get('Cookie', '')
        token = next((v.partition('=')[2] for v in cookie.split('; ') if v.startswith('scribe=')), '')
        if os.environ.get('HEARNOTES_TAURI') == '1' and self.valid_host():
            return self.request_origin() in TAURI_ORIGINS
        return hmac.compare_digest(token, self.server.key)

    def request_origin(self):
        origin = self.headers.get('Origin', '')
        if origin: return origin.rstrip('/')
        referer = self.headers.get('Referer', '')
        if referer:
            parsed = urllib.parse.urlparse(referer)
            return f'{parsed.scheme}://{parsed.netloc}'.rstrip('/')
        return ''

    def cors_headers(self):
        origin = self.headers.get('Origin', '').rstrip('/')
        if origin in TAURI_ORIGINS:
            return {
                'Access-Control-Allow-Origin': origin,
                'Access-Control-Allow-Headers': 'Content-Type, X-Local-App',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
                'Access-Control-Expose-Headers': 'Content-Disposition, Content-Length',
                'Vary': 'Origin',
            }
        return {}

    def send_bytes(self, body, kind='application/json; charset=utf-8', status=200, headers=None):
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; media-src 'self' blob:; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'")
        combined = {**self.cors_headers(), **(headers or {})}
        for k,v in combined.items(): self.send_header(k,v)
        self.end_headers()
        try: self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError): pass

    def reply(self, data, status=200):
        self.send_bytes(json.dumps(data, ensure_ascii=False).encode(), status=status)

    def valid_host(self):
        return self.headers.get('Host') in {
            f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}',
            '127.0.0.1:28661', 'localhost:28661'}

    def do_OPTIONS(self):
        if not self.valid_host() or self.request_origin() not in TAURI_ORIGINS:
            return self.send_bytes(b'', status=403)
        self.send_bytes(b'', status=204)

    def do_GET(self):
        try:
            if not self.valid_host(): return self.reply({'error': 'Host rejected'}, 403)
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            if parsed.path == '/' and 'key' in query and hmac.compare_digest(query['key'][0], self.server.key):
                return self.send_bytes(b'', status=303, headers={'Location': '/', 'Set-Cookie': f'scribe={self.server.key}; Path=/; HttpOnly; SameSite=Strict'})
            if not self.authenticated():
                return self.send_bytes('请通过 HearNotes 桌面应用打开，或从源码运行 launch.py。'.encode(), 'text/plain; charset=utf-8', 403)
            path = parsed.path
            manager = self.server.manager
            # 静态页面和脚本也必须经过同一个本机 Cookie 校验。
            static_files = {
                '/': 'index.html',
                '/app.js': 'app.js',
                '/i18n.js': 'i18n.js',
                '/style.css': 'style.css',
                '/brand.css': 'brand.css',
                '/assets/hearnotes-icon.png': 'assets/hearnotes-icon.png',
            }
            if path in static_files:
                name = static_files[path]
                return self.send_bytes((ROOT / 'ui' / name).read_bytes(), mimetypes.guess_type(name)[0] + '; charset=utf-8')
            if path == '/api/config':
                with manager.lock:
                    plan = manager.plan
                    update_available = bool(plan and
                                            (plan.get('asr_available') or plan.get('voices_available')))
                    return self.reply({'ready': paths_ready(), 'busy': manager.busy(),
                                       'model_update': manager.update,
                                       'model_update_available': update_available,
                                       'version': '1.1.5'})
            if path == '/api/jobs':
                records = [manager.summary(f) for f in JOBS.iterdir() if f.is_dir() and (f/'job.json').is_file()]
                return self.reply(sorted(records, key=lambda x: x.get('created', 0), reverse=True))
            if path == '/api/models':
                with manager.lock:
                    current = models.state()
                    asr = Path(current['active']['asr']['path'])
                    voices = Path(current['active']['voices']['path'])
                    model_ready = {
                        'asr': (asr / 'model.bin').is_file(),
                        'voices': (voices / 'segmentation.onnx').is_file() and (voices / 'speaker.onnx').is_file(),
                    }
                    return self.reply({'state': current, 'model_ready': model_ready,
                                       'update': manager.update, 'plan': manager.plan, 'busy': manager.busy()})
            match = re.fullmatch(r'/api/jobs/([a-f0-9]{32})(?:/(result|audio|export))?', path)
            if match:
                folder = manager.folder(match[1]); action = match[2]
                if action is None: return self.reply(manager.summary(folder))
                if action == 'result':
                    result = read_json(folder / 'result.json')
                    if result is None: return self.reply({'error': '文字还未准备好。'}, 404)
                    return self.reply(result)
                if action == 'audio': return self.audio(folder / 'playback.wav')
                if action == 'export':
                    kind = query.get('format', ['txt'])[0]
                    if kind not in {'txt','md','srt','json'}: raise ValueError('导出格式无效。')
                    result = read_json(folder / 'result.json')
                    if result is None: raise ValueError('请等待转写完成。')
                    title = Path(result['filename']).stem + '_转写.' + kind
                    return self.send_bytes(export(result, kind, query.get('language', ['zh'])[0]).encode('utf-8-sig' if kind=='txt' else 'utf-8'),
                        'application/octet-stream', headers={'Content-Disposition': "attachment; filename*=UTF-8''" + urllib.parse.quote(title)})
            return self.reply({'error': '页面不存在。'}, 404)
        except (ValueError, OSError) as error: self.reply({'error': str(error)}, 400)

    def audio(self, path):
        if not path.is_file(): return self.reply({'error': '音频还在准备中。'}, 404)
        size = path.stat().st_size
        start, end, status = 0, size-1, 200
        requested = self.headers.get('Range')
        if requested:
            match = re.fullmatch(r'bytes=(\d*)-(\d*)', requested)
            if not match: return self.send_bytes(b'', status=416, headers={'Content-Range': f'bytes */{size}'})
            if not match[1]: start = max(0, size-int(match[2] or 0))
            else: start = int(match[1]); end = min(size-1, int(match[2])) if match[2] else size-1
            if start >= size or end < start: return self.send_bytes(b'', status=416, headers={'Content-Range': f'bytes */{size}'})
            status = 206
        self.send_response(status)
        self.send_header('Content-Type', 'audio/wav'); self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(end-start+1))
        self.send_header('Cache-Control','no-store')
        if status == 206: self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        for key, value in self.cors_headers().items(): self.send_header(key, value)
        self.end_headers()
        try:
            with path.open('rb') as source:
                source.seek(start)
                left = end-start+1
                while left:
                    chunk=source.read(min(left,65536))
                    if not chunk: break
                    self.wfile.write(chunk); left-=len(chunk)
        except (ConnectionResetError, BrokenPipeError): pass

    def body(self):
        size = int(self.headers.get('Content-Length', 0))
        if size > 16*1024*1024: raise ValueError('保存内容过大。')
        return json.loads(self.rfile.read(size) or b'{}')

    def do_POST(self):
        try:
            if not self.valid_host() or not self.authenticated(): return self.reply({'error': '请从启动程序打开。'}, 403)
            origin = self.headers.get('Origin', '')
            valid = {f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}',
                     'http://127.0.0.1:28661', 'http://localhost:28661', *TAURI_ORIGINS}
            if origin not in valid or self.headers.get('X-Local-App') != '1': return self.reply({'error': '请求来源无效。'}, 403)
            parsed = urllib.parse.urlparse(self.path)
            manager = self.server.manager
            if parsed.path == '/api/upload': return self.upload(urllib.parse.parse_qs(parsed.query))
            payload = self.body()
            if parsed.path == '/api/models/settings':
                with manager.lock:
                    if manager.busy(): raise ValueError('任务进行中，请稍后修改设置。')
                    value = models.state(); value['check_on_start'] = bool(payload.get('check_on_start')); models.save(value)
                return self.reply({'ok': True})
            if parsed.path in {'/api/models/check','/api/models/install','/api/models/rollback','/api/models/bootstrap'}:
                manager.update_action(parsed.path.rsplit('/',1)[1]); return self.reply({'ok': True})
            if parsed.path == '/api/shutdown':
                if manager.maintenance: raise ValueError('正在导入或更新，请稍后退出。')
                if manager.process and manager.process.poll() is None: manager.cancel(manager.active_id)
                self.reply({'ok': True})
                threading.Thread(target=self.server.shutdown, daemon=True).start(); return
            match = re.fullmatch(r'/api/jobs/([a-f0-9]{32})/(save|cancel|retry)', parsed.path)
            if match:
                folder = manager.folder(match[1])
                with manager.lock:
                    if match[2] == 'cancel': manager.cancel(match[1])
                    elif match[2] == 'retry':
                        if (folder / 'result.json').exists(): raise ValueError('该记录已经完成。请重新导入以保留已校对的原稿。')
                        meta = read_json(folder/'job.json')
                        if payload.get('device') in {'auto','cuda_all','cpu'}:
                            meta['device']=payload['device']; atomic_json(folder/'job.json',meta)
                        manager.start(folder)
                    else:
                        result = read_json(folder/'result.json')
                        if result is None: raise ValueError('请等待转写完成。')
                        updated = apply_edits(result, payload)
                        atomic_json(folder/'result.json',updated)
                        return self.reply({'ok':True, 'revision':updated['revision']})
                return self.reply({'ok':True})
            match = re.fullmatch(r'/api/jobs/([a-f0-9]{32})/delete', parsed.path)
            if match:
                manager.delete(match[1])
                return self.reply({'ok': True})
            return self.reply({'error':'操作不存在。'},404)
        except (ValueError, KeyError, OSError) as error: self.reply({'error': str(error)},400)

    def upload(self, query):
        manager=self.server.manager
        size=int(self.headers.get('Content-Length',0))
        name=query.get('name',[''])[0].replace('\\','/').split('/')[-1]
        suffix=Path(name).suffix.lower()
        if not name or len(name)>240 or suffix not in EXTENSIONS: raise ValueError('请选择支持的音频文件。')
        if not 0<size<=MAX_UPLOAD: raise ValueError('请选择1GB以内的非空文件。')
        language=query.get('language',['ja'])[0]
        count=int(query.get('speakers',['0'])[0])
        device=query.get('device',['auto'])[0]
        quality=query.get('quality',['balanced'])[0]
        if (language not in {'','ja','zh','en','ko'} or not 0<=count<=12
                or device not in {'auto','cuda_all','cpu'} or quality not in {'accurate','balanced','fast'}):
            raise ValueError('转写设置无效。')
        glossary=query.get('glossary',[''])[0]
        if len(glossary)>1000: raise ValueError('词汇提示请控制在1000字以内。')
        with manager.lock:
            if manager.busy(): raise ValueError('已有任务正在运行，请稍后导入。')
            manager.maintenance=True
        folder=JOBS/uuid.uuid4().hex
        try:
            folder.mkdir()
            audio='source'+suffix
            self.connection.settimeout(180)
            with (folder/audio).open('wb') as target:
                left=size
                while left:
                    chunk=self.rfile.read(min(left,1024*1024))
                    if not chunk: raise ValueError('文件导入中断，请重新选择。')
                    target.write(chunk); left-=len(chunk)
            atomic_json(folder/'job.json', {'filename':name,'audio':audio,'created':time.time(),
                'speakers':count,'language':language,'device':device,'quality':quality,'glossary':glossary})
            with manager.lock:
                manager.maintenance=False
                manager.start(folder)
            self.reply({'id':folder.name})
        finally:
            with manager.lock: manager.maintenance=False

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--port',type=int,default=0)
    args=parser.parse_args()
    existing=read_json(INSTANCE)
    if existing:
        try:
            request=urllib.request.Request(existing['url']+'/api/config', headers={'Cookie':'scribe='+existing['key']})
            with urllib.request.urlopen(request,timeout=2) as response:
                if response.status==200:
                    if not args.no_browser: webbrowser.open(existing['url']+'/?key='+existing['key'])
                    print('Already running',flush=True); return
        except Exception: pass
    if os.environ.get('HEARNOTES_TAURI') == '1' and args.port == 0:
        args.port = 28661
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    server.daemon_threads=True
    server.key=secrets.token_urlsafe(32)
    server.manager=Manager()
    url=f'http://127.0.0.1:{server.server_port}'
    atomic_json(INSTANCE,{'url':url,'key':server.key,'pid':os.getpid()})
    print('Listening '+url,flush=True)
    if not args.no_browser: webbrowser.open(url+'/?key='+server.key)
    if models.state().get('check_on_start'): server.manager.update_action('check')
    try: server.serve_forever()
    finally:
        server.server_close()
        if read_json(INSTANCE,{}).get('pid')==os.getpid(): INSTANCE.unlink(missing_ok=True)

if __name__=='__main__': main()
