"""Windows portable launcher; only the bundled standard library is needed here."""
import argparse
import hashlib
import json
import msvcrt
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[3]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--serve', action='store_true')
    parser.add_argument('--source', action='store_true')
    parser.add_argument('--port', type=int, default=0)
    args = parser.parse_args()
    if args.port != 0 and not 1024 <= args.port <= 65535:
        raise ValueError('Port must be between 1024 and 65535.')
    os.chdir(ROOT)
    # A portable demo must not inherit another application's database or secrets.
    if not args.source:
        os.environ['DATABASE_URL'] = 'sqlite:///' + (ROOT / 'backend/demo.db').as_posix()
        os.environ['COOKIE_SECURE'] = 'false'
    os.environ['SHUBAN_INSTANCE_ID'] = hashlib.sha256(str(ROOT).casefold().encode()).hexdigest()[:24]
    instance = os.environ['SHUBAN_INSTANCE_ID']
    if args.serve:
        sys.path.insert(0, str(ROOT))
        import uvicorn
        uvicorn.run('backend.app.main:app', host='127.0.0.1', port=args.port, access_log=False)
        return
    if not (ROOT / 'frontend/dist/index.html').is_file():
        raise RuntimeError('Frontend build missing. Extract the complete portable ZIP first.')
    auto_port = args.port == 0
    port_file = ROOT / 'backend/launcher-port.txt'
    url = ''
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def ready():
        try:
            with opener.open(url + 'api/health', timeout=1) as response:
                health = json.load(response)
            with opener.open(url, timeout=1) as response:
                page = response.read()
            return (health.get('status') == 'ok' and health.get('instance_id') == instance
                    and (not args.source or health.get('agent_version') == '0.2.0')
                    and b'<html' in page and b'/assets/' in page)
        except (OSError, ValueError):
            return False

    # Windows byte-range lock releases automatically even if the launcher crashes.
    with (ROOT / 'backend/launcher.lock').open('a+b') as lock:
        lock.seek(0)
        if not lock.read(1):
            lock.write(b'0')
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            print('SHUBAN is already starting. Please wait for the first launcher.')
            return
        try:
            if auto_port:
                try:
                    args.port = int(port_file.read_text())
                    if not 1024 <= args.port <= 65535:
                        raise ValueError('Invalid saved port')
                except (OSError, ValueError):
                    args.port = 18080
            url = f'http://127.0.0.1:{args.port}/'
            if not ready():
                with socket.socket() as sock:
                    try:
                        sock.bind(('127.0.0.1', args.port))
                    except OSError:
                        if not auto_port:
                            raise RuntimeError(f'Port {args.port} is occupied or reserved by Windows. '
                                               'No process was stopped. Run without -Port to auto-select.')
                        sock.bind(('127.0.0.1', 0))
                        args.port = sock.getsockname()[1]
                        url = f'http://127.0.0.1:{args.port}/'
                with (ROOT / 'backend/server.out.log').open('ab') as out, (ROOT / 'backend/server.err.log').open('ab') as err:
                    child_args = [sys.executable, '-B', str(Path(__file__).resolve()), '--serve', '--port', str(args.port)]
                    if args.source:
                        child_args.append('--source')
                    child = subprocess.Popen(child_args, cwd=ROOT,
                                             stdout=out, stderr=err, stdin=subprocess.DEVNULL,
                                             creationflags=subprocess.CREATE_NO_WINDOW)
                deadline = time.monotonic() + 45
                while not ready():
                    if child.poll() is not None:
                        raise RuntimeError('Backend exited. See backend/server.err.log.')
                    if time.monotonic() > deadline:
                        child.terminate()
                        child.wait(timeout=10)
                        raise RuntimeError('Startup timed out. See backend/server.err.log.')
                    time.sleep(.25)
                print(f'Backend process: {child.pid}')
            port_file.write_text(str(args.port), encoding='ascii')
            print(f'Ready: {url}')
            print('Services stay running in the background. Data: backend/demo.db')
            if not args.no_browser:
                webbrowser.open(url)
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)
