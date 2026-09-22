"""B 模块第二阶段测试：契约修复、长期记忆、推荐、评价、总结、资源检索。

运行：python -m pytest -q
测试使用独立的临时 SQLite 文件，不会碰到开发用的数据库。
"""
from __future__ import annotations

import atexit
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_DB_DIR = tempfile.TemporaryDirectory(prefix='shuban-agent-phase2-')
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
os.environ['DATABASE_URL'] = 'sqlite:///' + (Path(_DB_DIR.name) / 'phase2.db').as_posix()
os.environ['AGENT_MODE'] = 'demo'
os.environ['SHUBAN_SEED_DEMO'] = 'true'

from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from backend.app.ai import insight, knowledge, memory, service  # noqa: E402
from backend.app.main import app  # noqa: E402
from backend.app.platform.database import engine as db_engine  # noqa: E402


def _cleanup() -> None:
    """先释放连接再删临时库，避免 Windows 上残留文件占用告警。"""
    try:
        db_engine.dispose()
    except Exception:  # noqa: BLE001 - 清理失败不应影响测试结论
        pass
    _DB_DIR.cleanup()


atexit.register(_cleanup)

HEADERS = {'X-Requested-With': 'shuban-web'}
PNG_1PX = ('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8AAAAMBAQDJ/pLv'
           'AAAAAElFTkSuQmCC')
NOT_AN_IMAGE = 'bm90IGFuIGltYWdlIG5vdCBhbiBpbWFnZSBub3QgYW4gaW1hZ2Ugbm90IGFu'


@pytest.fixture(scope='module')
def client():
    with TestClient(app) as instance:
        login = instance.post('/api/auth/login',
                              json={'username': 'student', 'password': 'Student123!', 'role': 'student'},
                              headers=HEADERS)
        assert login.status_code == 200
        yield instance


def _live_settings(monkeypatch, chat_result):
    monkeypatch.setattr(service, 'load_settings',
                        lambda: SimpleNamespace(resolved_mode='live', vision_model='vision-model'))
    monkeypatch.setattr(service, 'chat', lambda *args, **kwargs: chat_result)


# ---------------------------------------------------------------- 契约修复

def test_recognize_rejects_malformed_base64():
    with pytest.raises(ValidationError):
        service.RecognizeInput(image_base64='@' * 16)


def test_recognize_rejects_non_image_mime():
    with pytest.raises(ValidationError):
        service.RecognizeInput(image_base64=PNG_1PX, media_type='text/plain')


def test_recognize_rejects_payload_without_image_header():
    with pytest.raises(ValidationError):
        service.RecognizeInput(image_base64=NOT_AN_IMAGE, media_type='image/png')


def test_recognize_accepts_real_png():
    parsed = service.RecognizeInput(image_base64=PNG_1PX)
    assert parsed.media_type == 'image/png'
    assert detect_type(parsed.image_base64) == 'image/png'


def detect_type(payload: str) -> str | None:
    return service.detect_image_type(service.decode_image(payload))


def test_recognize_empty_model_text_raises_controlled_error(monkeypatch):
    _live_settings(monkeypatch, '{}')
    with pytest.raises(HTTPException) as excinfo:
        service.recognize_question(service.RecognizeInput(image_base64=PNG_1PX), None)
    assert excinfo.value.status_code == 502


def test_recognize_numeric_warnings_do_not_crash(monkeypatch):
    _live_settings(monkeypatch, '{"text": "识别出的题目", "warnings": 123}')
    result = service.recognize_question(service.RecognizeInput(image_base64=PNG_1PX), None)
    assert isinstance(result['warnings'], list)
    assert result['text'] == '识别出的题目'
    assert result['requires_confirmation'] is True


