import importlib.util
import os
from pathlib import Path
import shutil


def test_installed_code_and_data_paths_are_separate(tmp_path, monkeypatch):
    root = tmp_path/'application'
    root.mkdir()
    source = Path(__file__).resolve().parents[1]/'desktop.py'
    shutil.copy2(source, root/'desktop.py')
    (root/'desktop-installed.json').write_text('{}')
    data = tmp_path/'user-data'
    monkeypatch.setenv('SHUBAN_DATA_DIR',str(data))
    for name in ('DATABASE_URL','SHUBAN_INSTANCE_ID','COOKIE_SECURE','SHUBAN_SEED_DEMO','AGENT_MODE','MODEL_BASE_URL','MODEL_NAME','MODEL_VISION_NAME','MODEL_API_KEY','MODEL_THINKING','MODEL_MAX_TOKENS'):
        monkeypatch.delenv(name,raising=False)
    spec = importlib.util.spec_from_file_location('isolated_desktop', root/'desktop.py')
    launcher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(launcher)
    launcher.prepare_installed_data()
    assert launcher.PORTABLE == root/'backend/app/platform/portable.py'
    assert launcher.PORT_FILE == data/'launcher-port.txt'
    assert os.environ['DATABASE_URL'] == 'sqlite:///' + (data/'demo.db').as_posix()
    assert os.environ['SHUBAN_SEED_DEMO'] == 'false'
    (data/'.env').write_text('MODEL_NAME=user-choice\n')
    launcher.prepare_installed_data()
    assert (data/'.env').read_text() == 'MODEL_NAME=user-choice\n'


def test_source_desktop_keeps_existing_data_location():
    import desktop
    assert not desktop.INSTALLED
    assert desktop.BACKEND == desktop.ROOT/'backend'
    assert desktop.PORTABLE.is_file()
