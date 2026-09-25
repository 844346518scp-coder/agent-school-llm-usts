"""B 模块第三阶段测试：分层提示、图形批注、数学工具、语音适配、准确性评测、教师纠错、降级统计。

运行：python -m pytest -q
测试使用独立的临时 SQLite 文件，不会碰到开发用的数据库。
"""
from __future__ import annotations

import atexit
import base64
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_DB_DIR = tempfile.TemporaryDirectory(prefix='shuban-agent-phase3-')
os.environ['PYTHON_DOTENV_DISABLED'] = '1'
os.environ['DATABASE_URL'] = 'sqlite:///' + (Path(_DB_DIR.name) / 'phase3.db').as_posix()
os.environ['AGENT_MODE'] = 'demo'
os.environ['SHUBAN_SEED_DEMO'] = 'true'

from fastapi.testclient import TestClient  # noqa: E402

from backend.app.ai import evaluation, hints, knowledge, mathcheck, plotting, resilience, voice  # noqa: E402
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
WAV_BYTES = b'RIFF' + b'\x00' * 4 + b'WAVE' + b'\x00' * 600
WAV_BASE64 = base64.b64encode(WAV_BYTES).decode()


def _login(instance: TestClient, username: str, password: str) -> TestClient:
    login = instance.post('/api/auth/login',
                          json={'username': username, 'password': password, 'role': username},
                          headers=HEADERS)
    assert login.status_code == 200, login.text
    return instance


@pytest.fixture(scope='module')
def student():
    with TestClient(app) as instance:
        yield _login(instance, 'student', 'Student123!')


@pytest.fixture(scope='module')
def teacher():
    with TestClient(app) as instance:
        yield _login(instance, 'teacher', 'Teacher123!')


# ---------------------------------------------------------------- 数学工具

def test_power_binds_tighter_than_unary_minus():
    """-x^2 必须是 -(x^2)：准确性评测发现过的优先级错误，作为回归用例保留。"""
    assert mathcheck.evaluate('-x^2', 3) == -9
    assert mathcheck.evaluate('(-x)^2', 3) == 9
    assert mathcheck.evaluate('2^3^2', 0) == 512
    assert mathcheck.evaluate('2^-1', 0) == 0.5


def test_derivative_matches_numeric_check():
    for expr in ('x^2', 'sin(x)/x', 'exp(-x^2)', 'ln(x)+3*x', 'sqrt(1+x^2)'):
        report = mathcheck.derivative_report(expr)
        assert report['ok'], (expr, report['error'])
        assert report['numeric_agreement']['ok'], (expr, report['numeric_agreement'])
        assert report['derivative_latex']


def test_derivative_unsupported_is_reported_not_guessed():
    report = mathcheck.derivative_report('abs(x)')
    assert report['ok'] is False
    assert 'abs' in report['error']


def test_equivalence_detects_difference():
    assert mathcheck.equivalent('x^2', 'x*x')['ok'] is True
    mismatch = mathcheck.equivalent('x^2', '2*x')
    assert mismatch['ok'] is False
    assert mismatch['counter_examples']


def test_limit_probe_is_honest_about_divergence():
    assert mathcheck.probe_limit('sin(x)/x', 0)['ok'] is True
    assert mathcheck.probe_limit('1/x', 0)['ok'] is False
    assert '不是严格证明' in mathcheck.probe_limit('sin(x)/x', 0)['method']


def test_check_value_reports_mismatch():
    assert mathcheck.check_value('x^2', 2, 4)['ok'] is True
    wrong = mathcheck.check_value('x^2', 2, 5)
    assert wrong['ok'] is False and wrong['reason']


# ---------------------------------------------------------------- 分层提示

