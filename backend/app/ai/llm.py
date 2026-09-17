"""B 模块模型调用客户端（OpenAI 兼容的 Chat Completions，httpx 实现）。

只做三件事：拼请求、拿回复、把失败翻译成明确的异常，便于上层如实降级。
"""
from __future__ import annotations

import json
import re
from typing import Iterator

import httpx

from .config import AgentSettings

JSON_FENCE = re.compile(r'```(?:json)?\s*(.*?)```', re.S)


class ModelUnavailable(RuntimeError):
    """未配置模型（缺少 base_url / api_key / model），此时不应发起调用。"""


class ModelCallFailed(RuntimeError):
    """已发起调用但失败：网络错误、超时、非 2xx 或返回结构异常。"""


def endpoint(base_url: str) -> str:
    """允许填写 ``https://host/v1`` 或完整的 ``.../chat/completions``。"""
    base = (base_url or '').rstrip('/')
    if base.endswith('/chat/completions'):
        return base
    return f'{base}/chat/completions'


def extract_json(text: str) -> dict | None:
    """从模型输出里取出第一个 JSON 对象；失败返回 None（调用方保留规则结果）。"""
    if not text:
        return None
    candidates: list[str] = []
    fenced = JSON_FENCE.search(text)
    if fenced:
        candidates.append(fenced.group(1))
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(data, dict):
            return data
    return None


def _payload(messages: list[dict], settings: AgentSettings, *, stream: bool, model: str | None) -> dict:
    return {
        'model': model or settings.model,
        'messages': messages,
        'temperature': settings.temperature,
        'max_tokens': settings.max_tokens,
        'stream': stream,
    }


def _headers(settings: AgentSettings) -> dict:
    return {'Authorization': f'Bearer {settings.api_key}', 'Content-Type': 'application/json'}


def chat(
    messages: list[dict],
    settings: AgentSettings,
    *,
    model: str | None = None,
    client: httpx.Client | None = None,
) -> str:
    """同步一次性问答。失败时抛出 ModelUnavailable / ModelCallFailed。"""
    if not settings.model_ready:
        raise ModelUnavailable('未配置 MODEL_BASE_URL / MODEL_API_KEY / MODEL_NAME。')
    owns_client = client is None
    client = client or httpx.Client(timeout=settings.timeout)
    try:
        response = client.post(
            endpoint(settings.base_url),
            headers=_headers(settings),
            json=_payload(messages, settings, stream=False, model=model),
        )
    except httpx.HTTPError as exc:
        raise ModelCallFailed(f'请求模型失败：{exc}') from exc
    finally:
        if owns_client:
            client.close()
    if response.status_code >= 400:
        raise ModelCallFailed(f'模型返回 {response.status_code}：{response.text[:200]}')
    try:
        content = response.json()['choices'][0]['message']['content']
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise ModelCallFailed('模型返回结构无法解析。') from exc
    text = (content or '').strip()
    if not text:
        raise ModelCallFailed('模型返回内容为空。')
    return text


def chat_stream(
    messages: list[dict],
    settings: AgentSettings,
    *,
    model: str | None = None,
) -> Iterator[str]:
    """流式输出增量文本（SSE 的 data 行）。"""
    if not settings.model_ready:
        raise ModelUnavailable('未配置 MODEL_BASE_URL / MODEL_API_KEY / MODEL_NAME。')
    with httpx.Client(timeout=settings.timeout) as client:
        with client.stream(
            'POST',
            endpoint(settings.base_url),
            headers=_headers(settings),
            json=_payload(messages, settings, stream=True, model=model),
        ) as response:
            if response.status_code >= 400:
                body = response.read().decode('utf-8', 'replace')
                raise ModelCallFailed(f'模型返回 {response.status_code}：{body[:200]}')
            for raw_line in response.iter_lines():
                line = (raw_line or '').strip()
                if not line:
                    continue
                if line.startswith('data:'):
                    line = line[5:].strip()
                if line == '[DONE]':
                    return
                try:
                    chunk = json.loads(line)
                except ValueError:
                    continue
                try:
                    piece = chunk['choices'][0]['delta'].get('content')
                except (KeyError, IndexError, TypeError):
                    piece = None
                if piece:
                    yield piece
