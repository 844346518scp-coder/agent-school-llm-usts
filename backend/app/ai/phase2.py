"""B 模块第二阶段接口：长期记忆、推荐练习、评价、总结复习、资源检索。

单独成模块的原因：`service.py` 是三方共用的路由入口，第二阶段接口独立后，
各角色的改动更不容易互相冲突。本模块只依赖 knowledge / memory / insight，
不反向导入 service，避免循环依赖。

模式约定与第一阶段一致：`mode=demo` 表示结果来自本地规则与预设内容，
`live` 表示模型参与了生成；模型不可用时一律降级为规则结果并在 `notice` 说明。
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..platform.auth import current_user
from ..platform.database import Conversation, User, get_db
from . import insight, knowledge, memory

phase2_router = APIRouter(tags=['agent-phase2'])

MAX_LIMIT = 8
DEFAULT_SUMMARY_DAYS = 7
MAX_SUMMARY_DAYS = 90
SUMMARY_SCAN_LIMIT = 200


class RecommendInput(BaseModel):
    topic: str | None = Field(default=None, max_length=40)
    limit: int = Field(default=3, ge=1, le=MAX_LIMIT)
    exclude: list[str] = Field(default_factory=list)


class ReviewInput(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    topic: str | None = Field(default=None, max_length=40)
    kind: Literal['feynman', 'self'] = 'feynman'


class SummaryInput(BaseModel):
    days: int = Field(default=DEFAULT_SUMMARY_DAYS, ge=1, le=MAX_SUMMARY_DAYS)
    topic: str | None = Field(default=None, max_length=40)


class ResourceSearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    topic: str | None = Field(default=None, max_length=40)
    limit: int = Field(default=5, ge=1, le=20)


def _state(db: Session, user: User) -> dict:
    return memory.state(db, user.id)


@phase2_router.get('/memory')
def read_memory(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """读取本人长期记忆（各知识点掌握度与证据数量）。"""
    state = _state(db, user)
    state['privacy'] = '该记忆只属于当前账号，可随时通过 DELETE /api/agent/memory 清空。'
    return state


@phase2_router.delete('/memory')
def clear_memory(point_id: str | None = None, user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    """清空本人长期记忆；传 point_id 时只清空该知识点的记录。"""
    removed = memory.clear(db, user.id, point_id=point_id)
    return {'removed': removed, 'point_id': point_id, 'scope': 'own_account'}


@phase2_router.post('/recommend')
def recommend_practice(data: RecommendInput, user: User = Depends(current_user),
                       db: Session = Depends(get_db)):
    """按长期记忆推荐练习；把上一批的 point_id 放进 exclude 即可“换一批”。"""
    return insight.recommend(_state(db, user), topic=data.topic, limit=data.limit, exclude=data.exclude)


@phase2_router.post('/review')
def review_answer(data: ReviewInput, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    """评价（费曼复述 / 自评）：给出覆盖率评价，并把结果写入长期记忆。"""
    result = insight.evaluate(data.text, topic=data.topic, kind=data.kind)
    point = result.get('point') or {}
    if point.get('id'):
        memory.record(db, user.id, 'review',
                      topic=point.get('topic') or data.topic,
                      point_id=point.get('id'),
                      verdict=result.get('band'),
                      weight=int(result.get('memory_weight') or 0),
                      excerpt=data.text)
    return result


@phase2_router.post('/summary')
def study_summary(data: SummaryInput, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    """阶段总结复习：汇总统计窗口内的提问记录与长期记忆。"""
    rows = db.execute(
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(Conversation.created_at.desc())
        .limit(SUMMARY_SCAN_LIMIT)
    ).scalars().all()
    conversations = [
        {
            'id': row.id,
            'topic': row.topic,
            'created_at': row.created_at,
            'question': row.question,
            'favorite': row.favorite,
        }
        for row in rows
    ]
    return insight.summarize(_state(db, user), conversations, days=data.days, topic=data.topic)


@phase2_router.post('/resources/search')
def search_resources_endpoint(data: ResourceSearchInput, user: User = Depends(current_user)):
    """资源检索：概念 / 例题 / 练习 / 资料条目，带出处与复核状态。"""
    items = knowledge.search_resources(data.query, topic=data.topic, limit=data.limit)
    return {
        'query': data.query,
        'topic': knowledge.normalize_topic(data.topic),
        'items': items,
        'total': len(items),
        'note': '资源库当前由课程知识点派生（概念/例题/练习三类）并附少量资料条目，外部课件与视频待补充；'
                '条目 verified=false 表示待课程资料复核。',
    }
