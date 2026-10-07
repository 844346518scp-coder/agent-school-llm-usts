from dataclasses import replace
import json
import httpx
import pytest
from backend.app.ai import llm
from backend.app.ai.config import load_settings


def settings():
    return replace(load_settings(), mode='live', base_url='https://api.deepseek.com/v1',
                   api_key='synthetic-test-key', model='deepseek-flash', thinking='auto')


def test_deepseek_auto_and_other_providers():
    assert llm._payload([], settings(), stream=False, model=None)['thinking'] == {'type': 'disabled'}
    other = replace(settings(), base_url='https://api.deepseek.com.example.org/v1')
    assert 'thinking' not in llm._payload([], other, stream=False, model=None)
    assert llm._payload([], replace(other, thinking='enabled'), stream=True, model=None)['thinking']['type'] == 'enabled'


@pytest.mark.parametrize('content', ['', 'half a formula $$x='])
def test_truncated_reply_never_counts_as_success(content):
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={
        'choices': [{'message': {'content': content}, 'finish_reason': 'length'}]}))) as client:
        with pytest.raises(llm.ModelCallFailed, match='长度上限'):
            llm.chat([], settings(), client=client)


def test_normal_reply_and_no_reasoning_leak():
    def respond(request):
        assert json.loads(request.content)['thinking']['type'] == 'disabled'
        return httpx.Response(200, json={'choices': [{'message': {'content': '答案4', 'reasoning_content': 'private'}, 'finish_reason': 'stop'}]})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        assert llm.chat([], settings(), client=client) == '答案4'


def test_stream_truncation_is_reported(monkeypatch):
    real_client = httpx.Client
    transport = httpx.MockTransport(lambda r: httpx.Response(200, text='data: '+json.dumps({
        'choices': [{'delta': {'content': 'partial'}, 'finish_reason': 'length'}]})+'\n\ndata: [DONE]\n'))
    monkeypatch.setattr(llm.httpx, 'Client', lambda **kwargs: real_client(transport=transport))
    with pytest.raises(llm.ModelCallFailed, match='长度上限'):
        list(llm.chat_stream([], settings()))