def test_hint_levels_are_distinct_and_never_leak_answers():
    texts = [hints.build('求 lim(x→0) sin(x)/x 的极限', level=level)['hint'] for level in (1, 2, 3)]
    assert len(set(texts)) == 3
    assert all(text.strip() for text in texts)
    first = hints.build('求 lim(x→0) sin(x)/x 的极限', level=1)
    assert first['answer_leaked'] is False
    assert first['guard'] and first['next_level'] == 2
    third = hints.build('求 lim(x→0) sin(x)/x 的极限', level=3)
    assert third['next_level'] is None


def test_hint_without_knowledge_match_is_honest():
    result = hints.build('今天天气怎么样', level=2)
    assert result['point'] is None
    assert result['notice'] is None
    assert '没有检索到' in result['hint']


def test_hint_live_failure_falls_back_to_rule_text(monkeypatch):
    def broken(*_args, **_kwargs):
        raise ModelCallFailed('模型返回 HTTP 500。')

    monkeypatch.setattr(hints, 'chat', broken)
    result = hints.build('求 lim(x→0) sin(x)/x 的极限', level=1,
                         settings=SimpleNamespace(resolved_mode='live'))
    assert result['mode'] == 'demo'
    assert '模型提示生成失败' in result['notice']


# ---------------------------------------------------------------- 图形批注

def test_extract_expression_from_question():
    assert plotting.extract_expression('画 f(x)=x^2-1 的图像并标出零点') == 'x^2-1'
    assert plotting.extract_expression('今天天气不错') is None


def test_plot_coordinates_come_from_local_tool():
    result = plotting.annotate('画 f(x)=x^2-1 的图像并标出零点', at=1.0)
    assert result['mode'] == 'demo'
    assert result['function']['expr']
    assert len(result['samples']) >= 40
    kinds = {item['kind'] for item in result['key_points']}
    assert {'zero', 'extremum', 'tangent'} <= kinds
    tangent = [item for item in result['key_points'] if item['kind'] == 'tangent'][0]
    assert tangent['x'] == 1.0 and tangent['y'] == 0.0
    assert result['steps'] and result['honesty']


def test_plot_without_expression_is_honest():
    result = plotting.annotate('这道题怎么做')
    assert result['function'] is None
    assert '没有从题目里解析出函数表达式' in result['notice']


def test_plot_circle_shape():
    result = plotting.annotate('', circle={'cx': 1.0, 'cy': 2.0, 'radius': 3.0})
    assert result['shape'] == 'circle'
    assert result['key_points'][0]['kind'] == 'center'
    assert len(result['samples']) > 10


# ---------------------------------------------------------------- 语音适配

def test_audio_validation_rejects_bad_input():
    with pytest.raises(ValueError):
        voice.check_audio('@' * 32, 'audio/wav')
    with pytest.raises(ValueError):
        voice.check_audio(WAV_BASE64, 'text/plain')
    with pytest.raises(ValueError):
        voice.check_audio(base64.b64encode(b'not an audio file at all' * 40).decode(), 'audio/wav')


def test_audio_validation_prefers_real_header():
    checked = voice.check_audio(WAV_BASE64, 'audio/mpeg')
    assert checked['media_type'] == 'audio/wav'
    assert checked['size'] == len(WAV_BYTES)


def test_transcript_normalisation_is_reviewable():
    result = voice.normalize_transcript('嗯 x 的平方 加 1 趋于 无穷大 的极限')
    assert '^2' in result['text'] and '→' in result['text'] and '∞' in result['text']
    assert result['changed'] is True
    assert any(item['from'] == '平方' for item in result['corrections'])


def test_voice_status_is_honest_in_demo_mode():
    status = voice.status()
    assert status['ready'] is False
    assert status['credential_source'] == 'none'
    assert status['text_to_speech'] is False
    assert status['browser_fallback']['available'] is True


def test_voice_transcribe_without_credentials_raises():
    checked = voice.check_audio(WAV_BASE64, 'audio/wav')
    with pytest.raises(voice.VoiceUnavailable):
        voice.transcribe(checked)
    assert '不返回编造文本' in voice.status()['note']


# ---------------------------------------------------------------- 超时降级

