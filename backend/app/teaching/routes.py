from datetime import date, datetime, timezone
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from ..platform.auth import current_user, require_role
from ..platform.database import Assignment, AssignmentRecipient, Classroom, ClassMember, Question, Review, Submission, User, get_db, write_db
from .classes import owned_class

router = APIRouter(prefix='/api', tags=['teaching'])


def now():
    return datetime.now(timezone.utc).isoformat()


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class AssignmentInput(Input):
    title: str = Field(min_length=1, max_length=100)
    content: str = Field(min_length=1, max_length=3000)
    topic: str = Field(min_length=1, max_length=40)
    due_date: date
    class_id: str = Field(min_length=1, max_length=40)

    @field_validator('title', 'content', 'topic')
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError('内容不能为空')
        return value.strip()


class DraftInput(Input):
    title: str = Field(default='', max_length=100)
    content: str = Field(default='', max_length=3000)
    topic: str = Field(default='', max_length=40)
    due_date: str = ''
    question_ids: list[str] = Field(default_factory=list, max_length=30)
    class_id: str | None = Field(default=None, min_length=1, max_length=40)

    @field_validator('due_date')
    @classmethod
    def valid_date(cls, value):
        return date.fromisoformat(value).isoformat() if value else ''


class AssignmentPatch(Input):
    title: str = Field(default='', max_length=100)
    content: str = Field(default='', max_length=3000)
    topic: str = Field(default='', max_length=40)
    due_date: str = ''
    class_id: str | None = Field(default=None, min_length=1, max_length=40)

    @field_validator('due_date')
    @classmethod
    def valid_date(cls, value):
        return DraftInput.valid_date(value)


class QuestionInput(Input):
    title: str = Field(min_length=1, max_length=100)
    topic: str = Field(min_length=1, max_length=40)
    content: str = Field(min_length=1, max_length=3000)
    reference_answer: str = Field(default='', max_length=3000)

    @field_validator('title', 'topic', 'content')
    @classmethod
    def not_blank(cls, value):
        return AssignmentInput.not_blank(value)


class QuestionPatch(Input):
    title: str = Field(default='', min_length=1, max_length=100)
    topic: str = Field(default='', min_length=1, max_length=40)
    content: str = Field(default='', min_length=1, max_length=3000)
    reference_answer: str = Field(default='', max_length=3000)

    @field_validator('title', 'topic', 'content')
    @classmethod
    def not_blank(cls, value):
        return AssignmentInput.not_blank(value)


class SubmissionInput(Input):
    answer: str = Field(min_length=1, max_length=5000)

    @field_validator('answer')
    @classmethod
    def not_blank(cls, value):
        return AssignmentInput.not_blank(value)


class ReviewInput(Input):
    version: int = Field(ge=1)
    comment: str = Field(min_length=1, max_length=3000)
    status: Literal['needs_improvement', 'completed']

    @field_validator('comment')
    @classmethod
    def not_blank(cls, value):
        return AssignmentInput.not_blank(value)


def owned(db, model, item_id, user):
    item = db.get(model, item_id)
    if not item or item.teacher_id != user.id:
        raise HTTPException(404, '记录不存在或不可访问。')
    return item


def review_data(item):
    return {key: getattr(item, key) for key in ('id', 'version', 'comment', 'status', 'answer_snapshot', 'reviewed_at')}


def submission_data(item, db):
    reviews = list(db.scalars(select(Review).where(Review.submission_id == item.id).order_by(Review.version.desc())))
    student = db.get(User, item.student_id)
    return {key: getattr(item, key) for key in ('id', 'student_id', 'answer', 'created_at', 'version')} | {
        'student_name': student.name if student else '已移除账号',
        'review': next((review_data(r) for r in reviews if r.version == item.version), None),
        'review_history': [review_data(r) for r in reviews if r.version < item.version],
    }


