"""B 模块长期记忆：学生知识点掌握状态的追加式记录与聚合。

存储位置说明（改动前必读）：

- 本模块用**独立 MetaData** 在自己的连接上建表（`CREATE TABLE IF NOT EXISTS` 语义），
  不把模型塞进 `backend/app/platform/database.py` 的 `Base`。
- 原因：`migrations/upgrade.py` 在 schema v3 时会逐张校验 `Base.metadata` 里的表是否都已存在，
  往 `Base` 里加表会让既有数据库启动时报 “Incomplete schema”。
- 该表与业务表在同一个数据库文件中，整库备份/恢复（`migrations/restore.py`）自然覆盖它。
- 若以后要把长期记忆纳入版本化 schema，需由平台侧出 v4 迁移并在 `upgrade.py` 里加分支。

掌握度口径（对教师与学生都要能解释）：

- 事件来自三类可核对的信号：学生自评/复述评价结果、步骤反馈结论、诊断命中；
- 掌握度用拉普拉斯平滑的加权成功率表示：`(正证据 + 1) / (正证据 + 负证据 + 2)`，
  没有证据时是 0.5，不代表掌握；
- 掌握度**不是模型判断**，证据不足时状态一律是 `learning`。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Sequence
from uuid import uuid4

from sqlalchemy import Column, Integer, MetaData, String, Table, delete, insert, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from . import knowledge
from ..platform.database import engine as default_engine

MEMORY_METADATA = MetaData()

LEARNING_EVENTS = Table(
    'ai_learning_events',
    MEMORY_METADATA,
    Column('id', String(36), primary_key=True),
    Column('user_id', String(64), nullable=False, index=True),
    Column('kind', String(24), nullable=False),
    Column('topic', String(64)),
    Column('point_id', String(64)),
    Column('verdict', String(16)),
    Column('weight', Integer, nullable=False, default=0),
    Column('excerpt', String(200)),
    Column('created_at', String(40), nullable=False),
)

DEFAULT_EVENT_WINDOW = 600
CONFIDENCE_STEP = 0.3
MAX_CONFIDENCE = 0.9

_READY = False


def ensure_table(engine: Engine | None = None) -> None:
    """惰性建表：只在真正读写记忆时调用，避免导入期碰数据库。"""
    global _READY
    if _READY:
        return
    MEMORY_METADATA.create_all(engine or default_engine, checkfirst=True)
    _READY = True


def reset_ready_flag() -> None:
    """测试用：允许在换引擎后重新建表。"""
    global _READY
    _READY = False


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record(
    db: Session,
    user_id: str,
    kind: str,
    *,
    topic: str | None = None,
    point_id: str | None = None,
    verdict: str | None = None,
    weight: int = 0,
    excerpt: str | None = None,
    engine: Engine | None = None,
) -> dict:
    """写入一条学习证据。`weight` 为正表示正面证据，为负表示负面证据。"""
    ensure_table(engine)
    row = {
        'id': str(uuid4()),
        'user_id': user_id,
        'kind': kind,
        'topic': knowledge.normalize_topic(topic),
        'point_id': point_id,
        'verdict': verdict,
        'weight': int(weight),
        'excerpt': (excerpt or '')[:200] or None,
        'created_at': _now(),
    }
    db.execute(insert(LEARNING_EVENTS).values(**row))
    db.commit()
    return row


def clear(db: Session, user_id: str, point_id: str | None = None, engine: Engine | None = None) -> int:
    """删除本人记忆（可按知识点局部删除）。返回删除条数。"""
    ensure_table(engine)
    statement = delete(LEARNING_EVENTS).where(LEARNING_EVENTS.c.user_id == user_id)
    if point_id:
        statement = statement.where(LEARNING_EVENTS.c.point_id == point_id)
    result = db.execute(statement)
    db.commit()
    return int(result.rowcount or 0)


def events(db: Session, user_id: str, limit: int = DEFAULT_EVENT_WINDOW, engine: Engine | None = None) -> list[dict]:
    ensure_table(engine)
    rows = db.execute(
        select(LEARNING_EVENTS)
        .where(LEARNING_EVENTS.c.user_id == user_id)
        .order_by(LEARNING_EVENTS.c.created_at.desc())
        .limit(limit)
    ).mappings().all()
    return [dict(row) for row in rows]


def _status_of(mastery: float, attempts: int) -> str:
    if attempts <= 0:
        return 'unseen'
    if mastery <= 0.4:
        return 'weak'
    if attempts >= 2 and mastery >= 0.75:
        return 'mastered'
    return 'learning'


def _aggregate_point(point_id: str, rows: Sequence[dict]) -> dict:
    positive = sum(row['weight'] for row in rows if row['weight'] > 0)
    negative = -sum(row['weight'] for row in rows if row['weight'] < 0)
    attempts = len(rows)
    mastery = (positive + 1) / (positive + negative + 2)
    point = knowledge.get_point(point_id)
    return {
        'point_id': point_id,
        'title': point.title if point else point_id,
        'topic': point.topic if point else None,
        'attempts': attempts,
        'positive': positive,
        'negative': negative,
        'mastery': round(mastery, 3),
        'confidence': round(min(MAX_CONFIDENCE, CONFIDENCE_STEP * attempts), 2),
        'status': _status_of(mastery, attempts),
        'last_seen': max(row['created_at'] for row in rows),
    }


def state(db: Session, user_id: str, limit: int = DEFAULT_EVENT_WINDOW, engine: Engine | None = None) -> dict:
    """按知识点聚合长期记忆。返回可直接给前端/教师的结构。"""
    rows = events(db, user_id, limit=limit, engine=engine)
    by_point: dict[str, list[dict]] = {}
    kinds: dict[str, int] = {}
    for row in rows:
        kinds[row['kind']] = kinds.get(row['kind'], 0) + 1
        if not row['point_id']:
            continue
        by_point.setdefault(row['point_id'], []).append(row)

    points = [_aggregate_point(point_id, items) for point_id, items in by_point.items()]
    points.sort(key=lambda item: (item['mastery'], -item['attempts'], item['point_id']))

    topics: dict[str, list[dict]] = {}
    for item in points:
        if item['topic']:
            topics.setdefault(item['topic'], []).append(item)
    topic_rows = [
        {
            'topic': topic,
            'points': len(items),
            'attempts': sum(item['attempts'] for item in items),
            'mastery': round(sum(item['mastery'] for item in items) / len(items), 3),
            'weak_points': sum(1 for item in items if item['status'] == 'weak'),
        }
        for topic, items in topics.items()
    ]
    topic_rows.sort(key=lambda item: (item['mastery'], item['topic']))

    return {
        'user_id': user_id,
        'event_count': len(rows),
        'kinds': kinds,
        'updated_at': rows[0]['created_at'] if rows else None,
        'points': points,
        'topics': topic_rows,
        'weak_points': [item['point_id'] for item in points if item['status'] == 'weak'],
        'mastered_points': [item['point_id'] for item in points if item['status'] == 'mastered'],
        'evidence_tags': ['学生自评/复述评价', '步骤反馈结论', '诊断命中'],
        'note': '掌握度由可核对的证据汇总平滑得到，证据不足时不判定掌握；它不是模型判断。',
    }


def point_mastery(state_data: dict, point_id: str) -> dict | None:
    for item in state_data.get('points', []):
        if item['point_id'] == point_id:
            return item
    return None


def weak_point_ids(state_data: dict, limit: int | None = None) -> list[str]:
    ids = list(state_data.get('weak_points') or [])
    if limit is not None:
        return ids[:limit]
    return ids


def seen_point_ids(state_data: dict) -> set[str]:
    return {item['point_id'] for item in state_data.get('points', [])}


def summarize_kinds(rows: Iterable[dict]) -> dict:
    counts: dict[str, int] = {}
    for row in rows:
        counts[row['kind']] = counts.get(row['kind'], 0) + 1
    return counts
