from datetime import date, datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..platform.auth import current_user, require_role
from ..platform.database import Assignment, Submission, User, get_db

router = APIRouter(prefix='/api/assignments', tags=['teaching'])


class AssignmentInput(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=3000)
    topic: str = Field(min_length=1, max_length=40)
    due_date: date

    @field_validator('title', 'content', 'topic')
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError('内容不能为空')
        return value.strip()


class SubmissionInput(BaseModel):
    answer: str = Field(min_length=1, max_length=5000)

    @field_validator('answer')
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError('请输入作答内容')
        return value.strip()


def assignment_data(item, db, user):
    submissions = list(db.scalars(select(Submission).where(Submission.assignment_id == item.id)))
    own = next((s for s in submissions if s.student_id == user.id), None)
    data = {key: getattr(item, key) for key in ('id', 'title', 'content', 'topic', 'due_date', 'created_at')}
    data['submitted'] = own is not None
    data['answer'] = own.answer if own else ''
    if user.role == 'teacher':
        data['submissions'] = [{'student_name': db.get(User, s.student_id).name, 'answer': s.answer, 'created_at': s.created_at} for s in submissions]
    return data


@router.get('')
def assignments(user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = select(Assignment).order_by(Assignment.created_at.desc())
    if user.role == 'teacher':
        query = query.where(Assignment.teacher_id == user.id)
    return [assignment_data(item, db, user) for item in db.scalars(query)]


@router.post('', status_code=201)
def create_assignment(data: AssignmentInput, user: User = Depends(require_role('teacher')), db: Session = Depends(get_db)):
    if data.due_date < date.today():
        raise HTTPException(422, '截止日期不能早于今天。')
    item = Assignment(id=str(uuid4()), teacher_id=user.id, title=data.title, content=data.content,
                      topic=data.topic, due_date=data.due_date.isoformat(), created_at=datetime.now(timezone.utc).isoformat())
    db.add(item)
    db.commit()
    return assignment_data(item, db, user)


@router.put('/{assignment_id}/submission')
def submit(assignment_id: str, data: SubmissionInput, user: User = Depends(require_role('student')), db: Session = Depends(get_db)):
    item = db.get(Assignment, assignment_id)
    if not item:
        raise HTTPException(404, '作业不存在。')
    if date.fromisoformat(item.due_date) < date.today():
        raise HTTPException(409, '作业已截止，暂不能修改或提交。')
    key = f'{assignment_id}:{user.id}'
    submission = db.get(Submission, key)
    if submission:
        submission.answer = data.answer
        submission.created_at = datetime.now(timezone.utc).isoformat()
    else:
        db.add(Submission(id=key, assignment_id=item.id, student_id=user.id, answer=data.answer, created_at=datetime.now(timezone.utc).isoformat()))
    db.commit()
    return assignment_data(item, db, user)