def assignment_data(item, db, user):
    query = select(Submission).where(Submission.assignment_id == item.id)
    if user.role != 'teacher':
        query = query.where(Submission.student_id == user.id)
    submissions = list(db.scalars(query.order_by(Submission.created_at)))
    own = next((s for s in submissions if s.student_id == user.id), None)
    data = {key: getattr(item, key) for key in ('id', 'title', 'content', 'topic', 'due_date', 'created_at', 'status')}
    data.update(submitted=own is not None, answer=own.answer if own else '', submission=submission_data(own, db) if own else None)
    classroom = db.get(Classroom, item.class_id) if item.class_id else None
    data.update(class_id=item.class_id, class_name=classroom.name if classroom else '',
                class_archived=classroom.archived if classroom else False,
                recipient_count=db.scalar(select(func.count()).select_from(AssignmentRecipient).where(AssignmentRecipient.assignment_id == item.id)))
    if user.role == 'teacher':
        data['submissions'] = [submission_data(s, db) for s in submissions]
    else:
        member = db.get(ClassMember, (item.class_id, user.id)) if item.class_id else None
        recipient = db.get(AssignmentRecipient, (item.id, user.id))
        data['can_submit'] = bool(recipient and member and member.active and user.active and classroom and not classroom.archived
                                  and item.status == 'published' and item.due_date >= date.today().isoformat())
    return data


def question_data(item):
    return {key: getattr(item, key) for key in ('id', 'teacher_id', 'title', 'topic', 'content', 'reference_answer', 'archived', 'created_at', 'updated_at')}


def ensure_publishable(item):
    if not all(getattr(item, field).strip() for field in ('title', 'content', 'topic', 'due_date')):
        raise HTTPException(422, '发布前请填写标题、章节、题干和截止日期。')
    if date.fromisoformat(item.due_date) < date.today():
        raise HTTPException(422, '截止日期不能早于今天。')


def snapshot_recipients(item, db, user):
    if not item.class_id:
        raise HTTPException(422, '发布前请选择班级。')
    owned_class(db, item.class_id, user, writable=True)
    ids = list(db.scalars(select(User.id).join(ClassMember, ClassMember.student_id == User.id)
                         .where(ClassMember.class_id == item.class_id, ClassMember.active.is_(True), User.active.is_(True), User.role == 'student')))
    if not ids:
        raise HTTPException(422, '班级至少需要一位有效学生才能发布作业。')
    db.flush()
    db.add_all([AssignmentRecipient(assignment_id=item.id, student_id=sid) for sid in ids])


def ensure_class_writable(item, db, user):
    if item.class_id:
        owned_class(db, item.class_id, user, writable=True)


@router.get('/questions')
def questions(search: str = '', topic: str = '', archived: bool = False, user: User = Depends(require_role('teacher')), db: Session = Depends(get_db)):
    query = select(Question).where(Question.teacher_id == user.id, Question.archived == archived)
    if search.strip():
        query = query.where(Question.title.contains(search.strip(), autoescape=True) | Question.content.contains(search.strip(), autoescape=True))
    if topic:
        query = query.where(Question.topic == topic)
    return [question_data(q) for q in db.scalars(query.order_by(Question.updated_at.desc()))]


@router.post('/questions', status_code=201)
def create_question(data: QuestionInput, db: Session = Depends(write_db), user: User = Depends(require_role('teacher'))):
    item = Question(id=str(uuid4()), teacher_id=user.id, **data.model_dump(), archived=False, created_at=now(), updated_at=now())
    db.add(item)
    db.commit()
    return question_data(item)


@router.patch('/questions/{question_id}')
def edit_question(question_id: str, data: QuestionPatch, db: Session = Depends(write_db), user: User = Depends(require_role('teacher'))):
    item = owned(db, Question, question_id, user)
    if item.archived:
        raise HTTPException(409, '已归档题目不可编辑。')
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    item.updated_at = now()
    db.commit()
    return question_data(item)


@router.post('/questions/{question_id}/archive')
def archive_question(question_id: str, db: Session = Depends(write_db), user: User = Depends(require_role('teacher'))):
    item = owned(db, Question, question_id, user)
    if not item.archived:
        item.archived = True
        item.updated_at = now()
        db.commit()
    return question_data(item)


