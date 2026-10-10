"""B 模块班级掌握度聚合（只读）：把学生的可核对证据按班汇总给教师。

边界（改动前必读）：

- B 只**读** platform 的班级与成员表，不新增表、不改结构、不做迁移；
- 教师只能看自己名下的班级（`Classroom.teacher_id == user.id`，与 C 的教师端同一口径），越权一律按“不存在”处理；
- 聚合只输出**掌握状态与证据条数**，不包含学生作答原文（`excerpt` 不对外），避免把学生草稿暴露给全班视角；
- 掌握度口径与长期记忆一致（拉普拉斯平滑加权成功率），证据不足时是“未练”，不是“已掌握”；
- 与 C 的分工：本接口是 B 侧的学情数据供给，教师端页面与更细的权限矩阵（助教、多教师）仍以 C 的班级权限为准，
  需要更细的权限时先出契约再改。
"""
from __future__ import annotations

from datetime import timezone
from typing import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import knowledge, memory
from ..platform.database import ClassMember, Classroom, User

MAX_STUDENTS = 200
TOP_WEAK = 5

PRIVACY = '只汇总掌握状态与证据条数，不包含学生作答原文；教师只能查看自己名下的班级。'
MASTERY_RULE = '掌握度 = 拉普拉斯平滑加权成功率；证据不足时显示“未练”，不判定为已掌握（与长期记忆口径一致）。'
SCOPE_NOTE = ('本接口是 B 侧的学情数据供给；教师端页面与更细的权限（助教、多教师）以 C 的班级权限为准。')


def own_class(db: Session, class_id: str, teacher_id: str) -> Classroom:
    """取教师自己的班级；不存在或不属于该教师都按不存在处理（不泄露他班存在性）。"""
    item = db.get(Classroom, class_id)
    if item is None or item.teacher_id != teacher_id:
        raise LookupError('班级不存在或不可访问。')
    return item


def student_ids(db: Session, class_id: str) -> list[str]:
    return list(db.scalars(
        select(User.id)
        .join(ClassMember, ClassMember.student_id == User.id)
        .where(ClassMember.class_id == class_id, ClassMember.active.is_(True), User.active.is_(True))
    ))[:MAX_STUDENTS]


def _student_names(db: Session, ids: Sequence[str]) -> dict[str, str]:
    if not ids:
        return {}
    rows = db.execute(select(User.id, User.name).where(User.id.in_(list(ids)))).all()
    return {row[0]: row[1] for row in rows}


def _events_by_student(db: Session, ids: Sequence[str]) -> dict[str, list[dict]]:
    """一次查出全班证据，避免逐个学生查询（事件表是 B 自有表，只读）。"""
    if not ids:
        return {}
    memory.ensure_table()
    rows = db.execute(
        select(memory.LEARNING_EVENTS).where(memory.LEARNING_EVENTS.c.user_id.in_(list(ids)))
    ).mappings().all()
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row['user_id'], []).append(dict(row))
    return grouped


def _student_row(student_id: str, name: str | None, rows: Sequence[dict]) -> dict:
    by_point: dict[str, list[dict]] = {}
    for row in rows:
        if row['point_id']:
            by_point.setdefault(row['point_id'], []).append(row)
    points = [memory._aggregate_point(point_id, items) for point_id, items in by_point.items()]
    weak = [item for item in points if item['status'] == 'weak']
    mastered = [item for item in points if item['status'] == 'mastered']
    graded = [item for item in points if item['attempts'] > 0]
    return {
        'id': student_id,
        'name': name or student_id,
        'event_count': len(rows),
        'evidence_points': len(points),
        'weak_points': len(weak),
        'mastered_points': len(mastered),
        'avg_mastery': round(sum(item['mastery'] for item in graded) / len(graded), 3) if graded else None,
        'last_active': max((row['created_at'] for row in rows), default=None),
    }