def test_demo_mode_never_calls_model_for_recognize(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('demo 模式不应调用模型')

    monkeypatch.setattr(service, 'load_settings', lambda: SimpleNamespace(resolved_mode='demo'))
    monkeypatch.setattr(service, 'chat', forbidden)
    with pytest.raises(HTTPException) as excinfo:
        service.recognize_question(service.RecognizeInput(image_base64=PNG_1PX), None)
    assert excinfo.value.status_code == 503


# ---------------------------------------------------------------- 知识库与资源

def test_suggest_topic_only_when_covered():
    assert knowledge.suggest_topic('求定积分 integral_0^1 x^2 dx') == '一元函数积分学'
    assert knowledge.suggest_topic('判断级数 sum(1/n^2) 的敛散性') == '无穷级数'
    assert knowledge.suggest_topic('求 lim(x→0) sin x / x') == '极限与连续'
    assert knowledge.suggest_topic("求微分方程 y'=y 的通解") is None
    assert knowledge.suggest_topic('今天天气不错') is None


def test_knowledge_stats_include_resources_and_new_topics():
    stats = knowledge.stats()
    assert stats['points'] >= 12
    assert stats['resources'] >= stats['points'] * 3
    assert '一元函数积分学' in stats['topics']
    assert '无穷级数' in stats['topics']


def test_search_resources_returns_cited_items():
    items = knowledge.search_resources('定积分 面积 计算', limit=4)
    assert items, '资源检索不应为空'
    for item in items:
        assert item['source']
        assert item['kind'] in {'概念讲解', '例题', '练习', '资料'}
        assert item['verified'] is False


# ---------------------------------------------------------------- 接口鉴权与能力

def test_memory_requires_login():
    with TestClient(app) as anonymous:
        assert anonymous.get('/api/agent/memory').status_code == 401


def test_status_reports_phase2_capabilities():
    with TestClient(app) as anonymous:
        payload = anonymous.get('/api/agent/status').json()
    assert payload['phase'] == 2
    capabilities = payload['capabilities']
    for key in ('memory', 'recommendation', 'review', 'summary', 'resource_search', 'step_feedback'):
        assert capabilities[key] is True
    assert capabilities['async_tasks'] is False
    assert payload['knowledge']['resources'] > 0


# ---------------------------------------------------------------- 长期记忆闭环

def test_review_writes_memory_and_recommend_uses_it(client):
    text = '定积分是把区间分成很多小段再求和取极限，几何意义是曲线与 x 轴围成的面积，可以用牛顿-莱布尼茨公式计算。'
    review = client.post('/api/agent/review', json={'text': text, 'topic': '一元函数积分学'}, headers=HEADERS)
    assert review.status_code == 200
    body = review.json()
    assert body['point'] is not None
    assert body['band'] in {'基本到位', '有遗漏', '需要重讲'}
    assert body['mode'] == 'demo'
    assert body['method'].startswith('规则覆盖率')

    state = client.get('/api/agent/memory', headers=HEADERS).json()
    assert state['event_count'] >= 1
    assert any(item['point_id'] == body['point']['id'] for item in state['points'])
    assert state['evidence_tags']

    rec = client.post('/api/agent/recommend', json={'limit': 3}, headers=HEADERS)
    assert rec.status_code == 200
    items = rec.json()['items']
    assert items, '应给出推荐练习'
    assert all(item['prompt'] for item in items)
    excluded = [item['point_id'] for item in items[:1]]
    again = client.post('/api/agent/recommend', json={'limit': 3, 'exclude': excluded}, headers=HEADERS).json()
    assert all(item['point_id'] not in excluded for item in again['items'])


def test_step_feedback_and_diagnosis_write_memory(client):
    client.post('/api/agent/feedback',
                json={'question': '求 lim(x→0) sin(x)/x', 'step': '我直接用洛必达法则求导'},
                headers=HEADERS)
    client.post('/api/agent/diagnosis',
                json={'question': '洛必达法则怎么用？', 'answer': '我直接代入 0/0 就用了洛必达'},
                headers=HEADERS)
    client.post('/api/conversations', json={'question': '用定义求 x^2 的导数', 'topic': '导数与微分'},
                headers=HEADERS)
    state = client.get('/api/agent/memory', headers=HEADERS).json()
    assert {'step', 'diagnosis', 'ask'} <= set(state['kinds'])
    assert state['points'], '记忆里应出现知识点'


def test_summary_reports_window_and_next_steps(client):
    client.post('/api/conversations', json={'question': '求 lim(x→0) sin(x)/x', 'topic': '函数与极限'},
                headers=HEADERS)
    response = client.post('/api/agent/summary', json={'days': 7}, headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body['period_days'] == 7
    assert body['question_count'] >= 1
    assert body['highlights'] and body['next_steps']
    assert body['mode'] == 'demo'
    assert body['method'].endswith('（未调用模型）')


def test_clear_memory_removes_own_records(client):
    removed = client.delete('/api/agent/memory', headers=HEADERS)
    assert removed.status_code == 200
    assert removed.json()['removed'] >= 1
    assert client.get('/api/agent/memory', headers=HEADERS).json()['event_count'] == 0


# ---------------------------------------------------------------- 纯函数行为

def test_recommend_prioritizes_weak_points():
    state = {
        'points': [
            {'point_id': 'limit-techniques', 'title': '极限的四则运算与常见计算方法', 'topic': '极限与连续',
             'attempts': 3, 'positive': 0, 'negative': 3, 'mastery': 0.2, 'confidence': 0.9,
             'status': 'weak', 'last_seen': '2026-09-21T00:00:00+00:00'},
            {'point_id': 'continuity', 'title': '连续性与间断点分类', 'topic': '极限与连续',
             'attempts': 2, 'positive': 1, 'negative': 1, 'mastery': 0.5, 'confidence': 0.6,
             'status': 'learning', 'last_seen': '2026-09-21T00:00:00+00:00'},
        ],
        'event_count': 5,
    }
    result = insight.recommend(state, limit=2)
    assert result['items'][0]['point_id'] == 'limit-techniques'
    assert '优先' in result['items'][0]['reason']


def test_mastery_formula_is_conservative():
    assert memory._status_of(0.5, 0) == 'unseen'
    assert memory._status_of(0.5, 1) == 'learning'
    assert memory._status_of(0.33, 3) == 'weak'
    assert memory._status_of(0.8, 3) == 'mastered'


def test_evaluate_without_content_is_honest():
    result = insight.evaluate('   ')
    assert result['band'] == '无法评价'
    assert result['memory_weight'] == 0
    assert result['point'] is None