def test_call_model_retries_only_timeouts():
    calls: list[int] = []

    def flaky() -> str:
        calls.append(1)
        if len(calls) == 1:
            raise ModelCallFailed('网络连接失败或超时，请检查模型服务。')
        return '模型回答'

    text, meta = resilience.call_model(flaky, endpoint='test')
    assert text == '模型回答'
    assert meta['attempts'] == 2


def test_call_model_does_not_retry_http_errors():
    calls: list[int] = []

    def broken() -> str:
        calls.append(1)
        raise ModelCallFailed('模型返回 HTTP 500。')

    with pytest.raises(ModelCallFailed):
        resilience.call_model(broken, endpoint='test')
    assert len(calls) == 1


def test_resilience_events_are_sanitized():
    resilience.reset()
    event = resilience.record('model_timeout', 'POST /api/agent/ask',
                              'Bearer synthetic-secret-token-abcdefghijklmnop https://api.example.com/v1 超时')
    assert 'https://' not in event['detail']
    assert 'synthetic-secret-token' not in event['detail']
    stats = resilience.stats()
    assert stats['counters']['model_timeout'] == 1
    assert stats['retry_policy']['max_attempts'] == 2
    assert stats['codes']['model_timeout']
    resilience.reset()


def test_coerce_helpers_fix_invalid_model_fields():
    assert resilience.coerce_enum('wrong', ('a', 'b'), 'a') == 'a'
    assert resilience.coerce_enum('b', ('a', 'b'), 'a') == 'b'
    assert resilience.coerce_text(123, 'fallback') == 'fallback'


# ---------------------------------------------------------------- 知识库回归

def test_out_of_scope_topics_still_return_none():
    assert knowledge.suggest_topic("求微分方程 y'=y 怎么解") is None
    assert knowledge.suggest_topic('概率论里的条件概率') is None


# ---------------------------------------------------------------- 接口

def test_phase3_endpoints_require_login():
    with TestClient(app) as anonymous:
        assert anonymous.get('/api/agent/voice/status').status_code == 200
        assert anonymous.post('/api/agent/hint', json={'question': '求极限', 'level': 1}).status_code in (401, 403)
        assert anonymous.post('/api/agent/plot/annotate', json={'expr': 'x^2'}).status_code in (401, 403)
        assert anonymous.get('/api/agent/diagnostics').status_code in (401, 403)


def test_hint_and_plot_endpoints(student):
    hint = student.post('/api/agent/hint',
                        json={'question': '求 lim(x→0) sin(x)/x 的极限', 'level': 3}, headers=HEADERS)
    assert hint.status_code == 200
    assert hint.json()['level_title'] == '关键步骤提示'

    plot = student.post('/api/agent/plot/annotate',
                        json={'question': '画 f(x)=x^2-1 的图像并标出零点', 'at': 1.0}, headers=HEADERS)
    assert plot.status_code == 200
    assert plot.json()['samples']