def _point_rows(students: Sequence[dict], per_student_points: dict[str, list[dict]]) -> list[dict]:
    buckets: dict[str, list[dict]] = {}
    for item in students:
        for point in per_student_points.get(item['id'], []):
            buckets.setdefault(point['point_id'], []).append(point)
    rows: list[dict] = []
    for point_id, items in buckets.items():
        point = knowledge.get_point(point_id)
        rows.append({
            'point_id': point_id,
            'title': point.title if point else point_id,
            'topic': point.topic if point else None,
            'verified': point.verified if point else False,
            'students_with_evidence': len(items),
            'weak_students': sum(1 for item in items if item['status'] == 'weak'),
            'mastered_students': sum(1 for item in items if item['status'] == 'mastered'),
            'avg_mastery': round(sum(item['mastery'] for item in items) / len(items), 3),
        })
    rows.sort(key=lambda item: (-item['weak_students'], item['avg_mastery'], item['point_id']))
    return rows


def overview(db: Session, classroom: Classroom) -> dict:
    """一个班级的掌握度聚合（只含掌握状态与证据条数）。"""
    ids = student_ids(db, classroom.id)
    names = _student_names(db, ids)
    grouped = _events_by_student(db, ids)

    students: list[dict] = []
    per_student_points: dict[str, list[dict]] = {}
    for student_id in ids:
        rows = grouped.get(student_id, [])
        students.append(_student_row(student_id, names.get(student_id), rows))
        by_point: dict[str, list[dict]] = {}
        for row in rows:
            if row['point_id']:
                by_point.setdefault(row['point_id'], []).append(row)
        per_student_points[student_id] = [memory._aggregate_point(point_id, items)
                                          for point_id, items in by_point.items()]

    students.sort(key=lambda item: (item['weak_points'], -(item['event_count']), item['name']))
    points = _point_rows(students, per_student_points)
    with_evidence = [item for item in students if item['evidence_points']]
    graded = [item['avg_mastery'] for item in with_evidence if item['avg_mastery'] is not None]

    return {
        'mode': 'demo',
        'notice': None,
        'class': {
            'id': classroom.id,
            'name': classroom.name,
            'course': classroom.course,
            'term': classroom.term,
            'archived': classroom.archived,
        },
        'students': students,
        'points': points,
        'top_weak': points[:TOP_WEAK],
        'summary': {
            'students': len(students),
            'students_with_evidence': len(with_evidence),
            'evidence_events': sum(item['event_count'] for item in students),
            'weak_point_rows': sum(item['weak_students'] for item in points),
            'class_avg_mastery': round(sum(graded) / len(graded), 3) if graded else None,
        },
        'unseen_note': '没有证据的学生或知识点只显示“未练/证据不足”，不得显示为已掌握。',
        'privacy': PRIVACY,
        'mastery_rule': MASTERY_RULE,
        'scope_note': SCOPE_NOTE,
        'method': 'B 长期记忆聚合（只读班级成员表），未调用模型',
    }


def class_list(db: Session, teacher_id: str) -> dict:
    """教师名下班级的概览列表（不含学生明细）。"""
    classrooms = list(db.scalars(
        select(Classroom).where(Classroom.teacher_id == teacher_id).order_by(Classroom.created_at.desc())
    ))
    rows: list[dict] = []
    for classroom in classrooms:
        detail = overview(db, classroom)
        rows.append({
            'class_id': classroom.id,
            'name': classroom.name,
            'course': classroom.course,
            'term': classroom.term,
            'archived': classroom.archived,
            'summary': detail['summary'],
            'top_weak': [{'point_id': item['point_id'], 'title': item['title'],
                          'weak_students': item['weak_students']} for item in detail['top_weak'][:3]],
        })
    return {
        'mode': 'demo',
        'notice': None,
        'classes': rows,
        'total': len(rows),
        'privacy': PRIVACY,
        'mastery_rule': MASTERY_RULE,
        'scope_note': SCOPE_NOTE,
        'method': 'B 长期记忆聚合（只读班级成员表），未调用模型',
    }


def describe() -> dict:
    return {
        'top_weak': TOP_WEAK,
        'max_students': MAX_STUDENTS,
        'outputs': ['班级概览', '学生证据条数', '知识点薄弱人数与平均掌握度'],
        'privacy': PRIVACY,
        'scope_note': SCOPE_NOTE,
    }
