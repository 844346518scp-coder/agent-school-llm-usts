"""B 模块复习排期（间隔重复的规则版）：把长期记忆证据变成「今天该复习什么」。

口径（对教师与学生都要能解释）：

- 排期只用**可核对证据的时间戳与掌握档位**：`last_seen + 间隔` 得到到期时间，不调用模型；
- 间隔取值是教学经验规则（薄弱 1 天 / 练习中 3 天 / 已较稳 7 天），**未经学习效果实验校准**，
  响应里必须带上这条说明，不得写成“科学记忆曲线”；
- 还没练过的知识点不进排期（没有证据就没有到期日），只会出现在推荐练习里；
- 掌握度仍是长期记忆口径（拉普拉斯平滑加权成功率），证据不足时不算掌握。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Sequence

from . import knowledge

# 复习间隔（天）：规则取自常见教学节奏，而非实验结果。
INTERVALS = {'weak': 1, 'learning': 3, 'mastered': 7}
DEFAULT_HORIZON = 7
MAX_HORIZON = 60
MAX_ITEMS = 12
RULE_NOTE = ('间隔按掌握档位取值（薄弱 1 天 / 练习中 3 天 / 已较稳 7 天），属于教学经验规则，'
             '未经学习效果实验校准；它不是记忆曲线模型。排序规则：薄弱知识点优先，其次逾期越久越靠前。')


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def plan(state_data: dict | None, days: int = DEFAULT_HORIZON, limit: int = 8,
         topic: str | None = None, now: datetime | None = None) -> dict:
    """按长期记忆给出复习排期：到期与临期分开，逾期越久越靠前。"""
    moment = now or datetime.now(timezone.utc)
    horizon = max(1, min(MAX_HORIZON, int(days)))
    wanted = knowledge.normalize_topic(topic)

    due: list[dict] = []
    upcoming: list[dict] = []
    unscheduled: list[dict] = []

    for item in (state_data or {}).get('points', []):
        point = knowledge.get_point(item['point_id'])
        if point is None or (wanted and point.topic != wanted):
            continue
        interval = INTERVALS.get(item['status'])
        last_seen = _parse_time(item.get('last_seen'))
        if interval is None or last_seen is None:
            unscheduled.append({'point_id': item['point_id'], 'title': point.title,
                                'status': item['status'], 'why': '这个档位不排期（未练过或数据不足）。'})
            continue
        due_at = last_seen + timedelta(days=interval)
        overdue_days = round((moment - due_at).total_seconds() / 86400, 2)
        row = {
            'point_id': point.id,
            'title': point.title,
            'topic': point.topic,
            'status': item['status'],
            'mastery': item['mastery'],
            'attempts': item['attempts'],
            'last_seen': item['last_seen'],
            'due_at': due_at.isoformat(),
            'interval_days': interval,
            'overdue_days': overdue_days,
            'source': point.source,
            'verified': point.verified,
            'reason': (f"上次练习 {last_seen.date().isoformat()}，按 {interval} 天间隔已逾期 {overdue_days} 天。"
                       if overdue_days > 0 else
                       f"上次练习 {last_seen.date().isoformat()}，按 {interval} 天间隔还有 {abs(overdue_days):.2f} 天到期。"),
        }
        if overdue_days >= 0:
            due.append(row)
        elif -overdue_days <= horizon:
            upcoming.append(row)

    # 排序规则：薄弱优先，其次逾期越久越靠前，再次掌握度低的靠前。
    priority = {'weak': 0, 'learning': 1, 'mastered': 2}
    due.sort(key=lambda row: (priority.get(row['status'], 3), -row['overdue_days'], row['mastery'], row['point_id']))
    upcoming.sort(key=lambda row: (row['overdue_days'], priority.get(row['status'], 3), row['mastery'], row['point_id']))

    items = due[:max(0, min(MAX_ITEMS, int(limit)))]
    return {
        'mode': 'demo',
        'notice': None,
        'horizon_days': horizon,
        'due_count': len(due),
        'upcoming_count': len(upcoming),
        'items': items,
        'upcoming': upcoming[:5],
        'unscheduled': unscheduled[:5],
        'intervals': dict(INTERVALS),
        'rule': RULE_NOTE,
        'method': '长期记忆的时间戳与掌握档位（规则排序，未调用模型）',
        'note': ('排期只说明“该复习了”，不等于学生已经忘记；掌握度证据不足时仍按长期记忆口径显示。'),
    }


def intervals_for(status: str) -> int | None:
    return INTERVALS.get(status)


def describe() -> dict:
    return {
        'intervals': dict(INTERVALS),
        'max_horizon_days': MAX_HORIZON,
        'max_items': MAX_ITEMS,
        'rule': RULE_NOTE,
    }
