"""B 模块教师纠错（模块衔接图中的「教师纠错：B 修正判断与状态」）。

语义与边界：

- 学生端呈现的“判断/掌握状态”来自 `ai_learning_events` 的可核对证据；教师复核后 **不删除** 原始证据，
  而是追加一条 `teacher_correction` 补偿证据，掌握度随之重算 —— 历史可追溯，谁在什么时候改了什么一目了然。
- 存储沿用长期记忆的做法：**独立 MetaData + 惰性建表**，不加入 `platform.database.Base`
  （原因见 `memory.py`：platform 的 schema v3 校验会让既有库启动报 Incomplete schema）。
- 权限：只允许教师账号对自己班级的学生纠错 —— 该判断在路由层用 `require_role('teacher')` 完成，
  本模块只负责“写补偿证据 + 记账 + 返回新状态”，不重复实现权限逻辑。
- 学生只能看与自己相关的纠错记录，不能修改。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence
from uuid import uuid4

from sqlalchemy import Column, Integer, MetaData, String, Table, insert, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from . import knowledge, memory
from ..platform.database import engine as default_engine

CORRECTION_METADATA = MetaData()

CORRECTIONS = Table(
    'ai_corrections',
    CORRECTION_METADATA,
    Column('id', String(36), primary_key=True),
    Column('student_id', String(64), nullable=False, index=True),
    Column('teacher_id', String(64), nullable=False, index=True),
    Column('point_id', String(64), nullable=False),
    Column('corrected', String(16), nullable=False),
    Column('weight', Integer, nullable=False),
    Column('reason', String(300), nullable=False),
    Column('origin', String(200)),
    Column('created_at', String(40), nullable=False),
)

VALID_VERDICTS = ('correct', 'incorrect', 'unclear')
DEFAULT_WEIGHTS = {'correct': 2, 'incorrect': -2, 'unclear': 0}
MAX_ABS_WEIGHT = 3
MAX_HISTORY = 200

_READY = False


def ensure_table(engine: Engine | None = None) -> None:
    global _READY
    if _READY:
        return
    CORRECTION_METADATA.create_all(engine or default_engine, checkfirst=True)
    _READY = True


def reset_ready_flag() -> None:
    """测试用：允许换引擎后重新建表。"""
    global _READY
    _READY = False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def weight_for(corrected: str, weight: int | None = None) -> int:
    """纠正权重：默认 correct=+2 / incorrect=-2 / unclear=0，可用 weight 覆盖但受 -3..3 限制。"""
    base = DEFAULT_WEIGHTS.get(corrected, 0)
    if weight is None:
        return base
    return max(-MAX_ABS_WEIGHT, min(MAX_ABS_WEIGHT, int(weight)))


def apply(db: Session, *, teacher_id: str, student_id: str, point_id: str, corrected: str,
          reason: str, weight: int | None = None, origin: str | None = None,
          engine: Engine | None = None) -> dict:
    """写入一次教师纠错，并追加补偿证据；返回纠错记录、该知识点新状态与整体记忆快照。"""
    if corrected not in VALID_VERDICTS:
        raise ValueError(f'corrected 只能是 {"/".join(VALID_VERDICTS)}')
    point = knowledge.get_point(point_id)
    if point is None:
        raise ValueError(f'未知知识点：{point_id}')
    text = (reason or '').strip()
    if not text:
        raise ValueError('必须填写纠错理由，便于教师之间复核')

    ensure_table(engine)
    before = memory.state(db, student_id, engine=engine)
    previous = memory.point_mastery(before, point_id)

    row = {
        'id': str(uuid4()),
        'student_id': student_id,
        'teacher_id': teacher_id,
        'point_id': point_id,
        'corrected': corrected,
        'weight': weight_for(corrected, weight),
        'reason': text[:300],
        'origin': (origin or '')[:200] or None,
        'created_at': _now(),
    }
    db.execute(insert(CORRECTIONS).values(**row))
    db.commit()

    memory.record(db, student_id, 'teacher_correction', topic=point.topic, point_id=point_id,
                  verdict=corrected, weight=row['weight'],
                  excerpt=f'教师纠错（{teacher_id}）：{text[:120]}', engine=engine)

    after = memory.state(db, student_id, engine=engine)
    return {
        'correction': dict(row),
        'point': {'id': point.id, 'title': point.title, 'topic': point.topic},
        'before': previous,
        'after': memory.point_mastery(after, point_id),
        'state': after,
        'note': '原始学习证据未删除；纠错以补偿证据追加，掌握度按同一口径重算。',
    }


def history(db: Session, *, teacher_id: str | None = None, student_id: str | None = None,
            limit: int = 50, engine: Engine | None = None) -> list[dict]:
    """查询纠错记录：教师查自己发出的，学生查与自己相关的。"""
    ensure_table(engine)
    statement = select(CORRECTIONS)
    if teacher_id:
        statement = statement.where(CORRECTIONS.c.teacher_id == teacher_id)
    if student_id:
        statement = statement.where(CORRECTIONS.c.student_id == student_id)
    statement = statement.order_by(CORRECTIONS.c.created_at.desc()).limit(max(1, min(MAX_HISTORY, limit)))
    rows = db.execute(statement).mappings().all()
    return [dict(row) for row in rows]


def describe(rows: Sequence[dict]) -> list[dict]:
    """给前端补上知识点标题，避免前端再查一次课程库。"""
    described: list[dict] = []
    for row in rows:
        point = knowledge.get_point(row.get('point_id') or '')
        item = dict(row)
        item['point_title'] = point.title if point else None
        item['topic'] = point.topic if point else None
        described.append(item)
    return described


def stats(db: Session, engine: Engine | None = None) -> dict:
    """纠错总量（用于教师端与学生端的提示，不做权限判断）。"""
    ensure_table(engine)
    total = len(db.execute(select(CORRECTIONS.c.id)).all())
    return {
        'total': total,
        'valid_verdicts': list(VALID_VERDICTS),
        'default_weights': DEFAULT_WEIGHTS,
        'note': '纠错是追加式补偿证据，原始记录保留；掌握度口径与长期记忆一致。',
    }
