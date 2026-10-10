"""B 模块第五阶段测试：复习排期、多题切分、按班掌握度聚合（只读 + 权限）。

运行：python -m pytest -q
测试使用独立的临时 SQLite 文件，不会碰到开发用的数据库。
"""
from __future__ import annotations

import atexit
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_DB_DIR = tempfile.TemporaryDirectory(prefix='shuban-agent-phase5-')
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
os.environ['DATABASE_URL'] = 'sqlite:///' + (Path(_DB_DIR.name) / 'phase5.db').as_posix()
os.environ['AGENT_MODE'] = 'demo'
os.environ['SHUBAN_SEED_DEMO'] = 'true'

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.ai import class_insight, question_split, review  # noqa: E402
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
MOMENT = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
LEAK_MARKER = 'ZZMARKER 这道题的条件是唯一的'


def _ago(days: float) -> str:
    return (MOMENT - timedelta(days=days)).isoformat()


STATE = {'points': [
    {'point_id': 'limit-techniques', 'attempts': 3, 'positive': 0, 'negative': 3, 'mastery': 0.2,
     'status': 'weak', 'last_seen': _ago(3)},
    {'point_id': 'derivative-definition', 'attempts': 4, 'positive': 3, 'negative': 0, 'mastery': 0.86,
     'status': 'mastered', 'last_seen': _ago(10)},
    {'point_id': 'continuity', 'attempts': 2, 'positive': 1, 'negative': 1, 'mastery': 0.5,
     'status': 'learning', 'last_seen': _ago(1)},
    {'point_id': 'integral-definite', 'attempts': 0, 'positive': 0, 'negative': 0, 'mastery': 0.5,
     'status': 'unseen', 'last_seen': _ago(0)},
]}


def _login(instance: TestClient, username: str, password: str, role: str) -> TestClient:
    response = instance.post('/api/auth/login',
                             json={'username': username, 'password': password, 'role': role},
                             headers=HEADERS)
    assert response.status_code == 200, response.text
    return instance


@pytest.fixture(scope='module')
def student():
    with TestClient(app) as instance:
        yield _login(instance, 'student', 'Student123!', 'student')


@pytest.fixture(scope='module')
def teacher():
    with TestClient(app) as instance:
        yield _login(instance, 'teacher', 'Teacher123!', 'teacher')


# ---------------------------------------------------------------- 复习排期

def test_review_intervals_and_ordering():
    plan = review.plan(STATE, days=7, limit=5, now=MOMENT)
    assert [review.intervals_for(status) for status in ('weak', 'learning', 'mastered')] == [1, 3, 7]
    # 薄弱优先，即使已较稳的知识点逾期更久。
    assert plan['items'][0]['point_id'] == 'limit-techniques'
    assert plan['items'][0]['overdue_days'] == 2.0
    assert [item['point_id'] for item in plan['items']] == ['limit-techniques', 'derivative-definition']
    assert '未经学习效果实验校准' in plan['rule']


def test_review_separates_upcoming_and_unscheduled():
    plan = review.plan(STATE, days=7, limit=5, now=MOMENT)
    assert [item['point_id'] for item in plan['upcoming']] == ['continuity']
    assert plan['due_count'] == 2
    assert plan['upcoming_count'] == 1
    assert [item['point_id'] for item in plan['unscheduled']] == ['integral-definite']


def test_review_topic_filter_and_empty_state():
    filtered = review.plan(STATE, topic='一元函数积分学', now=MOMENT)
    assert filtered['items'] == [] and filtered['upcoming'] == []
    empty = review.plan({'points': []}, now=MOMENT)
    assert empty['due_count'] == 0 and empty['items'] == []
    assert '不等于学生已经忘记' in empty['note']


def test_review_rejects_absent_state():
    plan = review.plan(None, now=MOMENT)
    assert plan['due_count'] == 0 and plan['intervals']['weak'] == 1


# ---------------------------------------------------------------- 多题切分

def test_split_numbered_questions():
    text = ('1. 求 lim(x→0) sin(x)/x\n'
            '2. 用定义求 f(x)=x^2 的导数\n'
            '3. 判断级数 sum(1/n^2) 是否收敛')
    result = question_split.split(text)
    assert result['strategy'] == 'markers'
    assert result['total'] == 3
    assert [item['index'] for item in result['items']] == [1, 2, 3]
    assert result['items'][0]['text'] == '求 lim(x→0) sin(x)/x'
    assert result['items'][2]['suggested_topic'] == '无穷级数'
    assert result['requires_confirmation'] is True
    assert result['confirm_endpoint'] == '/api/conversations'


@pytest.mark.parametrize('marker', ['第一题', '①', '（2）'])
def test_split_supports_cn_and_circled_markers(marker):
    text = f'{marker} 求 lim(x→0) sin(x)/x 的极限值是多少呢\n第二题 用定义求导数并说明依据'
    result = question_split.split(f'{marker} 求 lim(x→0) sin(x)/x 的极限值是多少呢\n第二题 用定义求导数并说明依据')
    assert result['strategy'] == 'markers'
    assert result['total'] == 2, text


def test_split_without_markers_uses_question_verbs():
    result = question_split.split('求 lim(x→0) sin x / x。计算定积分 ∫0..1 x^2 dx。证明可导必连续。')
    assert result['strategy'] == 'sentences'
    assert result['total'] == 3
    assert result['items'][0]['text'].startswith('求 lim')


def test_split_single_question_is_honest():
    result = question_split.split('求 lim(x→0) sin(x)/x')
    assert result['strategy'] == 'single'
    assert result['total'] == 1
    assert '没有识别到分题标记' in result['notice']