@router.get('/teaching/stats')
def stats(class_id: str | None = None, user: User = Depends(require_role('teacher')), db: Session = Depends(get_db)):
    if class_id:
        owned_class(db, class_id, user)
    classes_query = select(Classroom).where(Classroom.teacher_id == user.id, Classroom.archived.is_(False))
    if class_id:
        classes_query = classes_query.where(Classroom.id == class_id)
    class_ids = [c.id for c in db.scalars(classes_query)]
    items = list(db.scalars(select(Assignment).where(Assignment.teacher_id == user.id, Assignment.status == 'published', Assignment.class_id.in_(class_ids))))
    student_ids = set(db.scalars(select(User.id).join(ClassMember, ClassMember.student_id == User.id).where(ClassMember.class_id.in_(class_ids), ClassMember.active.is_(True), User.active.is_(True))))
    result = dict(classes=len(class_ids), students=len(student_ids), expected=0, unsubmitted=0,
                  published=len(items), submitted=0, pending=0, needs_improvement=0, completed=0)
    for item in items:
        recipients = set(db.scalars(select(AssignmentRecipient.student_id).where(AssignmentRecipient.assignment_id == item.id)))
        result['expected'] += len(recipients)
        for s in db.scalars(select(Submission).where(Submission.assignment_id == item.id, Submission.student_id.in_(recipients))):
            review = db.scalar(select(Review).where(Review.submission_id == s.id, Review.version == s.version))
            result['submitted'] += 1
            result[review.status if review else 'pending'] += 1
    result['unsubmitted'] = result['expected'] - result['submitted']
    return result


