"""B 模块第三阶段路由（9/25–27 交付）：分层提示、图形批注、语音适配、数学工具、准确性评测、教师纠错、降级统计。

与 `phase2.py` 同样的取舍：单独成模块，避免每轮都改三方共用的 `service.py`；
本模块只依赖 ai 包内模块，不反向导入 service，防止循环依赖。

模式约定与第一、二阶段一致：`mode=demo` 表示结果来自本地规则与预设内容，`live` 表示模型参与了生成；
模型不可用时一律降级为规则结果并在 `notice` 说明原因，绝不把演示内容冒充模型输出。
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from ..platform.auth import current_user, require_role
from ..platform.database import User, get_db
from . import corrections, evaluation, hints, mathcheck, plotting, resilience, voice
from .config import AgentSettings, load_settings
from .llm import ModelCallFailed

phase3_router = APIRouter(tags=['agent-phase3'])

MAX_HINT_QUESTION = 1000
MAX_EXPR = 200


class HintInput(BaseModel):
    """分层提示：level 1/2/3 分别为概念、方法、关键步骤。"""

    question: str = Field(min_length=1, max_length=MAX_HINT_QUESTION)
    level: int = Field(default=1, ge=1, le=3)
    topic: str | None = Field(default=None, max_length=40)

    @field_validator('question')
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError('请输入问题')
        return value.strip()


class PlotInput(BaseModel):
    """图形批注：可给题干、也可直接给函数表达式；圆用 cx/cy/radius。"""

    question: str = Field(default='', max_length=1000)
    expr: str | None = Field(default=None, max_length=MAX_EXPR)
    at: float | None = None
    topic: str | None = Field(default=None, max_length=40)
    x_min: float = Field(default=-6.0, ge=-1e4, le=1e4)
    x_max: float = Field(default=6.0, ge=-1e4, le=1e4)
    samples: int = Field(default=49, ge=2, le=241)
    cx: float | None = None
    cy: float | None = None
    radius: float | None = Field(default=None, gt=0, le=1e4)


class MathCheckInput(BaseModel):
    """数学工具：表达式求值 / 符号求导 / 极限探测 / 等价性校验 / 指定点取值核对。"""

    expr: str = Field(min_length=1, max_length=MAX_EXPR)
    x: float | None = None
    expected: float | None = None
    compare_expr: str | None = Field(default=None, max_length=MAX_EXPR)
    x0: float | None = None


class VoiceInput(BaseModel):
    """语音转写适配：提交音频后返回“题目草稿 + 术语纠错”，必须由学生确认。"""

    audio_base64: str = Field(min_length=16, max_length=40_000_000)
    media_type: str = Field(default='audio/webm', max_length=60)
    language: str = Field(default='zh', max_length=10)
    duration_seconds: float | None = Field(default=None, ge=0, le=600)
    hint: str = Field(default='', max_length=200)


class EvaluateInput(BaseModel):
    """准确性评测：不传 suites 就全部跑。"""

    suites: list[str] = Field(default_factory=list)


class CorrectionInput(BaseModel):
    """教师纠错：追加补偿证据修正判断与状态（原始证据保留）。"""

    student_id: str = Field(min_length=1, max_length=64)
    point_id: str = Field(min_length=1, max_length=64)
    corrected: Literal['correct', 'incorrect', 'unclear']
    reason: str = Field(min_length=1, max_length=300)
    weight: int | None = Field(default=None, ge=-3, le=3)
    origin: str | None = Field(default=None, max_length=200)

    @field_validator('reason')
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError('必须填写纠错理由')
        return value.strip()


def _settings() -> AgentSettings:
    return load_settings()


@phase3_router.post('/hint')
def build_hint(data: HintInput, user: User = Depends(current_user)):
    """分层提示：按层级返回概念/方法/关键步骤提示，任何层级都不给最终答案。"""
    return hints.build(data.question, level=data.level, topic=data.topic, settings=_settings())


@phase3_router.post('/plot/annotate')
def plot_annotate(data: PlotInput, user: User = Depends(current_user)):
    """图形批注：返回采样坐标、关键点与分步讲解，供 A 端画布渲染。"""
    circle = None
    if data.radius is not None:
        circle = {'cx': data.cx or 0.0, 'cy': data.cy or 0.0, 'radius': data.radius}
    return plotting.annotate(
        data.question, topic=data.topic, expr=data.expr, at=data.at,
        x_min=data.x_min, x_max=data.x_max, samples=data.samples,
        circle=circle, settings=_settings(),
    )


@phase3_router.post('/math/check')
def math_check(data: MathCheckInput, user: User = Depends(current_user)):
    """数学工具：把可复核的计算结果直接返回给前端（不调用模型）。"""
    try:
        node = mathcheck.parse(data.expr)
    except mathcheck.MathError as exc:
        raise HTTPException(status_code=422, detail=f'表达式无法解析：{exc}') from exc

    payload = {
        'mode': 'demo',
        'notice': None,
        'expr': mathcheck.to_text(mathcheck.simplify(node)),
        'latex': mathcheck.to_latex(node),
        'variables': sorted(mathcheck.variables(node)),
        'derivative': mathcheck.derivative_report(data.expr),
        'method': '本地数学工具（零依赖），结果可被数值取样复核',
        'limitations': '极限与等价性为数值证据；多变量、积分、级数暂不支持。',
    }
    if data.x is not None:
        value = mathcheck.safe_value(data.expr, data.x)
        payload['value'] = {'x': data.x, 'value': value}
        if data.expected is not None:
            payload['value_check'] = mathcheck.check_value(data.expr, data.x, data.expected)
    if data.x0 is not None:
        payload['limit'] = mathcheck.probe_limit(data.expr, data.x0)
    if data.compare_expr:
        payload['equivalence'] = mathcheck.equivalent(data.expr, data.compare_expr)
    return payload


@phase3_router.get('/voice/status')
def voice_status():
    """语音能力探针：只说是否可用与凭据来源，不返回密钥。"""
    return voice.status(_settings())


@phase3_router.post('/voice/transcribe')
def voice_transcribe(data: VoiceInput, user: User = Depends(current_user)):
    """语音转写：只给草稿（requires_confirmation=true）；未配置语音服务时 503，不返回编造文本。"""
    settings = _settings()
    try:
        checked = voice.check_audio(data.audio_base64, data.media_type, data.duration_seconds)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        result = voice.transcribe(checked, settings, language=data.language, hint=data.hint)
    except voice.VoiceUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail=f'{exc} 可改用浏览器原生语音输入（见 GET /api/agent/voice/status 的 browser_fallback）。',
        ) from exc
    except ModelCallFailed as exc:
        raise HTTPException(status_code=502, detail=f'语音服务调用失败：{exc}') from exc
    result['confirm_endpoint'] = '/api/conversations'
    return result


@phase3_router.get('/diagnostics')
def diagnostics(user: User = Depends(current_user)):
    """降级与错误统计：只返回本进程内存统计，已过滤 URL 与长 token。"""
    stats = resilience.stats()
    stats['math_tools'] = mathcheck.capabilities()
    stats['voice'] = voice.status(_settings())
    return stats


@phase3_router.post('/evaluate')
def run_evaluation(data: EvaluateInput, user: User = Depends(require_role('teacher'))):
    """准确性评测（教师）：运行内置评测集并返回逐条结果。"""
    try:
        return evaluation.run(tuple(data.suites) if data.suites else None)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@phase3_router.post('/corrections')
def create_correction(data: CorrectionInput, user: User = Depends(require_role('teacher')),
                      db: Session = Depends(get_db)):
    """教师纠错：追加补偿证据并返回修正后的知识状态。

    这里用 get_db 而不是 write_db：与 memory.py 一致，B 自有表不走平台写锁；
    同时避免 BEGIN IMMEDIATE 持锁期间去建表（SQLite 会直接报 database is locked）。
    """
    try:
        return corrections.apply(db, teacher_id=user.id, student_id=data.student_id,
                                 point_id=data.point_id, corrected=data.corrected,
                                 reason=data.reason, weight=data.weight, origin=data.origin)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@phase3_router.get('/corrections')
def list_corrections(limit: int = 50, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """纠错记录：教师查自己发出的，学生查与自己相关的。"""
    if user.role == 'teacher':
        rows = corrections.history(db, teacher_id=user.id, limit=limit)
    else:
        rows = corrections.history(db, student_id=user.id, limit=limit)
    return {
        'items': corrections.describe(rows),
        'total': len(rows),
        'scope': 'teacher_self' if user.role == 'teacher' else 'own_account',
        'note': '纠错以补偿证据追加，原始学习证据保留，便于复核。',
    }
