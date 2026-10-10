"""B 模块第四阶段测试：刻意练习 / 苏格拉底追问、知识讲解拆解（知识树），以及图注字段回归。

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

_DB_DIR = tempfile.TemporaryDirectory(prefix='shuban-agent-phase4-')
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
os.environ['DATABASE_URL'] = 'sqlite:///' + (Path(_DB_DIR.name) / 'phase4.db').as_posix()
os.environ['AGENT_MODE'] = 'demo'
os.environ['SHUBAN_SEED_DEMO'] = 'true'

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.ai import knowledge, knowledge_tree, plotting, practice  # noqa: E402
from backend.app.ai.llm import ModelCallFailed  # noqa: E402
from backend.app.main import app  # noqa: E402
from backend.app.platform.database import engine as db_engine  # noqa: E402


def _cleanup() -> None:
    try:
        db_engine.dispose()
    except Exception:  # noqa: BLE001 - 清理失败不应影响测试结论
        pass
    _DB_DIR.cleanup()


atexit.register(_cleanup)

HEADERS = {'X-Requested-With': 'shuban-web'}

WEAK_STATE = {'points': [{
    'point_id': 'limit-techniques', 'title': '极限的四则运算与常见计算方法', 'topic': '极限与连续',
    'attempts': 3, 'positive': 0, 'negative': 3, 'mastery': 0.2, 'confidence': 0.9,
    'status': 'weak', 'last_seen': '2026-09-25T00:00:00+00:00',
}]}


@pytest.fixture(scope='module')
def student():
    with TestClient(app) as instance:
        login = instance.post('/api/auth/login',
                              json={'username': 'student', 'password': 'Student123!', 'role': 'student'},
                              headers=HEADERS)
        assert login.status_code == 200, login.text
        yield instance


# ---------------------------------------------------------------- 刻意练习计划

def test_plan_prefers_weak_point():
    plan = practice.plan(WEAK_STATE)
    assert plan['session']['point_id'] == 'limit-techniques'
    assert '优先重练' in plan['why']
    assert plan['mode'] == 'demo'


def test_plan_steps_do_not_leak_expected_answers():
    plan = practice.plan(WEAK_STATE)
    assert [step['kind'] for step in plan['steps']] == ['recall', 'boundary', 'compute', 'transfer']
    assert plan['session']['total_steps'] == practice.TOTAL_STEPS
    for step in plan['steps']:
        # 公开计划只能有这四个字段：期望关键词与期望数值属于私有评价依据。
        assert sorted(step) == ['index', 'kind', 'prompt', 'title']
        assert step['prompt'].strip()
    assert '不包含期望关键词' in plan['leak_guard']
    assert plan['steps'][2]['prompt'].count('= 结果') == 1


def test_plan_without_memory_starts_from_first_point():
    plan = practice.plan({'points': []}, topic='无穷级数')
    assert plan['session']['point_id'] == 'series-convergence'
    assert '还没有练习记录' in plan['why']


def test_plan_rejects_unknown_point():
    with pytest.raises(ValueError):
        practice.plan(WEAK_STATE, point_id='not-a-point')


# ---------------------------------------------------------------- 逐步评价

def test_answer_verifies_explicit_result_with_math_tool():
    correct = practice.answer('important-limits', 3, '先整理成 sin u/u 的形式，取极限 = 1')
    assert correct['verdict'] == 'correct'
    assert correct['band'] == '数值核对通过'
    assert correct['memory_weight'] == 2
    assert correct['numeric_check']['matched'] == [1.0]

    wrong = practice.answer('important-limits', 3, '0/0 是不定式，我先直接代入，得到 0')
    assert wrong['verdict'] == 'incorrect'
    assert wrong['memory_weight'] == -2
    assert '不一致' in wrong['feedback']


def test_answer_without_explicit_result_is_not_judged():
    result = practice.answer('important-limits', 3, '先利用重要极限，把式子整理成 sin u/u 的形式再取极限')
    assert result['verdict'] == 'unverifiable'
    assert result['numeric_check']['ok'] is None
    assert '没有写出显式结果' in result['numeric_check']['note']


def test_answer_scores_recall_by_coverage():
    good = practice.answer('important-limits', 1, '重要极限刻画 sin x 与 x 在 0 附近同阶，比值趋于 1')
    assert good['band'] == '基本到位'
    assert good['coverage'] >= 0.6
    assert good['memory_weight'] == 1
    assert good['follow_up']

    poor = practice.answer('important-limits', 1, '不知道')
    assert poor['band'] == '需要重讲'
    assert poor['memory_weight'] == -1


def test_answer_next_step_and_completion():
    first = practice.answer('derivative-definition', 1, '导数刻画局部的变化率，可导必连续')
    assert first['next_step']['index'] == 2
    assert first['completed'] is False
    last = practice.answer('derivative-definition', 4, '如果最后一条要点不成立，结论需要重新检查前提条件')
    assert last['next_step'] is None and last['completed'] is True


def test_answer_rejects_bad_input():
    with pytest.raises(ValueError):
        practice.answer('unknown-point', 1, '随便写点')
    with pytest.raises(ValueError):
        practice.answer('important-limits', 5, '超过步数')
    with pytest.raises(ValueError):
        practice.answer('important-limits', 1, '   ')


def test_answer_live_failure_keeps_rule_feedback(monkeypatch):
    def broken(*_args, **_kwargs):
        raise ModelCallFailed('模型返回 HTTP 500。')

    monkeypatch.setattr(practice, 'chat', broken)
    result = practice.answer('important-limits', 1, '重要极限刻画 sin x 与 x 在 0 附近同阶，比值趋于 1',
                             settings=SimpleNamespace(resolved_mode='live'))
    assert result['mode'] == 'demo'
    assert '模型反馈生成失败' in result['notice']
    assert result['band'] == '基本到位'


# ---------------------------------------------------------------- 知识树

def test_tree_covers_all_points_and_edges_are_valid():
    tree = knowledge_tree.tree()
    assert [item['topic'] for item in tree['topics']] == list(knowledge_tree.TOPIC_ORDER)
    assert tree['total_points'] == len(knowledge.KNOWLEDGE_POINTS) == 12
    known = {point.id for point in knowledge.KNOWLEDGE_POINTS}
    for edge in tree['edges']:
        assert edge['from'] in known and edge['to'] in known
    assert tree['edges']
    first = [point for item in tree['topics'] for point in item['points'] if point['id'] == 'limit-definition'][0]
    assert {item['id'] for item in first['unlocks']} >= {'limit-techniques', 'continuity'}
    assert '待复核' in tree['note']


def test_explain_builds_renderable_branches():
    result = knowledge_tree.explain('integral-ftc')
    assert result['root']['label']
    assert result['branch_count'] >= 5
    for branch in result['branches']:
        assert branch['label'] and branch['children']
        for child in branch['children']:
            assert child['label'] and child['text']
            assert ' ' not in child['id']  # 叶子 id 供前端做 key，保持简单
    labels = [branch['label'] for branch in result['branches']]
    assert '关键要点' in labels and '例题拆解' in labels
    assert result['mode'] == 'demo'


def test_explain_rejects_unknown_point():
    with pytest.raises(ValueError):
        knowledge_tree.explain('not-a-point')


def test_explain_live_falls_back_on_invalid_structure(monkeypatch):
    monkeypatch.setattr(knowledge_tree, 'chat', lambda *args, **kwargs: '{"summary": "只有一句话"}')
    result = knowledge_tree.explain('continuity', settings=SimpleNamespace(resolved_mode='live'))
    assert result['mode'] == 'demo'
    assert '不符合约定' in result['notice']
    assert result['branch_count'] >= 5


# ---------------------------------------------------------------- 图注字段回归

def test_plot_derivative_checked_is_boolean():
    """前端按布尔判断“数值复核是否通过”，后端不能再返回对象（9/25 曾因此永不报警）。"""
    result = plotting.annotate('画 f(x)=x^2-1 的图像', at=1.0)
    assert result['function']['derivative_checked'] is True
    assert result['function']['derivative_check']['ok'] is True
    unsupported = plotting.annotate('画 f(x)=abs(x) 的图像')
    assert unsupported['function']['derivative_checked'] is None
    assert unsupported['function']['derivative_check'] is None


# ---------------------------------------------------------------- 接口

def test_phase4_endpoints_require_login():
    with TestClient(app) as anonymous:
        assert anonymous.get('/api/agent/knowledge/tree').status_code in (401, 403)
        assert anonymous.post('/api/agent/practice/plan', json={}).status_code in (401, 403)
        assert anonymous.post('/api/agent/knowledge/explain',
                              json={'point_id': 'continuity'}).status_code in (401, 403)


def test_practice_api_records_memory_evidence(student):
    plan = student.post('/api/agent/practice/plan', json={'point_id': 'important-limits'}, headers=HEADERS)
    assert plan.status_code == 200
    body = plan.json()
    assert body['session']['total_steps'] == 4

    answer = student.post('/api/agent/practice/answer',
                          json={'point_id': 'important-limits', 'step_index': 3,
                                'answer': '先整理成 sin u/u 的形式，取极限 = 1'}, headers=HEADERS)
    assert answer.status_code == 200
    payload = answer.json()
    assert payload['verdict'] == 'correct'
    assert payload['memory_recorded'] is True

    state = student.get('/api/agent/memory', headers=HEADERS).json()
    assert 'practice' in state['kinds']
    assert '刻意练习作答' in state['evidence_tags']
    assert any(item['point_id'] == 'important-limits' for item in state['points'])


def test_knowledge_endpoints(student):
    tree = student.get('/api/agent/knowledge/tree', headers=HEADERS).json()
    assert tree['total_points'] == 12

    explain = student.post('/api/agent/knowledge/explain', json={'point_id': 'continuity'}, headers=HEADERS)
    assert explain.status_code == 200
    assert explain.json()['branches']

    unknown = student.post('/api/agent/knowledge/explain', json={'point_id': 'nope'}, headers=HEADERS)
    assert unknown.status_code == 422

    bad_step = student.post('/api/agent/practice/answer',
                            json={'point_id': 'continuity', 'step_index': 4, 'answer': '  '}, headers=HEADERS)
    assert bad_step.status_code == 422


def test_status_reports_stage4_without_changing_frozen_fields():
    with TestClient(app) as anonymous:
        payload = anonymous.get('/api/agent/status').json()
    assert payload['phase'] == 2  # 冻结字段，启动器与既有测试依赖
    assert payload['stage'] >= 4  # 阶段号随迭代递增（当前为第五阶段），phase 保持不变
    capabilities = payload['capabilities']
    for key in ('deliberate_practice', 'knowledge_tree', 'teaching_logic'):
        assert capabilities[key] is True
