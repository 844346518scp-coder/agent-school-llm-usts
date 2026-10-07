"""Build the offline Windows x64 desktop installer using project Python + Inno Setup.

Run after npm run build with .runtime/python-3.13.13/python.exe.
Only whitelisted runtime, locked packages, app source and web assets are shipped.
"""
import argparse
import hashlib
from importlib import metadata
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent


def build():
    parser = argparse.ArgumentParser()
    parser.add_argument('--compiler', type=Path, default=ROOT/'.runtime/inno/ISCC.exe')
    args = parser.parse_args()
    if sys.platform != 'win32' or sys.version_info[:2] != (3, 13):
        raise RuntimeError('Use the project Windows x64 Python 3.13 runtime.')
    if not args.compiler.is_file() or not (ROOT/'frontend/dist/index.html').is_file():
        raise RuntimeError('Prepare Inno Setup and build frontend first.')
    output = ROOT/'dist'/('desktop-'+time.strftime('%Y%m%d-%H%M%S'))
    payload = output/'payload'
    payload.mkdir(parents=True, exist_ok=False)
    def copy(source, relative):
        target = payload/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    runtime = Path(sys.executable).parent
    for source in runtime.iterdir():
        if source.suffix.lower() in ('.dll', '.pyd') or source.name in ('python.exe', 'pythonw.exe', 'python313.zip', 'LICENSE.txt'):
            copy(source, Path('runtime')/source.name)
    packages = {}
    for line in (ROOT/'backend/requirements.lock.txt').read_text().splitlines():
        if not line.strip() or line.startswith('#'):
            continue
        name, version = line.split('==')
        dist = metadata.distribution(name)
        if dist.version != version or dist.files is None:
            raise RuntimeError('Locked dependency mismatch: '+name)
        packages[name] = version
        site = Path(dist.locate_file('')).resolve()
        for entry in dist.files:
            source = Path(dist.locate_file(entry)).resolve()
            if not source.is_relative_to(site) or '__pycache__' in source.parts or source.suffix == '.pyc' or source.name == 'direct_url.json':
                continue
            copy(source, Path('runtime/packages')/source.relative_to(site))
    (payload/'runtime/python313._pth').write_text('python313.zip\n.\npackages\n..\n',encoding='ascii')
    for directory in ('backend/app','migrations'):
        for source in (ROOT/directory).rglob('*.py'):
            copy(source,source.relative_to(ROOT))
    shutil.copytree(ROOT/'frontend/dist',payload/'frontend/dist')
    copy(ROOT/'desktop.py','desktop.py')
    (payload/'desktop-installed.json').write_text(json.dumps({'version':'0.3.5','packages':packages},indent=2),encoding='utf-8')
    (payload/'使用说明.txt').write_text(
        '数伴桌面版 0.3.5\n\n双击桌面“数伴”启动。需要Windows x64及Edge或Chrome。\n'
        '已内置Python和网页，首次使用无需下载安装依赖。首次建立教师账号。\n'
        '开始菜单“模型配置”可填写自己的API Key，默认使用DeepSeek Flash。\n'
        '修改模型配置后需关闭数伴后台服务再重启（重启电脑也可）。\n'
        '本安装包不含API Key和原有数据库；未配置时为演示模式。\n'
        '数据、日志、模型配置位于 %LOCALAPPDATA%\\Shuban\\data。卸载保留此目录。\n'
        '源码目录中的旧数据不会自动导入；请另行备份迁移。关闭窗口后后台服务继续运行。\n'
        '此安装包未作商业代码签名。真实模型内容需核对，不能代替教师判断。\n',encoding='utf-8')
    notices=[]
    lock=json.loads((ROOT/'frontend/package-lock.json').read_text())
    for relative in lock['packages']:
        package=ROOT/'frontend'/relative
        if not relative or not (package/'package.json').is_file():
            continue
        info=json.loads((package/'package.json').read_text(encoding='utf-8'))
        notices.append({'name':info.get('name'),'version':info.get('version'),'license':info.get('license'),
                        'notices':{p.name:p.read_text(encoding='utf-8',errors='replace') for p in package.iterdir() if p.is_file() and p.name.upper().startswith(('LICENSE','LICENCE','COPYING','NOTICE'))}})
    (payload/'THIRD-PARTY.json').write_text(json.dumps(notices,ensure_ascii=False,indent=2),encoding='utf-8')
    for path in payload.rglob('*'):
        if path.is_file() and (path.suffix in ('.db','.log') or path.name == '.env' or re.search(rb'sk-[A-Za-z0-9]{24,}',path.read_bytes())):
            raise RuntimeError('Unexpected private content in payload: '+str(path.relative_to(payload)))
    subprocess.run([str(payload/'runtime/python.exe'),'-B','-c','import fastapi,uvicorn,sqlalchemy,ssl;print("Bundled imports OK")'],cwd=payload,check=True)
    manifest={p.relative_to(payload).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in payload.rglob('*') if p.is_file()}
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    subprocess.run([str(args.compiler),'/Qp','/DPayload='+str(payload),'/DOutput='+str(output),str(ROOT/'desktop-installer.iss')],check=True)
    exe=output/'Shuban-Setup-0.3.5-x64.exe'
    exe.with_suffix('.exe.sha256').write_text(hashlib.sha256(exe.read_bytes()).hexdigest()+'  '+exe.name+'\n',encoding='ascii')
    print(exe,flush=True)


if __name__ == '__main__':
    build()
