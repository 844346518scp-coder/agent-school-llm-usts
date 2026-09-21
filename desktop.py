"""SHUBAN desktop-window launcher (optional addition).

Opens the same local SHUBAN web app in a Chromium app-mode window: no address
bar, no tab strip, just the application. It reuses the project-local runtime and
the same backend command, port file, health checks and single-instance lock as
backend/app/platform/portable.py, so the normal web launcher (一键启动.cmd) and
this entry can share one running service. The default web entry point is not
changed by this file.

Design notes (see docs/development-log.md, 2026-09-21):

* pywebview was tried first and is NOT used. It installs into the project-local
  embeddable runtime only as 3.4 (newer releases need the sdist-only
  ``proxy_tools``, and that runtime has no setuptools), and importing it crashes
  the interpreter with a .NET CLR exit (0xE0434352) via pythonnet, which a Python
  ``try/except`` cannot catch. The app-mode window gives the same visible result
  with no extra dependency.
* The window process is detached on purpose: the backend keeps running in the
  background exactly like the web launcher, so this entry never changes the
  lifetime rules users already know.
"""
from __future__ import annotations

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

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / 'backend'
PORT_FILE = BACKEND / 'launcher-port.txt'
LOCK_FILE = BACKEND / 'launcher.lock'
PORTABLE = BACKEND / 'app/platform/portable.py'
DEFAULT_PORT = 18080
READY_TIMEOUT = 45
WINDOW_SIZE = (1280, 860)
WINDOW_PROFILE = ROOT / '.runtime/desktop-profile'
EXPECTED = ('0.2.0', '0.3.0', 3)  # agent_version, teaching_version, schema_version

_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def instance_id():
    """Must match backend/app/platform/portable.py so both entries share a service."""
    return hashlib.sha256(str(ROOT).casefold().encode()).hexdigest()[:24]


def is_ready(url):
    try:
        with _OPENER.open(url + 'api/health', timeout=1) as response:
            health = json.load(response)
        if health.get('status') != 'ok' or health.get('instance_id') != instance_id():
            return False
        if (health.get('agent_version'), health.get('teaching_version'),
                health.get('schema_version')) != EXPECTED:
            return False
        with _OPENER.open(url, timeout=1) as response:
            page = response.read()
        return b'<html' in page and b'/assets/' in page
    except (OSError, ValueError):
        return False


def find_browser():
    bases = (os.environ.get('ProgramFiles(x86)'), os.environ.get('ProgramFiles'),
             os.environ.get('LOCALAPPDATA'))
    relatives = ('Microsoft/Edge/Application/msedge.exe',
                 'Google/Chrome/Application/chrome.exe')
    for base in bases:
        if not base:
            continue
        for relative in relatives:
            candidate = Path(base) / relative
            if candidate.is_file():
                return candidate
    return None


def saved_port(preferred):
    if preferred:
        return preferred
    try:
        value = int(PORT_FILE.read_text().strip())
        if 1024 <= value <= 65535:
            return value
    except (OSError, ValueError):
        pass
    return DEFAULT_PORT


def available_port(port):
    with socket.socket() as sock:
        try:
            sock.bind(('127.0.0.1', port))
            return port
        except OSError:
            sock.bind(('127.0.0.1', 0))
            return sock.getsockname()[1]


def ensure_backend(port):
    """Reuse a healthy service from this folder, or start one. Returns (url, child)."""
    url = f'http://127.0.0.1:{port}/'
    if is_ready(url):
        return url, None
    port = available_port(port)
    url = f'http://127.0.0.1:{port}/'
    with (BACKEND / 'server.out.log').open('ab') as out, (BACKEND / 'server.err.log').open('ab') as err:
        child = subprocess.Popen(
            [sys.executable, '-B', str(PORTABLE), '--serve', '--source', '--port', str(port)],
            cwd=ROOT, stdout=out, stderr=err, stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    deadline = time.monotonic() + READY_TIMEOUT
    while not is_ready(url):
        if child.poll() is not None:
            raise RuntimeError('Backend exited during startup. See backend/server.err.log.')
        if time.monotonic() > deadline:
            child.terminate()
            raise RuntimeError('Backend did not become ready in time. See backend/server.err.log.')
        time.sleep(0.25)
    PORT_FILE.write_text(str(port), encoding='ascii')
    return url, child


def open_window(browser, url):
    width, height = WINDOW_SIZE
    return subprocess.Popen([
        str(browser), f'--app={url}', f'--user-data-dir={WINDOW_PROFILE}',
        '--no-first-run', '--no-default-browser-check', '--disable-background-mode',
        '--disable-features=msEdgeStartupBoost,msEdgeBackgroundMode',
        f'--window-size={width},{height}',
    ])


def main():
    parser = argparse.ArgumentParser(
        description='Open SHUBAN in a desktop app-mode window (optional entry).')
    parser.add_argument('--port', type=int, default=0,
                        help='fixed port; 0 reuses backend/launcher-port.txt then 18080')
    parser.add_argument('--check', action='store_true',
                        help='prepare/reuse the backend and exit without opening a window')
    args = parser.parse_args()
    if args.port and not 1024 <= args.port <= 65535:
        print('ERROR: --port must be between 1024 and 65535.', file=sys.stderr)
        return 2
    if not (ROOT / 'frontend/dist/index.html').is_file():
        print('ERROR: frontend build missing. Run the normal launcher once to initialise this folder.',
              file=sys.stderr)
        return 1
    browser = find_browser()
    if browser is None:
        print('ERROR: neither Microsoft Edge nor Google Chrome was found. Use 一键启动.cmd instead.',
              file=sys.stderr)
        return 1
    with LOCK_FILE.open('a+b') as lock:
        lock.seek(0)
        if not lock.read(1):
            lock.write(b'0')
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            print('SHUBAN is already starting. Please wait for the first launcher.')
            return 0
        try:
            url, child = ensure_backend(saved_port(args.port))
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
    if child is None:
        print('Reusing the SHUBAN service already running in this folder.')
    else:
        print(f'Backend process: {child.pid}')
    print(f'Ready: {url}')
    if args.check:
        print('Check only: the desktop window was not opened.')
        return 0
    open_window(browser, url)
    print(f'Desktop window: {browser.name} (profile: .runtime/desktop-profile)')
    print('Close the window to finish. The backend keeps running, exactly like the normal launcher.')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:  # keep the console message short and actionable
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(1)
