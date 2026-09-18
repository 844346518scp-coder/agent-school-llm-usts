"""B 模块（智能体）单元测试：检索、诊断、提示词与模式降级。

运行方式（仓库根目录）：
    python -m pytest -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.ai import diagnosis, knowledge, prompts  # noqa: E402
from backend.app.ai.config import load_settings  # noqa: E402


def test_tokenize_builds_chinese_bigrams():
    tokens = knowledge.tokenize('求极限洛必达')
    assert '极限' in tokens
    assert '洛必' in tokens and '必达' in tokens
    assert '洛必达' not in tokens


def test_retrieve_returns_limit_point_with_source():
    hits = knowledge.retrieve('求 lim(x→0) sin(x)/x 的极限', top_k=3)
    assert hits, '检索不应为空'
    assert any('极限' in hit.point.title for hit in hits)
    for hit in hits:
        assert hit.point.source, '教程片段必须带出处'
        assert hit.score > 0


def test_retrieve_respects_topic_hint():
    hits = knowledge.retrieve('用定义求 x^2 的导数', topic='导数与微分', top_k=3)
    assert hits
    assert hits[0].point.topic == '导数与微分'


def test_retrieve_empty_query_returns_nothing():
    assert knowledge.retrieve('   ') == []


def test_knowledge_stats_reports_pending_review():
    stats = knowledge.stats()
    assert stats['points'] == len(knowledge.KNOWLEDGE_POINTS)
    assert stats['verified_points'] == 0
    assert stats['pending_review'] == stats['points']


def test_diagnosis_flags_weak_points_from_evidence():
    result = diagnosis.diagnose(
        question='洛必达法则能不能直接用在 0/0 上？',
        answer='我直接代入得到 0/0，然后用洛必达法则求导。',
    )
    ids = [item['id'] for item in result['weak_points']]
    assert ids, result
    assert any(point_id.startswith('limit') for point_id in ids)
    assert result['suggested_practice'], '应给出变式练习'
    assert result['mode'] in {'demo', 'live'}


def test_diagnosis_without_evidence_is_honest():
    result = diagnosis.diagnose(question='今天天气不错')
    assert result['weak_points'] == []
    assert '未发现' in result['summary']
    assert result['mode'] == 'demo'


def test_diagnosis_confidence_is_bounded():
    result = diagnosis.diagnose(question='洛必达 不定式 等价无穷小 泰勒 有理化 通分 约分')
    for item in result['weak_points']:
        assert 0 < item['confidence'] <= 1


def test_prompts_number_references():
    chunks = knowledge.retrieve('函数极限的定义', top_k=2)
    messages = prompts.build_qa_messages('什么是函数极限？', '函数与极限', chunks)
    assert messages[0]['role'] == 'system'
    assert '概念层' in messages[1]['content']
    assert '[1]' in messages[1]['content']


def test_prompts_reference_block_matches_context_order():
    chunks = knowledge.retrieve('导数与微分', top_k=2)
    block = prompts.format_references(chunks)
    assert block.startswith('\n\n资料来源')
    assert '[1]' in block


def test_settings_demo_never_reports_live(monkeypatch):
    monkeypatch.setenv('AGENT_MODE', 'demo')
    monkeypatch.setenv('MODEL_API_KEY', 'should-be-ignored')
    assert load_settings().resolved_mode == 'demo'


def test_settings_live_without_credentials_falls_back_to_demo(monkeypatch):
    monkeypatch.setenv('AGENT_MODE', 'live')
    monkeypatch.delenv('MODEL_API_KEY', raising=False)
    monkeypatch.delenv('MODEL_BASE_URL', raising=False)
    assert load_settings().resolved_mode == 'demo'


def test_settings_auto_with_credentials_is_live(monkeypatch):
    monkeypatch.setenv('AGENT_MODE', 'auto')
    monkeypatch.setenv('MODEL_BASE_URL', 'https://example.com/v1')
    monkeypatch.setenv('MODEL_API_KEY', 'test-key')
    monkeypatch.setenv('MODEL_NAME', 'test-model')
    settings = load_settings()
    assert settings.model_ready
    assert settings.resolved_mode == 'live'


def test_settings_invalid_mode_defaults_to_auto(monkeypatch):
    monkeypatch.setenv('AGENT_MODE', '随便写的')
    monkeypatch.delenv('MODEL_API_KEY', raising=False)
    settings = load_settings()
    assert settings.mode == 'auto'
    assert settings.resolved_mode == 'demo'


def test_llm_endpoint_accepts_base_or_full_url():
    from backend.app.ai.llm import endpoint

    assert endpoint('https://example.com/v1') == 'https://example.com/v1/chat/completions'
    assert endpoint('https://example.com/v1/') == 'https://example.com/v1/chat/completions'
    assert endpoint('https://example.com/v1/chat/completions') == 'https://example.com/v1/chat/completions'


def test_llm_reports_unavailable_without_configuration(monkeypatch):
    from backend.app.ai import llm

    monkeypatch.setenv('AGENT_MODE', 'demo')
    monkeypatch.delenv('MODEL_API_KEY', raising=False)
    with pytest.raises(llm.ModelUnavailable):
        llm.chat([{'role': 'user', 'content': 'hi'}], load_settings())


def test_extract_json_handles_fenced_output():
    from backend.app.ai.llm import extract_json

    assert extract_json('```json\n{"summary": "ok"}\n```') == {'summary': 'ok'}
    assert extract_json('答案是 {"summary": "ok"} 结束') == {'summary': 'ok'}
    assert extract_json('没有 JSON') is None


def test_detect_mode_marks_demo_answers():
    from backend.app.ai.service import demo_reply, detect_mode

    assert detect_mode(demo_reply('求 lim sin x / x', '函数与极限', 'student')) == 'demo'
    assert detect_mode(demo_reply('任意问题', '函数与极限', 'student')) == 'demo'
    assert detect_mode('这是真实模型给出的解答，含 $\\lim$ 推导。') == 'live'


def test_demo_compose_never_claims_live(monkeypatch):
    from backend.app.ai.service import compose_answer

    monkeypatch.setenv('AGENT_MODE', 'live')
    monkeypatch.delenv('MODEL_API_KEY', raising=False)
    chunks = knowledge.retrieve('极限', top_k=1)
    answer, mode, notice = compose_answer('求 lim(x→0) sin x/x', '函数与极限', 'student', 'demo', chunks)
    assert mode == 'demo'
    assert notice is None
    assert '固定例题演示' in answer


def test_agent_status_endpoint_exposes_capabilities_without_secrets(monkeypatch):
    monkeypatch.setenv('AGENT_MODE', 'auto')
    monkeypatch.delenv('MODEL_API_KEY', raising=False)
    from fastapi.testclient import TestClient

    from backend.app.main import app

    with TestClient(app) as client:
        response = client.get('/api/agent/status')
    assert response.status_code == 200
    payload = response.json()
    assert payload['mode'] == 'demo'
    assert payload['model']['ready'] is False
    assert 'test-key' not in response.text
    assert payload['knowledge']['points'] > 0


def test_suggest_topic_from_recognized_text():
    assert knowledge.suggest_topic('求 lim(x→0) sin x / x') == '极限与连续'
    assert knowledge.suggest_topic('用定义求 x^2 的导数') == '导数与微分'


def test_step_feedback_flags_known_mistake():
    result = diagnosis.step_feedback('求 lim(x→0) sin x / x', '我直接用洛必达法则求导', topic='函数与极限')
    assert result['verdict'] == 'unclear'
    assert result['flagged'] == ['洛必达']
    assert result['mode'] == 'demo'
    assert result['references']
    assert result['next_question']


def test_step_feedback_never_claims_correct_in_demo():
    result = diagnosis.step_feedback('求 x^2 的导数', '先写出差商 (x+h)^2 - x^2', topic='导数与微分')
    assert result['verdict'] == 'unclear'
    assert '无法判定' in result['notice']
    assert result['mode'] == 'demo'


# 9 月 20 日最小版的测试题集：每题应当命中指定知识点。
MVP_CASES = (
    ('求 lim(x→0) sin(x)/x', 'important-limits'),
    ('函数极限的 ε-δ 定义是什么', 'limit-definition'),
    ('讨论 x=1 处是否连续', 'continuity'),
    ('用定义求导数', 'derivative-definition'),
    ('复合函数求导漏乘内层导数怎么改', 'derivative-rules'),
    ('求单调区间和极值', 'derivative-application'),
)


@pytest.mark.parametrize('question,expected_id', MVP_CASES)
def test_mvp_case_set_retrieves_expected_point(question, expected_id):
    hits = knowledge.retrieve(question, top_k=3)
    assert hits, question
    assert expected_id in {hit.point.id for hit in hits}, (question, [hit.point.id for hit in hits])


def test_correct_statement_is_not_marked_wrong_by_keywords(monkeypatch):
    monkeypatch.setenv('AGENT_MODE', 'demo')
    result = diagnosis.step_feedback('可导与连续有什么关系？', '可导必连续。')
    assert result['flagged'] and result['verdict'] == 'unclear'


@pytest.mark.parametrize('value', ['nan', 'inf', '-1', '99999'])
def test_model_timeout_is_finite_and_below_frontend_budget(monkeypatch, value):
    monkeypatch.setenv('MODEL_TIMEOUT_SECONDS', value)
    monkeypatch.setenv('MODEL_MAX_TOKENS', 'nan')
    settings = load_settings()
    assert 1 <= settings.timeout <= 60
    assert settings.max_tokens == 900


def test_http_model_errors_do_not_echo_provider_body(monkeypatch):
    import httpx
    from backend.app.ai import llm
    monkeypatch.setenv('AGENT_MODE', 'live')
    monkeypatch.setenv('MODEL_BASE_URL', 'https://example.invalid/v1')
    monkeypatch.setenv('MODEL_API_KEY', 'synthetic-private-value')
    monkeypatch.setenv('MODEL_NAME', 'test-model')
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401, text='synthetic-private-value'))) as client:
        with pytest.raises(llm.ModelCallFailed) as exc:
            llm.chat([], load_settings(), client=client)
    assert '401' in str(exc.value)
    assert 'synthetic-private-value' not in str(exc.value)


def test_stream_network_failure_is_translated(monkeypatch):
    import httpx
    from backend.app.ai import llm
    monkeypatch.setenv('AGENT_MODE', 'live')
    monkeypatch.setenv('MODEL_BASE_URL', 'https://example.invalid/v1')
    monkeypatch.setenv('MODEL_API_KEY', 'synthetic-key')
    monkeypatch.setenv('MODEL_NAME', 'test-model')
    def unavailable(*args, **kwargs):
        raise httpx.ConnectError('synthetic-private-value')
    monkeypatch.setattr(httpx.Client, 'stream', unavailable)
    with pytest.raises(llm.ModelCallFailed) as exc:
        list(llm.chat_stream([], load_settings()))
    assert 'synthetic-private-value' not in str(exc.value)