@router.get('/assignments')
def assignments(class_id: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = select(Assignment).order_by(Assignment.created_at.desc())
    if class_id:
        if user.role == 'teacher':
            owned_class(db, class_id, user)
        elif not db.get(ClassMember, (class_id, user.id)):
            raise HTTPException(404, '班级不存在或不可访问。')
        query = query.where(Assignment.class_id == class_id)
    query = query.where(Assignment.teacher_id == user.id) if user.role == 'teacher' else query.join(AssignmentRecipient, AssignmentRecipient.assignment_id == Assignment.id).where(Assignment.status != 'draft', AssignmentRecipient.student_id == user.id)
    return [assignment_data(item, db, user) for item in db.scalars(query)]


@router.post('/assignments', status_code=201)
def create_assignment(data: AssignmentInput, db: Session = Depends(write_db), user: User = Depends(require_role('teacher'))):
    item = Assignment(id=str(uuid4()), teacher_id=user.id, **data.model_dump(exclude={'due_date'}), due_date=data.due_date.isoformat(), created_at=now(), status='published')
    ensure_publishable(item)
    db.add(item)
    snapshot_recipients(item, db, user)
    db.commit()
    return assignment_data(item, db, user)


@router.post('/assignments/drafts', status_code=201)
def create_draft(data: DraftInput, db: Session = Depends(write_db), user: User = Depends(require_role('teacher'))):
    if data.class_id:
        owned_class(db, data.class_id, user, writable=True)
    content = data.content
    if data.question_ids:
        if len(set(data.question_ids)) != len(data.question_ids):
            raise HTTPException(422, '不能重复选择同一道题。')
        selected = [owned(db, Question, qid, user) for qid in data.question_ids]
        if any(q.archived for q in selected):
            raise HTTPException(409, '已归档题目不可加入新作业。')
        content = '\n\n'.join(f'{i}. {q.content}' for i, q in enumerate(selected, 1))
        if len(content) > 3000:
            raise HTTPException(422, '所选题干总长度超过3000字符，请减少题目。')
    item = Assignment(id=str(uuid4()), teacher_id=user.id, **data.model_dump(exclude={'question_ids', 'content'}), content=content, status='draft', created_at=now())
    db.add(item)
    db.commit()
    return assignment_data(item, db, user)


@router.patch('/assignments/{assignment_id}')
def edit_assignment(assignment_id: str, data: AssignmentPatch, db: Session = Depends(write_db), user: User = Depends(require_role('teacher'))):
    item = owned(db, Assignment, assignment_id, user)
    changes = data.model_dump(exclude_unset=True)
    if item.status == 'archived':
        raise HTTPException(409, '归档作业不可编辑。')
    ensure_class_writable(item, db, user)
    if 'class_id' in changes and data.class_id:
        owned_class(db, data.class_id, user, writable=True)
    if item.status == 'published':
        if set(changes) != {'due_date'} or not data.due_date or data.due_date < item.due_date:
            raise HTTPException(409, '已发布作业仅可延长截止日期；修改题干请复制为草稿。')
    for key, value in changes.items():
        setattr(item, key, value)
    db.commit()
    return assignment_data(item, db, user)


@router.delete('/assignments/{assignment_id}')
def delete_draft(assignment_id: str, db: Session = Depends(write_db), user: User = Depends(require_role('teacher'))):
    item = owned(db, Assignment, assignment_id, user)
    if item.status != 'draft':
        raise HTTPException(409, '只能删除草稿，已发布作业请归档。')
    ensure_class_writable(item, db, user)
    db.delete(item)
    db.commit()
    return {'ok': True}


@router.post('/assignments/{assignment_id}/publish')
def publish(assignment_id: str, db: Session = Depends(write_db), user: User = Depends(require_role('teacher'))):
    item = owned(db, Assignment, assignment_id, user)
    if item.status == 'archived':
        raise HTTPException(409, '归档作业不能重新发布。')
    ensure_class_writable(item, db, user)
    if item.status == 'draft':
        ensure_publishable(item)
        snapshot_recipients(item, db, user)
        item.status = 'published'
        db.commit()
    return assignment_data(item, db, user)


@router.post('/assignments/{assignment_id}/archive')
def archive(assignment_id: str, db: Session = Depends(write_db), user: User = Depends(require_role('teacher'))):
    item = owned(db, Assignment, assignment_id, user)
    if item.status == 'draft':
        raise HTTPException(409, '草稿可以删除，无需归档。')
    ensure_class_writable(item, db, user)
    if item.status != 'archived':
        item.status = 'archived'
        db.commit()
    return assignment_data(item, db, user)


@router.post('/assignments/{assignment_id}/copy', status_code=201)
def copy_assignment(assignment_id: str, db: Session = Depends(write_db), user: User = Depends(require_role('teacher'))):
    source = owned(db, Assignment, assignment_id, user)
    classroom = db.get(Classroom, source.class_id) if source.class_id else None
    # A new draft must remain editable even if its source belongs to a closed term.
    target_class = classroom.id if classroom and not classroom.archived else None
    item = Assignment(id=str(uuid4()), teacher_id=user.id, class_id=target_class, title=source.title, topic=source.topic, content=source.content, due_date='', status='draft', created_at=now())
    db.add(item)
    db.commit()
    return assignment_data(item, db, user)


@router.put('/assignments/{assignment_id}/submission')
def submit(assignment_id: str, data: SubmissionInput, db: Session = Depends(write_db), user: User = Depends(require_role('student'))):
    item = db.get(Assignment, assignment_id)
    if not item or item.status == 'draft' or not db.get(AssignmentRecipient, (assignment_id, user.id)):
        raise HTTPException(404, '作业不存在。')
    if item.status != 'published' or date.fromisoformat(item.due_date) < date.today():
        raise HTTPException(409, '作业已截止或归档，不能修改或提交。')
    classroom = db.get(Classroom, item.class_id)
    member = db.get(ClassMember, (item.class_id, user.id))
    if not classroom or classroom.archived or not member or not member.active:
        raise HTTPException(409, '班级已归档或您已移出班级，历史作业只读。')
    key = f'{assignment_id}:{user.id}'
    submission = db.get(Submission, key)
    if submission:
        submission.answer = data.answer
        submission.created_at = now()
        submission.version += 1
    else:
        db.add(Submission(id=key, assignment_id=item.id, student_id=user.id, answer=data.answer, created_at=now(), version=1))
    db.commit()
    return assignment_data(item, db, user)


@router.put('/assignments/{assignment_id}/submissions/{student_id}/review')
def review_submission(assignment_id: str, student_id: str, data: ReviewInput, db: Session = Depends(write_db), user: User = Depends(require_role('teacher'))):
    item = owned(db, Assignment, assignment_id, user)
    if item.status != 'published':
        raise HTTPException(409, '仅已发布且未归档的作业可批改。')
    ensure_class_writable(item, db, user)
    submission = db.get(Submission, f'{assignment_id}:{student_id}')
    if not submission:
        raise HTTPException(404, '学生尚未提交作答。')
    if submission.version != data.version:
        raise HTTPException(409, '学生已修改作答，请刷新后复核新版本。')
    review = db.scalar(select(Review).where(Review.submission_id == submission.id, Review.version == data.version))
    if not review:
        review = Review(id=str(uuid4()), submission_id=submission.id, teacher_id=user.id, version=data.version, answer_snapshot=submission.answer)
        db.add(review)
    review.comment, review.status, review.reviewed_at = data.comment, data.status, now()
    db.commit()
    return assignment_data(item, db, user)
