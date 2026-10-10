"""B 模块第五阶段路由（2026-10-10 续）：复习排期、班级掌握度聚合、多题切分。

范围：把长期记忆真正用起来（该复习什么）、把学情汇总到班级层（只读）、把拍照/语音的一段文本切成多道题。
与前面各阶段同样的取舍：单独成模块，避免每轮都改三方共用的 `service.py`。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from ..platform.auth import current_user, require_role
from ..platform.database import User, get_db
from . import class_insight, memory, question_split, review
from .config import AgentSettings, load_settings

phase5_router = APIRouter(tags=['agent-phase5'])

MAX_SPLIT_TEXT = 6000


class ReviewPlanInput(BaseModel):
    """复习排期：窗口天数与返回条数都受上限约束。"""

    days: int = Field(default=review.DEFAULT_HORIZON, ge=1, le=review.MAX_HORIZON)
    limit: int = Field(default=8, ge=1, le=review.MAX_ITEMS)
    topic: str | None = Field(default=None, max_length=40)


class SplitInput(BaseModel):
    """多题切分：文本来自拍照识别或语音转写，结果只是草稿。"""

    text: str = Field(min_length=1, max_length=MAX_SPLIT_TEXT)
    max_items: int = Field(default=question_split.MAX_ITEMS, ge=1, le=question_split.MAX_ITEMS)

    @field_validator('text')
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError('没有收到可切分的文本，请先拍照识别或语音转写。')
        return value.strip()


def _settings() -> AgentSettings:
    return load_settings()


@phase5_router.post('/review-plan')
def review_plan(data: ReviewPlanInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """今天该复习什么：按长期记忆的时间戳与掌握档位给出排期（规则，不调用模型）。"""
    state = memory.state(db, user.id)
    return review.plan(state, days=data.days, limit=data.limit, topic=data.topic)


@phase5_router.get('/class-insight/summary')
def class_insight_summary(user: User = Depends(require_role('teacher')), db: Session = Depends(get_db)):
    """教师名下班级的学情概览（只读，只含掌握状态与证据条数）。"""
    return class_insight.class_list(db, user.id)


@phase5_router.get('/class-insight')
def class_insight_detail(class_id: str, user: User = Depends(require_role('teacher')),
                         db: Session = Depends(get_db)):
    """单个班级的掌握度聚合；只能查自己名下的班级，越权按不存在处理。"""
    try:
        classroom = class_insight.own_class(db, class_id, user.id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return class_insight.overview(db, classroom)


@phase5_router.post('/recognize/split')
def recognize_split(data: SplitInput, user: User = Depends(current_user)):
    """把识别/转写得到的一段文本切成多道题（草稿，必须逐题确认）。"""
    return question_split.split(data.text, max_items=data.max_items)