def test_math_check_endpoint(student):
    response = student.post('/api/agent/math/check',
                            json={'expr': '(x+1)(x-1)', 'x': 3, 'expected': 8, 'compare_expr': 'x^2-1'},
                            headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body['value']['value'] == 8
    assert body['value_check']['ok'] is True
    assert body['equivalence']['ok'] is True
    assert body['derivative']['ok'] is True

    bad = student.post('/api/agent/math/check', json={'expr': 'x^'}, headers=HEADERS)
    assert bad.status_code == 422


def test_voice_endpoint_returns_503_with_fallback(student):
    response = student.post('/api/agent/voice/transcribe',
                            json={'audio_base64': WAV_BASE64, 'media_type': 'audio/wav'}, headers=HEADERS)
    assert response.status_code == 503
    assert 'browser_fallback' in response.json()['detail']

    malformed = student.post('/api/agent/voice/transcribe',
                             json={'audio_base64': '@' * 32, 'media_type': 'audio/wav'}, headers=HEADERS)
    assert malformed.status_code == 422


def test_stage_reported_without_breaking_frozen_phase_field():
    with TestClient(app) as anonymous:
        payload = anonymous.get('/api/agent/status').json()
    assert payload['phase'] == 2  # 冻结字段，启动器与既有测试依赖
    assert payload['stage'] == 3
    capabilities = payload['capabilities']
    for key in ('hints', 'plot_annotation', 'math_tools', 'accuracy_eval', 'teacher_correction'):
        assert capabilities[key] is True
    assert capabilities['voice_input'] is False  # demo 模式未配置语音服务
    assert payload['model']['ready'] is False


def test_diagnostics_endpoint_reports_policy(student):
    body = student.get('/api/agent/diagnostics', headers=HEADERS).json()
    assert body['retry_policy']['max_attempts'] == 2
    assert body['math_tools']['exact_derivative'] is True
    assert body['voice']['ready'] is False
    assert '仅统计本进程' in body['scope']


# ---------------------------------------------------------------- 教师纠错

def test_teacher_correction_appends_evidence(teacher, student):
    student.post('/api/agent/feedback',
                 json={'question': '求 lim(x→0) sin(x)/x', 'step': '我直接用洛必达法则求导'},
                 headers=HEADERS)
    before = student.get('/api/agent/memory', headers=HEADERS).json()

    response = teacher.post('/api/agent/corrections',
                            json={'student_id': 'student', 'point_id': 'limit-techniques',
                                  'corrected': 'correct',
                                  'reason': '洛必达的条件判断课堂上已确认正确，属于判断口径问题。'},
                            headers=HEADERS)
    assert response.status_code == 200
    body = response.json()
    assert body['correction']['weight'] == 2
    assert body['after'] is not None and body['after']['point_id'] == 'limit-techniques'
    assert '原始学习证据未删除' in body['note']

    after = student.get('/api/agent/memory', headers=HEADERS).json()
    assert after['event_count'] == before['event_count'] + 1  # 追加而不是覆盖

    history = student.get('/api/agent/corrections', headers=HEADERS).json()
    assert history['scope'] == 'own_account'
    assert history['items'] and history['items'][0]['point_title']


def test_correction_rejects_unknown_point_and_blank_reason(teacher):
    unknown = teacher.post('/api/agent/corrections',
                           json={'student_id': 'student', 'point_id': 'not-a-point',
                                 'corrected': 'correct', 'reason': '测试'}, headers=HEADERS)
    assert unknown.status_code == 422

    blank = teacher.post('/api/agent/corrections',
                         json={'student_id': 'student', 'point_id': 'limit-techniques',
                               'corrected': 'correct', 'reason': '   '}, headers=HEADERS)
    assert blank.status_code == 422


def test_student_cannot_create_correction(student):
    response = student.post('/api/agent/corrections',
                            json={'student_id': 'student', 'point_id': 'limit-techniques',
                                  'corrected': 'correct', 'reason': '自评通过'}, headers=HEADERS)
    assert response.status_code in (401, 403)


# ---------------------------------------------------------------- 准确性评测

def test_evaluation_suites_pass_in_demo_mode():
    report = evaluation.run()
    assert report['overall']['ok'] is True
    assert report['overall']['cases'] == report['overall']['passed']
    assert {item['name'] for item in report['suites']} >= {'retrieval', 'math', 'honesty'}
    assert '真实模型' in report['scope']


def test_evaluation_endpoint_is_teacher_only(teacher, student):
    refused = student.post('/api/agent/evaluate', json={}, headers=HEADERS)
    assert refused.status_code in (401, 403)

    response = teacher.post('/api/agent/evaluate', json={'suites': ['retrieval', 'math']}, headers=HEADERS)
    assert response.status_code == 200
    assert response.json()['overall']['ok'] is True

    unknown = teacher.post('/api/agent/evaluate', json={'suites': ['nope']}, headers=HEADERS)
    assert unknown.status_code == 422