def test_split_truncates_and_reports():
    many = '\n'.join(f'{index}. 求第 {index} 题的计算过程' for index in range(1, 15))
    result = question_split.split(many)
    assert result['total'] == question_split.MAX_ITEMS
    assert result['truncated'] is True
    assert '分批确认' in result['notice']


def test_split_empty_input():
    result = question_split.split('   ')
    assert result['items'] == []
    assert '没有收到可切分的文本' in result['notice']


# ---------------------------------------------------------------- 班级聚合（纯逻辑）

def test_class_insight_thresholds_documented():
    described = class_insight.describe()
    assert described['outputs']
    assert '不包含学生作答原文' in described['privacy']
    assert 'C 的班级权限为准' in described['scope_note']


# ---------------------------------------------------------------- 接口

def test_new_endpoints_require_login():
    with TestClient(app) as anonymous:
        assert anonymous.post('/api/agent/review-plan', json={}).status_code in (401, 403)
        assert anonymous.post('/api/agent/recognize/split', json={'text': '1. 求极限'}).status_code in (401, 403)
        assert anonymous.get('/api/agent/class-insight/summary').status_code in (401, 403)


def test_review_plan_endpoint_uses_memory(student):
    student.post('/api/agent/feedback',
                 json={'question': '求 lim(x→0) sin(x)/x', 'step': '我直接用洛必达法则求导'},
                 headers=HEADERS)
    response = student.post('/api/agent/review-plan', json={'days': 7, 'limit': 5}, headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body['intervals'] == review.INTERVALS
    assert '未调用模型' in body['method']
    assert isinstance(body['items'], list)

    bad = student.post('/api/agent/review-plan', json={'days': 999}, headers=HEADERS)
    assert bad.status_code == 422


def test_split_endpoint(student):
    response = student.post('/api/agent/recognize/split',
                            json={'text': '1. 求 lim(x→0) sin(x)/x\n2. 用定义求导数'}, headers=HEADERS)
    assert response.status_code == 200
    assert response.json()['total'] == 2

    assert student.post('/api/agent/recognize/split', json={'text': '   '},
                        headers=HEADERS).status_code == 422
    assert student.post('/api/agent/recognize/split', json={'text': 'x' * 6001},
                        headers=HEADERS).status_code == 422


def test_class_insight_is_teacher_only(student):
    assert student.get('/api/agent/class-insight/summary', headers=HEADERS).status_code in (401, 403)
    assert student.get('/api/agent/class-insight?class_id=demo-class', headers=HEADERS).status_code in (401, 403)


def test_class_insight_aggregates_evidence_without_answers(teacher, student):
    student.post('/api/conversations',
                 json={'question': LEAK_MARKER, 'topic': '函数与极限'}, headers=HEADERS)
    student.post('/api/agent/feedback',
                 json={'question': '求 lim(x→0) sin(x)/x', 'step': '我直接用洛必达法则求导'},
                 headers=HEADERS)

    summary = teacher.get('/api/agent/class-insight/summary', headers=HEADERS)
    assert summary.status_code == 200
    body = summary.json()
    assert body['total'] >= 1
    demo = [item for item in body['classes'] if item['class_id'] == 'demo-class'][0]
    assert demo['summary']['students'] >= 1
    assert '不包含学生作答原文' in body['privacy']

    detail = teacher.get('/api/agent/class-insight?class_id=demo-class', headers=HEADERS)
    assert detail.status_code == 200
    payload = detail.json()
    assert payload['class']['name']
    student_row = [item for item in payload['students'] if item['id'] == 'student'][0]
    assert student_row['event_count'] >= 2
    assert student_row['evidence_points'] >= 1
    assert payload['points'], '应当有点级聚合'
    assert payload['points'][0]['students_with_evidence'] >= 1
    assert '未练' in payload['unseen_note']
    assert '拉普拉斯平滑' in payload['mastery_rule']
    # 隐私：聚合结果里不能出现学生作答/问题原文。
    assert LEAK_MARKER not in detail.text
    assert '洛必达法则求导' not in detail.text


def test_class_insight_rejects_other_teacher_and_unknown_class(teacher):
    created = teacher.post('/api/auth/teachers',
                           json={'username': 'co-teacher', 'name': '协同教师',
                                 'password': 'CoTeacher123!'}, headers=HEADERS)
    assert created.status_code == 201
    with TestClient(app) as other:
        _login(other, 'co-teacher', 'CoTeacher123!', 'teacher')
        # 平台侧新教师带临时密码，必须先用 /api/auth/password 改密，否则其他接口一律 403。
        changed = other.post('/api/auth/password',
                             json={'current_password': 'CoTeacher123!',
                                   'new_password': 'CoTeacher456!'}, headers=HEADERS)
        assert changed.status_code == 200, changed.text
        summary = other.get('/api/agent/class-insight/summary', headers=HEADERS)
        assert summary.status_code == 200
        assert summary.json()['total'] == 0
        assert other.get('/api/agent/class-insight?class_id=demo-class',
                         headers=HEADERS).status_code == 404
    assert teacher.get('/api/agent/class-insight?class_id=nope', headers=HEADERS).status_code == 404


def test_status_reports_stage5():
    with TestClient(app) as anonymous:
        payload = anonymous.get('/api/agent/status').json()
    assert payload['phase'] == 2  # 冻结字段
    assert payload['stage'] >= 5
    for key in ('review_plan', 'class_insight', 'question_split'):
        assert payload['capabilities'][key] is True
