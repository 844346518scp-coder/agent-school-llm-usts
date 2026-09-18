"""B 模块（智能体与教学逻辑）。

职责：分领域答疑、课程检索与引用、基础诊断、按接口接入真实模型。
原则：未配置真实模型时只返回预设演示内容并如实标注 ``mode='demo'``；
      模型调用失败时降级到演示内容并给出 ``notice``，绝不把演示回复冒充模型输出。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Iterator, Literal
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..platform.auth import current_user
from ..platform.database import Conversation, User, get_db
from . import diagnosis as diagnosis_service
from . import knowledge, prompts
from .config import load_settings
from .llm import ModelCallFailed, ModelUnavailable, chat, chat_stream, extract_json

router = APIRouter(prefix='/api/conversations', tags=['agent'])
agent_router = APIRouter(prefix='/api/agent', tags=['agent-core'])

AGENT_VERSION = '0.2.0'

DEMO_MARKERS = ('未连接真实模型', '固定例题演示', '未评分', '教学设计示例')


class QuestionInput(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    topic: Literal['函数与极限', '导数与微分', '费曼练习', '教学设计'] = '函数与极限'

    @field_validator('question')
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError('请输入问题')
        return value.strip()


class FavoriteInput(BaseModel):
    favorite: bool


class AskInput(BaseModel):
    """无副作用的试问接口入参（不写入学习记录）。"""

    question: str = Field(min_length=1, max_length=2000)
    topic: str = Field(default='函数与极限', max_length=40)
    role: Literal['student', 'teacher'] = 'student'

    @field_validator('question')
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError('请输入问题')
        return value.strip()


class DiagnosisInput(BaseModel):
    question: str = Field(default='', max_length=4000)
    answer: str = Field(default='', max_length=4000)
    wrong_points: list[str] = Field(default_factory=list)
    topic: str | None = Field(default=None, max_length=40)


class StepFeedbackInput(BaseModel):
    """步骤反馈：只判断学生本次提交的这一步。"""

    question: str = Field(min_length=1, max_length=2000)
    step: str = Field(min_length=1, max_length=2000)
    steps: list[str] = Field(default_factory=list)
    topic: str = Field(default='函数与极限', max_length=40)


class RecognizeInput(BaseModel):
    image_base64: str = Field(min_length=16)
    media_type: str = Field(default='image/png', max_length=60)
    hint: str = Field(default='', max_length=200)


def demo_reply(question: str, topic: str, role: str) -> str:
    if role == 'teacher':
        return ('【教学设计示例 · 未连接真实模型】\n\n可以先围绕“概念 → 例题 → 迁移”组织一节微课：\n'
                '1. 用曲线在一点的切线，引入瞬时变化率。\n2. 让学生解释割线斜率为什么要取极限。\n'
                '3. 以 $f(x)=x^2$ 为例，用定义推导 $f\'(x)=2x$。\n'
                '4. 用一道变式题收集反馈，再决定是否补讲。\n\n'
                '这是固定教学示例，并未对你的具体要求进行模型分析。你可以前往“作业管理”发布自己的练习。')
    if topic == '费曼练习':
        return ('【费曼练习示例 · 未评分】\n\n试着把“导数”讲给第一次接触它的同学：\n'
                '① 它描述什么？\n② 割线与切线有什么关系？\n③ 生活中有哪些瞬时变化的例子？\n\n'
                '参考表达：导数描述函数在某一点的瞬时变化率，也对应曲线在该点的切线斜率。\n'
                '目前只展示固定追问，还不能评价你的讲解质量。')
    if 'sin' in question.lower() and ('极限' in question or 'lim' in question.lower()):
        return ('【固定例题演示】\n\n你可以先看这个经典极限：\n'
                '$$\\lim_{x\\to 0}\\frac{\\sin x}{x}=1$$\n'
                '这里 $x$ 使用弧度制。\n\n'
                '1. 直接代入会得到 $0/0$，它是不定式，不是答案。\n'
                '2. 当 $0<x<\\pi/2$ 时，有 $\\cos x<\\sin x/x<1$。\n'
                '3. 两侧都趋于 1；再结合偶函数性质，可得双侧极限为 1。\n\n'
                '试一试：$\\lim_{x\\to 0}\\sin(3x)/x$ 是多少？\n'
                '这段回复是预设例题说明，不是对任意输入的自动诊断。')
    if 'x^2' in question or 'x²' in question or '导数' in question:
        return ('【固定例题演示】\n\n以 $f(x)=x^2$ 为例，从定义理解导数：\n'
                '$$f\'(x)=\\lim_{h\\to0}\\frac{(x+h)^2-x^2}{h}=\\lim_{h\\to0}(2x+h)=2x$$\n'
                '1. 写出函数增量 $(x+h)^2-x^2$。\n2. 展开并约去 $h$，注意取极限前 $h\\ne0$。\n'
                '3. 令 $h$ 趋近于 0，得到 $2x$。\n\n'
                '你能解释为什么不能在约分前直接令 $h=0$ 吗？\n'
                '这是固定例题，尚未接入自动解题或数学工具校验。')
    return ('【交互演示 · 未连接真实模型】\n\n你的问题已保存。当前版本先验证提问、反馈和历史记录的完整流程，'
            '还不能生成针对这个问题的解答。\n\n'
            '可以点击示例问题，体验“求 sin(x)/x 的极限”或“用定义求 x² 的导数”的预设讲解。\n'
            '未来将在这里接入课程检索、分层提示与步骤诊断。')


def detect_mode(answer: str) -> str:
    """历史记录只存了答案文本，这里按演示标记反推来源，避免误报 live。"""
    text = answer or ''
    if text.startswith('【回复来源：模型】'):
        return 'live'
    if text.startswith('【回复来源：演示】'):
        return 'demo'
    return 'demo' if any(marker in text for marker in DEMO_MARKERS) else 'live'


def _safe_host(base_url: str) -> str | None:
    if not base_url:
        return None
    try:
        parts = urlsplit(base_url)
        return f'{parts.scheme}://{parts.hostname}' if parts.hostname else None
    except ValueError:
        return None


def retrieve_chunks(question: str, topic: str | None = None) -> list:
    """课程检索：返回可引用的资料片段（demo 模式下同样可用）。"""
    settings = load_settings()
    return knowledge.retrieve(question, topic=topic, top_k=settings.top_k, min_score=settings.min_score)


def compose_answer(question: str, topic: str, role: str, mode: str, chunks) -> tuple[str, str, str | None]:
    """返回 (answer, mode, notice)。demo 分支严格使用预设文案，保证可测且不误导。"""
    if mode != 'live':
        answer = demo_reply(question, topic, role)
        if chunks:
            # 引用是真实检索结果，与“未连接真实模型”的说明分开，避免读者误以为答案已由资料生成。
            answer += '\n\n本轮检索到的课程资料（未经模型解读）\n' + '\n'.join(prompts.reference_lines(chunks))
        return answer, 'demo', None

    settings = load_settings()
    try:
        body = chat(prompts.build_qa_messages(question, topic, chunks, role), settings)
    except ModelUnavailable as exc:
        return demo_reply(question, topic, role), 'demo', f'未配置真实模型，已返回演示内容（{exc}）。'
    except ModelCallFailed as exc:
        return demo_reply(question, topic, role), 'demo', f'真实模型调用失败，已降级为演示内容（{exc}）。'
    references = prompts.format_references(chunks)
    return (body + references) if references else body, 'live', None


def serialize(item: Conversation, extra: dict | None = None):
    data = {key: getattr(item, key) for key in ('id', 'question', 'answer', 'topic', 'favorite', 'created_at')}
    data |= {'mode': detect_mode(item.answer)}
    if extra:
        data |= extra
    return data


def _references(chunks) -> list[dict]:
    return [chunk.as_dict(index) for index, chunk in enumerate(chunks, 1)]


@router.get('')
def history(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [
        serialize(item)
        for item in db.scalars(
            select(Conversation).where(Conversation.user_id == user.id).order_by(Conversation.created_at.desc())
        )
    ]


@router.post('', status_code=201)
def ask(data: QuestionInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    settings = load_settings()
    chunks = retrieve_chunks(data.question, data.topic)
    answer, mode, notice = compose_answer(data.question, data.topic, user.role, settings.resolved_mode, chunks)
    if notice:
        answer = f'【调用提示】{notice}\n\n{answer}'  # Preserve fallback notice after refresh/relogin.
    answer = ('【回复来源：模型】\n' if mode == 'live' else '【回复来源：演示】\n') + answer
    item = Conversation(id=str(uuid4()), user_id=user.id, question=data.question, topic=data.topic,
                        answer=answer, favorite=False,
                        created_at=datetime.now(timezone.utc).isoformat())
    db.add(item)
    db.commit()
    return serialize(item, {'mode': mode, 'notice': notice, 'references': _references(chunks)})


@router.patch('/{conversation_id}')
def update_conversation(conversation_id: str, data: FavoriteInput,
                        user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = db.get(Conversation, conversation_id)
    if item is None or item.user_id != user.id:
        raise HTTPException(status_code=404, detail='记录不存在')
    item.favorite = data.favorite
    db.commit()
    return serialize(item)


@agent_router.get('/status')
def agent_status():
    """能力探针：只暴露“是否可用”，不返回任何密钥。"""
    settings = load_settings()
    return {
        'version': AGENT_VERSION,
        'mode': settings.resolved_mode,
        'requested_mode': settings.mode,
        'model': {
            'ready': settings.model_ready,
            'name': settings.model or None,
            'vision_name': settings.vision_model or None,
            'endpoint': _safe_host(settings.base_url),
            'timeout_seconds': settings.timeout,
        },
        'knowledge': knowledge.stats(),
        'capabilities': {
            'qa': True,
            'qa_stream': settings.resolved_mode == 'live',
            'references': True,
            'diagnosis': True,
            'recognize': settings.resolved_mode == 'live',
            'memory': False,
            'recommendation': True,
        },
        'notes': [
            'demo 模式只返回预设演示内容，不会伪造模型输出。',
            'memory（长期记忆）与异步任务仍在规划中。',
        ],
    }


@agent_router.post('/ask')
def quick_ask(data: AskInput, user: User = Depends(current_user)):
    """试问接口：与正式问答同一套流程，但不写入学习记录，便于联调与评测。"""
    settings = load_settings()
    chunks = retrieve_chunks(data.question, data.topic)
    answer, mode, notice = compose_answer(data.question, data.topic, data.role, settings.resolved_mode, chunks)
    return {
        'question': data.question,
        'topic': data.topic,
        'role': data.role,
        'answer': answer,
        'mode': mode,
        'notice': notice,
        'references': _references(chunks),
        'persisted': False,
    }


def _sse(payload: dict) -> str:
    return f'data: {json.dumps(payload, ensure_ascii=False)}\n\n'


@agent_router.post('/ask/stream')
def stream_ask(data: AskInput, user: User = Depends(current_user)):
    """SSE 流式问答：事件类型 meta / delta / done / fallback。"""
    settings = load_settings()
    chunks = retrieve_chunks(data.question, data.topic)
    references = _references(chunks)

    def events() -> Iterator[str]:
        yield _sse({'type': 'meta', 'mode': settings.resolved_mode, 'references': references})

        if settings.resolved_mode != 'live':
            answer, mode, notice = compose_answer(data.question, data.topic, data.role, 'demo', chunks)
            yield _sse({'type': 'delta', 'text': answer})
            yield _sse({'type': 'done', 'mode': mode, 'notice': notice})
            return

        messages = prompts.build_qa_messages(data.question, data.topic, chunks, data.role)
        try:
            produced = False
            for piece in chat_stream(messages, settings):
                produced = True
                yield _sse({'type': 'delta', 'text': piece})
            if not produced:
                raise ModelCallFailed('模型未返回任何内容。')
        except (ModelUnavailable, ModelCallFailed) as exc:
            answer, mode, notice = compose_answer(data.question, data.topic, data.role, 'demo', chunks)
            yield _sse({'type': 'fallback', 'mode': 'demo', 'replace': True, 'notice': f'流式调用失败，已降级（{exc}）。'})
            yield _sse({'type': 'delta', 'text': answer})
            yield _sse({'type': 'done', 'mode': mode, 'notice': notice})
            return

        tail = prompts.format_references(chunks)
        if tail:
            yield _sse({'type': 'delta', 'text': tail})
        yield _sse({'type': 'done', 'mode': 'live', 'notice': None})

    return StreamingResponse(events(), media_type='text/event-stream', headers={'Cache-Control': 'no-store'})


@agent_router.post('/diagnosis')
def run_diagnosis(data: DiagnosisInput, user: User = Depends(current_user)):
    """基础诊断：规则给出薄弱知识点与变式练习，模型仅润色学情总结。"""
    return diagnosis_service.diagnose(
        question=data.question,
        answer=data.answer,
        wrong_points=data.wrong_points,
        topic=data.topic,
    )


@agent_router.post('/feedback')
def check_step(data: StepFeedbackInput, user: User = Depends(current_user)):
    """步骤反馈：请求 → 判断这一步 → 提示与追问，不返回完整答案。"""
    return diagnosis_service.step_feedback(
        question=data.question,
        step=data.step,
        steps=data.steps,
        topic=data.topic,
    )


@agent_router.post('/recognize')
def recognize_question(data: RecognizeInput, user: User = Depends(current_user)):
    """拍照识别：仅做题目转录。未配置真实模型时如实报 503，不返回编造结果。"""
    settings = load_settings()
    if settings.resolved_mode != 'live':
        raise HTTPException(
            status_code=503,
            detail='未配置真实模型（MODEL_BASE_URL / MODEL_API_KEY / MODEL_NAME），识别功能不可用；'
            '演示模式不会返回编造的识别结果。',
        )
    data_url = f'data:{data.media_type};base64,{data.image_base64}'
    try:
        raw = chat(prompts.build_recognize_messages(data_url, data.hint), settings, model=settings.vision_model)
    except ModelUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ModelCallFailed as exc:
        raise HTTPException(status_code=502, detail=f'识别调用失败：{exc}') from exc

    parsed = extract_json(raw)
    if parsed is None:
        text = raw
        warnings = ['模型未按 JSON 格式返回，已原样透传。']
        confidence = None
    else:
        text = str(parsed.get('text') or '').strip()
        warnings = list(parsed.get('warnings') or [])
        confidence = parsed.get('confidence')
    # 识别只给草稿，必须由学生确认后再进入问答/保存（确认动作复用 POST /api/conversations）。
    return {
        'mode': 'live',
        'text': text,
        'confidence': confidence,
        'warnings': warnings,
        'requires_confirmation': True,
        'suggested_topic': knowledge.suggest_topic(text),
        'confirm_endpoint': '/api/conversations',
    }
