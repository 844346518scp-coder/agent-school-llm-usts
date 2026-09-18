"""B 模块（智能体）运行配置。

真实模型凭据只从环境变量或本地 .env 读取，不写进代码、不进入版本库。
默认行为：没有配置凭据时自动使用演示模式（demo），绝不把固定文案冒充模型输出。
"""
from __future__ import annotations

import os
import math
from dataclasses import dataclass

MODES = ('auto', 'demo', 'live')

KEY_ENV_NAMES = ('MODEL_BASE_URL', 'MODEL_API_KEY', 'MODEL_NAME')


def _number(name: str, default: float, low: float, high: float) -> float:
    raw = (os.getenv(name) or '').strip()
    if not raw:
        return default
    try:
        value = float(raw)
        return min(high, max(low, value)) if math.isfinite(value) else default
    except ValueError:
        return default


@dataclass(frozen=True)
class AgentSettings:
    """一次请求使用的智能体配置快照。"""

    mode: str
    base_url: str
    api_key: str
    model: str
    vision_model: str
    timeout: float
    temperature: float
    max_tokens: int
    top_k: int
    min_score: float

    @property
    def model_ready(self) -> bool:
        """是否具备调用真实模型的最小配置。"""
        return bool(self.base_url and self.api_key and self.model)

    @property
    def resolved_mode(self) -> str:
        """最终生效模式。

        live 缺少凭据时如实退回 demo，而不是返回看起来像模型输出的预设内容。
        """
        if self.mode == 'demo':
            return 'demo'
        return 'live' if self.model_ready else 'demo'


def load_settings() -> AgentSettings:
    """每次调用都重新读取环境变量，便于测试与热改配置。"""
    mode = (os.getenv('AGENT_MODE') or 'auto').strip().lower()
    if mode not in MODES:
        mode = 'auto'
    model = (os.getenv('MODEL_NAME') or '').strip()
    return AgentSettings(
        mode=mode,
        base_url=(os.getenv('MODEL_BASE_URL') or '').strip().rstrip('/'),
        api_key=(os.getenv('MODEL_API_KEY') or '').strip(),
        model=model,
        vision_model=(os.getenv('MODEL_VISION_NAME') or '').strip() or model,
        timeout=_number('MODEL_TIMEOUT_SECONDS', 30.0, 1, 60),
        temperature=_number('MODEL_TEMPERATURE', 0.3, 0, 2),
        max_tokens=int(_number('MODEL_MAX_TOKENS', 900, 1, 4096)),
        top_k=int(_number('AGENT_TOP_K', 4, 1, 8)),
        min_score=_number('AGENT_MIN_SCORE', 0.0, 0, 100),
    )
