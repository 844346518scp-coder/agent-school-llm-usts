"""Deterministic examples, never represented as a connected language model."""
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..platform.auth import current_user
from ..platform.database import Conversation, User, get_db

router = APIRouter(prefix='/api/conversations', tags=['agent'])


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


def serialize(item: Conversation):
    return {key: getattr(item, key) for key in ('id', 'question', 'answer', 'topic', 'favorite', 'created_at')} | {'mode': 'demo'}


@router.get('')
def history(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [serialize(item) for item in db.scalars(select(Conversation).where(Conversation.user_id == user.id).order_by(Conversation.created_at.desc()))]


@router.post('', status_code=201)
def ask(data: QuestionInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = Conversation(id=str(uuid4()), user_id=user.id, question=data.question, topic=data.topic,
                        answer=demo_reply(data.question, data.topic, user.role), favorite=False,
                        created_at=datetime.now(timezone.utc).isoformat())
    db.add(item)
    db.commit()
    return serialize(item)


@router.patch('/{conversation_id}')
def favorite(conversation_id: str, data: FavoriteInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = db.get(Conversation, conversation_id)
    if not item or item.user_id != user.id:
        raise HTTPException(404, '记录不存在。')
    item.favorite = data.favorite
    db.commit()
    return serialize(item)
