"""Build a Windows x64 offline test ZIP from the validated development environment.

Run: .venv/Scripts/python.exe build-portable.py
No venv, local database, .env, source attachments or credentials are copied.
"""
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import sysconfig
import time
import zipfile

ROOT = Path(__file__).resolve().parent


def copy_file(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def build():
    if sys.platform != 'win32' or platform.machine().lower() not in ('amd64', 'x86_64'):
        raise RuntimeError('Build on Windows x64 using the validated project Python environment.')
    if sys.version_info[:2] != (3, 11):
        raise RuntimeError('This builder currently validates Python 3.11 only.')
    base = Path(sys.base_prefix)
    for name in ('python.exe', 'python311.dll', 'vcruntime140.dll', 'LICENSE.txt', 'Lib', 'DLLs'):
        if not (base / name).exists():
            raise RuntimeError(f'Incomplete redistributable Python runtime: {name}')
    packages = []
    for line in (ROOT / 'backend/requirements.lock.txt').read_text().splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        name, version = line.split('==')
        dist = metadata.distribution(name)
        if dist.version != version:
            raise RuntimeError(f'{name} differs from requirements.lock.txt; install locked dependencies first.')
        packages.append(dist)
    npm = shutil.which('npm.cmd')
    if not npm:
        raise RuntimeError('Build computer needs Node.js/npm. Test computers do not.')
    subprocess.run([npm, 'run', 'build'], cwd=ROOT / 'frontend', check=True)
    # A new output each time: never overwrite a test installation or its database.
    output = ROOT / 'dist' / ('shuban-windows-x64-' + time.strftime('%Y%m%d-%H%M%S'))
    output.mkdir(parents=True, exist_ok=False)
    runtime = output / 'runtime'
    runtime.mkdir()
    for source in base.iterdir():
        if source.suffix.lower() == '.dll' or source.name in ('python.exe', 'pythonw.exe', 'LICENSE.txt', 'BUILD'):
            copy_file(source, runtime / source.name)
    ignore = shutil.ignore_patterns('site-packages', '__pycache__', '*.pyc')
    shutil.copytree(base / 'Lib', runtime / 'Lib', ignore=ignore)
    shutil.copytree(base / 'DLLs', runtime / 'DLLs', ignore=ignore)
    # Isolate from system Python, PYTHONPATH, registry and user site-packages.
    (runtime / 'python311._pth').write_text('Lib\nDLLs\nLib/site-packages\n..\n', encoding='ascii')
    site = Path(sysconfig.get_path('purelib')).resolve()
    for dist in packages:
        if dist.files is None:
            raise RuntimeError(f'Missing wheel RECORD: {dist.metadata["Name"]}')
        for entry in dist.files:
            source = Path(dist.locate_file(entry)).resolve()
            if not source.is_relative_to(site):
                continue  # Do not ship venv Scripts launchers with absolute build paths.
            relative = source.relative_to(site)
            if '__pycache__' in relative.parts or source.suffix == '.pyc' or source.name == 'direct_url.json':
                continue
            copy_file(source, runtime / 'Lib/site-packages' / relative)
    # Only reviewed source file types from the application modules.
    for directory in ('backend/app', 'migrations'):
        for source in (ROOT / directory).rglob('*.py'):
            if '__pycache__' not in source.parts:
                copy_file(source, output / source.relative_to(ROOT))
    shutil.copytree(ROOT / 'frontend/dist', output / 'frontend/dist')
    for name in ('start.ps1', '一键启动.cmd', 'backend/requirements.lock.txt'):
        copy_file(ROOT / name, output / name)
    copy_file(ROOT / 'docs/portable-windows.md', output / '使用说明.md')
    # Preserve notices for frontend libraries compiled into the JavaScript assets.
    notices = []
    lock = json.loads((ROOT / 'frontend/package-lock.json').read_text())
    for relative in lock['packages']:
        if not relative:
            continue
        package = ROOT / 'frontend' / relative
        if not (package / 'package.json').is_file():
            continue
        info = json.loads((package / 'package.json').read_text(encoding='utf-8'))
        texts = {p.name: p.read_text(encoding='utf-8', errors='replace') for p in package.iterdir()
                 if p.is_file() and p.name.upper().startswith(('LICENSE', 'LICENCE', 'COPYING', 'NOTICE'))}
        notices.append({'name': info.get('name'), 'version': info.get('version'),
                        'license': info.get('license'), 'notices': texts})
    (output / 'THIRD-PARTY.json').write_text(json.dumps(notices, ensure_ascii=False, indent=2), encoding='utf-8')
    manifest = {'platform': 'windows-x64', 'python': sys.version, 'version': '0.2.0',
                'scope': 'B/C integrated local MVP; real model validation pending',
                'packages': {d.metadata['Name']: d.version for d in packages},
                'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                'source_dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT)),
                'files': {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in sorted(output.rglob('*')) if p.is_file()}}
    (output / 'portable-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    # Import with the shipped runtime, not the build machine's virtual environment.
    env = os.environ.copy()
    env.pop('PYTHONHOME', None)
    env.pop('PYTHONPATH', None)
    subprocess.run([str(runtime / 'python.exe'), '-B', '-c',
                    'import fastapi, uvicorn, sqlalchemy, pydantic, sqlite3, ssl; print("Bundled imports OK")'],
                   cwd=output, env=env, check=True)
    archive = output.with_suffix('.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in sorted(output.rglob('*')):
            if path.is_file():
                bundle.write(path, Path(output.name) / path.relative_to(output))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(f'{digest}  {archive.name}\n', encoding='ascii')
    print(f'Portable ZIP: {archive}\nSHA256: {digest}', flush=True)


if __name__ == '__main__':
    build()
