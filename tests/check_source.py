"""Cold source-folder verification: no bundled runtime, venv or node_modules.

Requires internet for the first setup. All data/processes live under .tmp.
Run with a development Python: python tests/check_source.py
"""
import http.cookiejar
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


class MockModel(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get('Content-Length', '0')))
        body = json.dumps({'choices': [{'message': {'content': '联调模拟模型：可导必连续，请核对定义。'}}]}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def main():
    task_tmp = ROOT / '.tmp'
    task_tmp.mkdir(exist_ok=True)
    # Retain the isolated source folder for browser inspection and reproducibility.
    source = Path(tempfile.mkdtemp(prefix='源码 冷启动-', dir=task_tmp))
    paths = set(subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=ROOT).decode().split('\0'))
    for name in paths:
        if not name or name == 'PCL.exe' or name.startswith('原始素材/'):
            continue
        original = ROOT / name
        if original.is_file():
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, target)
    assert not any((source / name).exists() for name in ('.runtime', '.venv', 'frontend/node_modules', 'frontend/dist', '.env'))
    system = Path(os.environ['SystemRoot']) / 'System32'
    env = os.environ.copy()
    env['PATH'] = str(system) + os.pathsep + str(system / 'WindowsPowerShell/v1.0')
    env['PYTHONHOME'] = env['PYTHONPATH'] = str(source / 'not-installed')
    env['TEMP'] = env['TMP'] = str(task_tmp)
    env['AGENT_MODE'] = 'demo'
    env['SHUBAN_SEED_DEMO'] = 'true'
    for key in ('DATABASE_URL', 'MODEL_BASE_URL', 'MODEL_API_KEY', 'MODEL_NAME', 'COOKIE_SECURE'):
        env.pop(key, None)
    command = [str(system / 'WindowsPowerShell/v1.0/powershell.exe'), '-NoProfile', '-ExecutionPolicy', 'Bypass',
               '-File', str(source / 'start.ps1'), '-NoBrowser']
    pid = None
    port = None
    log = task_tmp / 'source-bootstrap-check.log'

    def start(cold=False):
        nonlocal pid, port
        print('Starting source folder: ' + ('cold download/install/build' if cold else 'cached restart'), flush=True)
        result = subprocess.run(command, cwd=source, env=env, capture_output=True, timeout=1200,
                                stdin=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
        output = result.stdout.decode(errors='replace') + result.stderr.decode(errors='replace')
        with log.open('a', encoding='utf-8') as stream:
            stream.write(output + '\n')
        match = re.search(r'Backend process: (\d+)', output)
        if match:
            pid = int(match[1])
        assert result.returncode == 0, f'See {log}\n' + output[-2500:]
        port = int(re.search(r'Ready: http://127.0.0.1:(\d+)', output)[1])
        if not cold:
            assert 'Downloading ' not in output and 'Installing ' not in output and 'Building the web app' not in output
        return output

    def stop():
        nonlocal pid
        if pid:
            subprocess.run([str(system / 'taskkill.exe'), '/PID', str(pid), '/F'], capture_output=True, check=True)
            pid = None
            time.sleep(.5)

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                         urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(path, data=None, method=None):
        req = urllib.request.Request(f'http://127.0.0.1:{port}' + path, method=method,
            data=json.dumps(data).encode() if data is not None else None,
            headers={'X-Requested-With': 'shuban-web', 'Content-Type': 'application/json'})
        with opener.open(req, timeout=15) as response:
            content = response.read()
            return json.loads(content) if response.headers.get_content_type() == 'application/json' else content

    def login(role):
        return request('/api/auth/login', {'role': role, 'username': role, 'password': role.title() + '123!'})

    model = ThreadingHTTPServer(('127.0.0.1', 0), MockModel)
    thread = threading.Thread(target=model.serve_forever, daemon=True)
    thread.start()
    try:
        start(cold=True)
        print('Cold setup passed. Checking B/C workflow and persistence...', flush=True)
        assert 'Backend process:' not in start()
        html = request('/').decode()
        for asset in re.findall(r'(?:src|href)="(/assets/[^\"]+)"', html):
            assert len(request(asset)) > 0
        login('teacher')
        question = request('/api/questions', {'title': '冷启动题目', 'topic': '导数与微分', 'content': '解释导数', 'reference_answer': '教师专有答案'})
        draft = request('/api/assignments/drafts', {'title': '源码启动闭环', 'question_ids': [question['id']]})
        from datetime import date, timedelta
        aid = draft['id']
        request(f'/api/assignments/{aid}', {'class_id': 'demo-class', 'topic': '导数与微分', 'due_date': (date.today() + timedelta(days=1)).isoformat()}, 'PATCH')
        request(f'/api/assignments/{aid}/publish', {})
        login('student')
        assert '教师专有答案' not in json.dumps(request('/api/assignments'), ensure_ascii=False)
        request(f'/api/assignments/{aid}/submission', {'answer': '瞬时变化率'}, 'PUT')
        reply = request('/api/conversations', {'question': '用定义求导数'})
        assert reply['mode'] == 'demo' and reply['references']
        login('teacher')
        request(f'/api/assignments/{aid}/submissions/student/review', {'version': 1, 'comment': '补充极限定义', 'status': 'needs_improvement'}, 'PUT')
        stop()
        # Cached setup is tested with unreachable proxies, so it must not reinstall.
        env['HTTP_PROXY'] = env['HTTPS_PROXY'] = 'http://127.0.0.1:9'
        env['NO_PROXY'] = '127.0.0.1,localhost'
        env['AGENT_MODE'] = 'live'
        env['MODEL_BASE_URL'] = f'http://127.0.0.1:{model.server_port}/v1'
        env['MODEL_API_KEY'] = 'local-test-only'
        env['MODEL_NAME'] = 'mock-model'
        start()
        assert request('/api/health')['agent_mode'] == 'live'
        login('student')
        assert next(a for a in request('/api/assignments') if a['id'] == aid)['submission']['review']['status'] == 'needs_improvement'
        assert request('/api/conversations', {'question': '可导与连续'})['mode'] == 'live'
        print(f'PASS: source ZIP equivalent, automatic setup, assets, B/C workflow, persistence, offline cached startup and mock live mode.\nSource copy: {source}', flush=True)
    finally:
        stop()
        model.shutdown()
        model.server_close()


if __name__ == '__main__':
    main()
