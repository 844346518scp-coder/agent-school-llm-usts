"""B 模块超时降级与错误修正（9/25–27 补齐项）。

集中管理三件事，避免每个接口各写一套：

1. **降级策略**：模型不可用 / 超时 / 非 2xx / 返回结构异常 → 依次降级到规则结论、演示内容或明确的
   503，并把原因写进 `notice`；本模块只记录与重试，不改变上层“不得冒充模型输出”的既定行为。
2. **超时与重试**：只对“网络阶段超时”这一类可恢复失败重试一次（`MAX_ATTEMPTS=2`），
   其它失败不重试，避免把远端故障放大成雪崩。业务语义失败（如判定 unclear）永不重试。
3. **错误修正规则**：把模型返回的枚举/文本字段收敛到白名单，防止非法值流入前端（`coerce_enum`）。

统计与最近事件只存在进程内存（环形缓冲，最多 200 条），单请求流程不做任何持久化写入；
事件文本经过 `sanitize` 处理，不记录密钥、URL 与长 token。
"""
from __future__ import annotations

import re
from collections import Counter, deque
from datetime import datetime, timezone
from typing import Callable

from .llm import ModelCallFailed, ModelUnavailable

DEGRADE_CODES = {
    'model_unavailable': '未配置模型凭据，已按规则或演示内容返回',
    'model_timeout': '模型调用超时（网络阶段），已降级并建议稍后重试',
    'model_http_error': '模型返回非 2xx，已降级且不回显远端响应体',
    'model_bad_json': '模型未按约定返回 JSON，已保留规则结论',
    'model_empty': '模型返回空内容，已按失败处理',
    'retrieval_empty': '检索未命中课程资料，已如实说明而不是猜测',
    'memory_write_failed': '长期记忆写入失败，主流程不受影响',
    'math_unsupported': '数学工具不支持该写法，已说明工具边界',
    'voice_unavailable': '未配置语音服务，转写不可用（不返回编造文本）',
    'plot_unparsed': '未能从题目解析出函数表达式，只返回文字步骤',
}

RETRYABLE_CODES = ('model_timeout',)
RETRYABLE_MARKERS = ('超时', '网络连接失败', 'timeout')
MAX_ATTEMPTS = 2
RECENT_LIMIT = 200
SECRET_PATTERNS = (
    re.compile(r'https?://\S+'),
    re.compile(r'(?i)bearer\s+\S+'),
    re.compile(r'\b[A-Za-z0-9_\-]{24,}\b'),
)

_counter: Counter = Counter()
_recent: deque = deque(maxlen=RECENT_LIMIT)


def sanitize(text: str, limit: int = 200) -> str:
    """去掉 URL、Bearer 串与长 token，只保留可读的失败原因。"""
    cleaned = str(text or '')
    for pattern in SECRET_PATTERNS:
        cleaned = pattern.sub('[已隐去]', cleaned)
    return cleaned[:limit]


def classify(exc: BaseException | str) -> str:
    """把异常/文本归类到降级码，便于统计与前端展示。"""
    text = exc if isinstance(exc, str) else f'{type(exc).__name__}: {exc}'
    lowered = text.lower()
    if isinstance(exc, ModelUnavailable) or '未配置 model_' in text or 'ModelUnavailable' in text:
        return 'model_unavailable'
    if '超时' in text or 'timeout' in lowered or '网络连接失败' in text:
        return 'model_timeout'
    if 'HTTP ' in text or 'http ' in lowered:
        return 'model_http_error'
    if 'JSON' in text or 'json' in lowered:
        return 'model_bad_json'
    if '为空' in text:
        return 'model_empty'
    return 'model_http_error'


def is_retryable(code: str) -> bool:
    return code in RETRYABLE_CODES


def record(code: str, endpoint: str = '', detail: str = '') -> dict:
    """记录一次降级/错误事件（内存统计，不写数据库）。"""
    event = {
        'at': datetime.now(timezone.utc).isoformat(),
        'code': code if code in DEGRADE_CODES else 'model_http_error',
        'endpoint': endpoint,
        'detail': sanitize(detail),
        'meaning': DEGRADE_CODES.get(code, '未分类的降级'),
    }
    _counter[event['code']] += 1
    _recent.appendleft(event)
    return event


def call_model(factory: Callable[[], str], *, endpoint: str = '', attempts: int = MAX_ATTEMPTS) -> tuple[str, dict]:
    """调用模型并统一处理失败：可恢复失败重试一次，其余记录后原样抛出。

    ``factory`` 必须是**零参数可调用对象**，这样上层对 `chat` 的替换（测试或桩）依然生效。
    """
    attempt = 0
    while True:
        attempt += 1
        try:
            text = factory()
        except ModelUnavailable as exc:
            record('model_unavailable', endpoint, str(exc))
            raise
        except ModelCallFailed as exc:
            code = classify(exc)
            record(code, endpoint, str(exc))
            if is_retryable(code) and attempt < max(1, attempts):
                continue
            raise
        if not (text or '').strip():
            record('model_empty', endpoint, '模型返回空内容')
            raise ModelCallFailed('模型返回内容为空。')
        return text, {'attempts': attempt, 'code': None, 'endpoint': endpoint}


def coerce_enum(value, allowed, default):
    """错误修正：把模型给出的枚举值收敛到白名单，非法值一律回落到 default。"""
    text = str(value).strip() if value is not None else ''
    return text if text in allowed else default


def coerce_text(value, default: str = '', limit: int = 2000) -> str:
    """错误修正：模型字段只接受字符串，其它类型忽略，并限制长度。"""
    if value is None:
        return default
    if not isinstance(value, str):
        return default
    text = value.strip()
    return text[:limit] if text else default


def stats() -> dict:
    """给 /api/agent/diagnostics 用的统计快照。"""
    return {
        'total': sum(_counter.values()),
        'counters': dict(sorted(_counter.items())),
        'recent': list(_recent),
        'codes': DEGRADE_CODES,
        'retry_policy': {
            'max_attempts': MAX_ATTEMPTS,
            'retryable_codes': list(RETRYABLE_CODES),
            'note': '只对网络阶段超时重试一次；模型语义失败与业务判定不重试。',
        },
        'scope': '仅统计本进程自启动以来的降级事件，不持久化、不包含任何密钥或远端 URL。',
    }


def reset() -> None:
    """测试用：清空内存统计。"""
    _counter.clear()
    _recent.clear()
