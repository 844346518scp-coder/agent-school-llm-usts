"""B 模块第四阶段路由（2026-10-10）：教学逻辑与知识讲解拆解。

范围（对应会议第 1、2 条里 B 负责的部分）：

- 刻意练习 / 苏格拉底追问：`practice.py` —— 计划、逐步评价、把作答记成长期记忆证据；
- 知识讲解拆解 → 树状图：`knowledge_tree.py` —— 章节与先修关系的结构化输出，供 A 端渲染。

与前三阶段同样的取舍：单独成模块，避免每轮都改三方共用的 `service.py`；
模式约定不变：`mode=demo` 表示本地规则派生，`live` 表示模型参与了文字生成，失败时降级并写 `notice`。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..platform.auth import current_user
from ..platform.database import User, get_db
from . import knowledge_tree, memory, practice
from .config import AgentSettings, load_settings

phase4_router = APIRouter(tags=['agent-phase4'])

MAX_ANSWER = 2000
MAX_QUESTION = 1000


class PracticePlanInput(BaseModel):
    """练习计划：给 point_id 就练指定知识点，否则按长期记忆挑最该练的。"""

    point_id: str | None = Field(default=None, max_length=64)
    topic: str | None = Field(default=None, max_length=40)


class PracticeAnswerInput(BaseModel):
    """某一步的作答：只评价这一步，并写入长期记忆证据。"""

    point_id: str = Field(min_length=1, max_length=64)
    step_index: int = Field(ge=1, le=practice.TOTAL_STEPS)
    answer: str = Field(min_length=1, max_length=MAX_ANSWER)


class ExplainInput(BaseModel):
    point_id: str = Field(min_length=1, max_length=64)
    question: str = Field(default='', max_length=MAX_QUESTION)


def _settings() -> AgentSettings:
    return load_settings()


@phase4_router.get('/knowledge/tree')
def knowledge_tree_endpoint(user: User = Depends(current_user)):
    """知识树：章节 → 知识点 → 先修/解锁关系，供 A 端画树状图。"""
    return knowledge_tree.tree()


@phase4_router.post('/knowledge/explain')
def knowledge_explain(data: ExplainInput, user: User = Depends(current_user)):
    """知识讲解拆解：把一个知识点拆成分支与叶子（live 模式下模型只重组讲解文字）。"""
    try:
        return knowledge_tree.explain(data.point_id, question=data.question, settings=_settings())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@phase4_router.post('/practice/plan')
def practice_plan(data: PracticePlanInput, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    """刻意练习计划：4 步苏格拉底式追问；公开计划不包含期望答案。"""
    state = memory.state(db, user.id)
    try:
        return practice.plan(state, point_id=data.point_id, topic=data.topic, settings=_settings())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@phase4_router.post('/practice/answer')
def practice_answer(data: PracticeAnswerInput, user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    """提交某一步的作答：返回反馈与追问，并把这一步记为长期记忆证据。

    记忆写入尽力而为（与问答/反馈一致）：失败不影响本次评价结果。
    """
    try:
        result = practice.answer(data.point_id, data.step_index, data.answer, settings=_settings())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        memory.record(db, user.id, 'practice', topic=result['point']['topic'],
                      point_id=result['point']['id'], verdict=result['band'],
                      weight=int(result['memory_weight']), excerpt=data.answer)
        remembered = True
    except Exception:  # noqa: BLE001 - 记忆写入失败不得影响评价结果
        db.rollback()
        remembered = False
    result['memory_recorded'] = remembered
    result['memory_note'] = ('已按长期记忆口径记一条证据。' if remembered
                             else '本次作答未能写入长期记忆，评价结果仍然有效。')
    return result
