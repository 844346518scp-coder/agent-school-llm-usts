"""Run against a built ZIP: python tests/check_portable.py path/to/bundle.zip.

Extracts to an isolated Chinese/space path, removes Python/Node from child PATH,
and tests the actual PowerShell launcher and persistence. Does not use the real demo DB.
"""
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile


def check(archive):
    task_tmp = Path(__file__).resolve().parents[1] / '.tmp'
    task_tmp.mkdir(exist_ok=True)
    system = Path(os.environ['SystemRoot']) / 'System32'
    env = os.environ.copy()
    env['PATH'] = str(system) + os.pathsep + str(system / 'WindowsPowerShell/v1.0')
    env['PYTHONHOME'] = env['PYTHONPATH'] = str(task_tmp / 'missing-python')
    env['DATABASE_URL'] = 'sqlite:///DO-NOT-CREATE.db'
    env['TEMP'] = env['TMP'] = str(task_tmp)
    with tempfile.TemporaryDirectory(prefix='便携 测试-', dir=task_tmp) as temporary:
        with zipfile.ZipFile(archive) as z:
            z.extractall(temporary)
        root = next(Path(temporary).iterdir())
        manifest = json.loads((root / 'portable-manifest.json').read_text(encoding='utf-8'))
        for relative, expected in manifest['files'].items():
            assert hashlib.sha256((root / relative).read_bytes()).hexdigest() == expected, relative
        assert not list(root.rglob('*.db')) and not list(root.rglob('.env'))
        assert not (root / '.venv').exists() and not (root / 'frontend/node_modules').exists()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        command = [str(system / 'WindowsPowerShell/v1.0/powershell.exe'), '-NoProfile',
                   '-ExecutionPolicy', 'Bypass', '-File', str(root / 'start.ps1'),
                   '-NoBrowser', '-Port', str(port)]
        pid = None

        def launch(arguments=None):
            nonlocal pid
            result = subprocess.run(arguments or command, env=env, cwd=temporary, capture_output=True,
                                    stdin=subprocess.DEVNULL, timeout=65)
            output = result.stdout.decode(errors='replace') + result.stderr.decode(errors='replace')
            match = re.search(r'Backend process: (\d+)', output)
            if match:
                pid = int(match[1])
            assert result.returncode == 0, output
            return output

        def stop():
            nonlocal pid
            if pid:
                subprocess.run([str(system / 'taskkill.exe'), '/PID', str(pid), '/F'],
                               capture_output=True, check=True)
                pid = None
                time.sleep(.5)

        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                             urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

        def request(path, data=None):
            req = urllib.request.Request(f'http://127.0.0.1:{port}' + path,
                                         data=json.dumps(data).encode() if data is not None else None,
                                         headers={'X-Requested-With': 'shuban-web', 'Content-Type': 'application/json'})
            with opener.open(req, timeout=10) as response:
                return response.read()

        try:
            launch()
            assert pid is not None
            assert 'Backend process:' not in launch(), 'Repeated launch started another server'
            html = request('/').decode()
            for asset in re.findall(r'(?:src|href)="(/assets/[^\"]+)"', html):
                assert len(request(asset)) > 0, asset
            request('/api/auth/login', {'username': 'teacher', 'password': 'Teacher123!', 'role': 'teacher'})
            draft = json.loads(request('/api/assignments/drafts', {'title': 'portable persistence'}))
            stop()
            launch()
            request('/api/auth/login', {'username': 'teacher', 'password': 'Teacher123!', 'role': 'teacher'})
            assert draft['id'] in [a['id'] for a in json.loads(request('/api/assignments'))]
            assert not list(Path(temporary).rglob('DO-NOT-CREATE.db'))
            # Busy foreign port must fail without terminating the listener.
            with socket.socket() as occupied:
                occupied.bind(('127.0.0.1', 0))
                occupied.listen()
                result = subprocess.run(command[:-1] + [str(occupied.getsockname()[1])],
                                        env=env, cwd=temporary, capture_output=True, timeout=15)
                assert result.returncode != 0
                assert b'occupied' in result.stderr
                stop()
                (root / 'backend/launcher-port.txt').write_text(str(occupied.getsockname()[1]))
                automatic = launch(command[:-2])
                port = int(re.search(r'Ready: http://127.0.0.1:(\d+)', automatic)[1])
                assert port != occupied.getsockname()[1]
                assert 'Backend process:' not in launch(command[:-2])
                launcher = str(root / '一键启动.cmd').replace("'", "''")
                cmd_output = launch([command[0], '-NoProfile', '-Command', f"& '{launcher}' -NoBrowser"])
                assert 'Backend process:' not in cmd_output
            print('PASS: manifest, clean package, isolated runtime, Chinese/space path, static assets,')
            print('      login, draft persistence, repeat launch, port conflict, auto fallback and CMD.')
        finally:
            stop()


if __name__ == '__main__':
    check(Path(sys.argv[1]).resolve())
