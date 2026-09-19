"""Teacher-owned classes and managed student accounts; no access to private chat."""
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..platform.auth import (AccountInput, Input, create_user, hash_password,
                             public_user, require_role, validate_name, validate_password)
from ..platform.database import (Assignment, AssignmentRecipient, Classroom, ClassMember,
                                 Review, Submission, User, Session as LoginSession, get_db, write_db)

router = APIRouter(prefix='/api', tags=['classes'])


class ClassInput(Input):
    name: str = Field(min_length=1, max_length=80)
    course: str = Field(min_length=1, max_length=80)
    term: str = Field(min_length=1, max_length=80)
    _text = field_validator('name', 'course', 'term')(validate_name)


class ClassPatch(Input):
    name: str = Field(default='', min_length=1, max_length=80)
    course: str = Field(default='', min_length=1, max_length=80)
    term: str = Field(default='', min_length=1, max_length=80)
    archived: bool = False
    _text = field_validator('name', 'course', 'term')(validate_name)


class MemberInput(Input):
    username: str = Field(min_length=1, max_length=80)


class MemberPatch(Input):
    active: bool


class StudentPatch(Input):
    name: str = Field(default='', min_length=1, max_length=80)
    active: bool = True
    _name = field_validator('name')(validate_name)


class ResetInput(Input):
    password: str = Field(min_length=10, max_length=128)
    _password = field_validator('password')(validate_password)


def owned_class(db, class_id, user, writable=False):
    item = db.get(Classroom, class_id)
    if not item or item.teacher_id != user.id:
        raise HTTPException(404, '班级不存在或不可访问。')
    if writable and item.archived:
        raise HTTPException(409, '班级已归档，请先恢复班级。')
    return item


def managed_student(db, student_id, user):
    student = db.get(User, student_id)
    if not student or student.role != 'student' or student.created_by != user.id:
        raise HTTPException(404, '学生不存在或不属于您管理。')
    return student


def class_data(item, db):
    students = list(db.scalars(select(User.id).join(ClassMember, ClassMember.student_id == User.id)
                              .where(ClassMember.class_id == item.id, ClassMember.active.is_(True), User.active.is_(True))))
    return {key: getattr(item, key) for key in ('id', 'name', 'course', 'term', 'archived', 'created_at')} | {'student_count': len(students)}


def student_data(student, member, db, teacher_id):
    result = public_user(student) | {'member_active': member.active, 'manageable': student.created_by == teacher_id,
                                   'submitted': 0, 'completed': 0, 'pending': 0, 'needs_improvement': 0, 'expected': 0}
    assignments = db.scalars(select(Assignment).join(AssignmentRecipient, AssignmentRecipient.assignment_id == Assignment.id)
                            .where(Assignment.class_id == member.class_id, Assignment.status == 'published', AssignmentRecipient.student_id == student.id))
    for item in assignments:
        result['expected'] += 1
        submission = db.get(Submission, f'{item.id}:{student.id}')
        if submission:
            result['submitted'] += 1
            review = db.scalar(select(Review).where(Review.submission_id == submission.id, Review.version == submission.version))
            result[review.status if review else 'pending'] += 1
    return result


@router.get('/classes')
def classes(user: User = Depends(require_role('teacher')), db: Session = Depends(get_db)):
    return [class_data(item, db) for item in db.scalars(select(Classroom).where(Classroom.teacher_id == user.id).order_by(Classroom.created_at.desc()))]


@router.post('/classes', status_code=201)
def create_class(data: ClassInput, db: Session = Depends(write_db), user: User = Depends(require_role('teacher'))):
    item = Classroom(id=str(uuid4()), teacher_id=user.id, **data.model_dump(), archived=False, created_at=datetime.now(timezone.utc).isoformat())
    db.add(item)
    db.commit()
    return class_data(item, db)


@router.patch('/classes/{class_id}')
def edit_class(class_id: str, data: ClassPatch, db: Session = Depends(write_db), user: User = Depends(require_role('teacher'))):
    item = owned_class(db, class_id, user)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    db.commit()
    return class_data(item, db)


@router.get('/classes/{class_id}/students')
def students(class_id: str, user: User = Depends(require_role('teacher')), db: Session = Depends(get_db)):
    owned_class(db, class_id, user)
    members = list(db.scalars(select(ClassMember).where(ClassMember.class_id == class_id)))
    return sorted([student_data(db.get(User, member.student_id), member, db, user.id) for member in members], key=lambda s: s['username'])


@router.post('/classes/{class_id}/students', status_code=201)
def create_student(class_id: str, data: AccountInput, db: Session = Depends(write_db), user: User = Depends(require_role('teacher'))):
    owned_class(db, class_id, user, writable=True)
    student = create_user(db, data, 'student', created_by=user.id, temporary=True)
    member = ClassMember(class_id=class_id, student_id=student.id, active=True)
    db.add(member)
    db.commit()
    return student_data(student, member, db, user.id)


@router.post('/classes/{class_id}/members', status_code=201)
def add_member(class_id: str, data: MemberInput, db: Session = Depends(write_db), user: User = Depends(require_role('teacher'))):
    owned_class(db, class_id, user, writable=True)
    student = db.scalar(select(User).where(User.username == data.username, User.role == 'student', User.created_by == user.id))
    if not student:
        raise HTTPException(404, '学生不存在或不属于您管理。')
    if not student.active:
        raise HTTPException(409, '学生账号已停用，请先恢复账号。')
    member = db.get(ClassMember, (class_id, student.id))
    if not member:
        member = ClassMember(class_id=class_id, student_id=student.id, active=True)
        db.add(member)
    else:
        member.active = True
    db.commit()
    return student_data(student, member, db, user.id)


@router.patch('/classes/{class_id}/members/{student_id}')
def edit_member(class_id: str, student_id: str, data: MemberPatch, db: Session = Depends(write_db), user: User = Depends(require_role('teacher'))):
    owned_class(db, class_id, user, writable=True)
    member = db.get(ClassMember, (class_id, student_id))
    if not member:
        raise HTTPException(404, '班级成员不存在。')
    # Membership belongs to the class teacher; account management remains creator-only.
    member.active = data.active
    db.commit()
    return student_data(db.get(User, student_id), member, db, user.id)


@router.patch('/students/{student_id}')
def edit_student(student_id: str, data: StudentPatch, db: Session = Depends(write_db), user: User = Depends(require_role('teacher'))):
    student = managed_student(db, student_id, user)
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(student, key, value)
    if not student.active:
        db.execute(delete(LoginSession).where(LoginSession.user_id == student.id))
    db.commit()
    return public_user(student)


@router.post('/students/{student_id}/password')
def reset_student_password(student_id: str, data: ResetInput, db: Session = Depends(write_db), user: User = Depends(require_role('teacher'))):
    student = managed_student(db, student_id, user)
    student.password_hash = hash_password(data.password)
    student.must_change_password = True
    student.is_demo = False
    db.execute(delete(LoginSession).where(LoginSession.user_id == student.id))
    db.commit()
    return public_user(student)
