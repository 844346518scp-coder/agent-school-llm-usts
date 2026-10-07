"""Student enrollment and private teacher/student mail."""
from datetime import datetime, timezone
import secrets
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field, field_validator
from sqlalchemy import String, Text, Boolean, Integer, select, or_, and_, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session
from ..platform.auth import Input, current_user, require_role
from ..platform.database import User, Classroom, ClassMember, get_db, write_db

class CommunityBase(DeclarativeBase):
    pass

class CommunityVersion(CommunityBase):
    __tablename__ = 'community_schema_migrations'
    version: Mapped[int] = mapped_column(Integer, primary_key=True)

class ClassCode(CommunityBase):
    __tablename__ = 'class_join_codes'
    class_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    code: Mapped[str] = mapped_column(String(12), unique=True)

class Mail(CommunityBase):
    __tablename__ = 'community_mail'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sender_id: Mapped[str] = mapped_column(String(40), index=True)
    recipient_id: Mapped[str] = mapped_column(String(40), index=True)
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(String(40))
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    client_id: Mapped[str] = mapped_column(String(100), unique=True)

router = APIRouter(prefix='/api', tags=['community'])

def ensure_code(db, class_id, rotate=False):
    item = db.get(ClassCode, class_id)
    if item and not rotate:
        return item.code
    while True:
        code = f'{secrets.randbelow(1000000):06d}'
        if not db.scalar(select(ClassCode.class_id).where(ClassCode.code == code)):
            break
    if item: item.code = code
    else: db.add(ClassCode(class_id=class_id, code=code))
    db.flush()
    return code

class JoinInput(Input):
    code: str = Field(min_length=1, max_length=20)

def join_class(db, user, code):
    code = code.strip().upper()
    link = db.scalar(select(ClassCode).where(ClassCode.code == code))
    item = db.get(Classroom, link.class_id) if link else None
    teacher = db.get(User, item.teacher_id) if item else None
    if not item or item.archived or not teacher or not teacher.active:
        raise HTTPException(404, '班级码无效或班级已关闭，请向老师核实。')
    member = db.get(ClassMember, (item.id, user.id))
    if member and not member.active:
        raise HTTPException(403, '你已被移出该班，请联系老师恢复成员身份。')
    if not member:
        db.add(ClassMember(class_id=item.id, student_id=user.id, active=True))
    return {'id': item.id, 'name': item.name, 'course': item.course, 'term': item.term, 'teacher_name': teacher.name}

@router.post('/student/classes/join')
def enroll(data: JoinInput, db: Session = Depends(write_db), user: User = Depends(require_role('student'))):
    result = join_class(db, user, data.code)
    db.commit()
    return result

@router.get('/student/classes')
def my_classes(db: Session = Depends(get_db), user: User = Depends(require_role('student'))):
    rows = db.execute(select(Classroom, ClassMember).join(ClassMember, ClassMember.class_id == Classroom.id).where(ClassMember.student_id == user.id)).all()
    return [{'id': c.id, 'name': c.name, 'course': c.course, 'term': c.term, 'teacher_name': db.get(User, c.teacher_id).name,
             'active': m.active, 'archived': c.archived} for c, m in rows]

@router.post('/classes/{class_id}/join-code')
def rotate_code(class_id: str, db: Session = Depends(write_db), user: User = Depends(require_role('teacher'))):
    from .classes import owned_class
    owned_class(db, class_id, user, writable=True)
    result = ensure_code(db, class_id, rotate=True)
    db.commit()
    return {'code': result}

def can_message(db, sender, recipient):
    if not recipient or not recipient.active or sender.role == recipient.role:
        return False
    teacher, student = (sender, recipient) if sender.role == 'teacher' else (recipient, sender)
    return db.scalar(select(Classroom.id).join(ClassMember, ClassMember.class_id == Classroom.id).where(
        Classroom.teacher_id == teacher.id, Classroom.archived.is_(False),
        ClassMember.student_id == student.id, ClassMember.active.is_(True)).limit(1)) is not None

@router.get('/mail/contacts')
def contacts(db: Session = Depends(get_db), user: User = Depends(current_user)):
    if user.role == 'teacher':
        ids = set(db.scalars(select(ClassMember.student_id).join(Classroom, Classroom.id == ClassMember.class_id).where(Classroom.teacher_id == user.id, Classroom.archived.is_(False), ClassMember.active.is_(True))))
    else:
        ids = set(db.scalars(select(Classroom.teacher_id).join(ClassMember, ClassMember.class_id == Classroom.id).where(ClassMember.student_id == user.id, ClassMember.active.is_(True), Classroom.archived.is_(False))))
    ids.update(db.scalars(select(Mail.sender_id).where(Mail.recipient_id == user.id)))
    ids.update(db.scalars(select(Mail.recipient_id).where(Mail.sender_id == user.id)))
    people = db.scalars(select(User).where(User.id.in_(ids)).order_by(User.name)).all() if ids else []
    return [{'id': p.id, 'name': p.name, 'role': p.role, 'can_send': can_message(db, user, p),
             'unread': db.scalar(select(func.count()).select_from(Mail).where(Mail.sender_id == p.id, Mail.recipient_id == user.id, Mail.read.is_(False)))} for p in people]

class MessageInput(Input):
    recipient_id: str = Field(min_length=1, max_length=40)
    content: str = Field(min_length=1, max_length=3000)
    client_id: str = Field(min_length=1, max_length=50)
    @field_validator('content')
    @classmethod
    def nonempty(cls, v):
        if not v.strip(): raise ValueError('信件不能为空')
        return v.strip()

def mail_data(m, user):
    return {'id': m.id, 'sender_id': m.sender_id, 'recipient_id': m.recipient_id, 'content': m.content,
            'created_at': m.created_at, 'read': m.read, 'mine': m.sender_id == user.id}

@router.post('/mail/messages', status_code=201)
def send(data: MessageInput, db: Session = Depends(write_db), user: User = Depends(current_user)):
    recipient = db.get(User, data.recipient_id)
    if not can_message(db, user, recipient):
        raise HTTPException(403, '仅可与当前班级中的老师或学生通信。')
    key = user.id + ':' + data.client_id
    old = db.scalar(select(Mail).where(Mail.client_id == key))
    if old:
        if old.recipient_id != data.recipient_id or old.content != data.content:
            raise HTTPException(409, '发送标识已使用，请刷新后重试。')
        return mail_data(old, user)
    item = Mail(sender_id=user.id, recipient_id=recipient.id, content=data.content, client_id=key,
                created_at=datetime.now(timezone.utc).isoformat(), read=False)
    db.add(item); db.commit()
    return mail_data(item, user)

@router.get('/mail/messages/{peer_id}')
def messages(peer_id: str, before: int | None = Query(None, ge=1), db: Session = Depends(get_db), user: User = Depends(current_user)):
    pair = or_(and_(Mail.sender_id == user.id, Mail.recipient_id == peer_id), and_(Mail.sender_id == peer_id, Mail.recipient_id == user.id))
    query = select(Mail).where(pair)
    if before is not None: query = query.where(Mail.id < before)
    rows = list(db.scalars(query.order_by(Mail.id.desc()).limit(100)))
    return [mail_data(m, user) for m in reversed(rows)]

class ReadInput(Input):
    through_id: int = Field(ge=1)

@router.post('/mail/messages/{peer_id}/read')
def mark_read(peer_id: str, data: ReadInput, db: Session = Depends(write_db), user: User = Depends(current_user)):
    for m in db.scalars(select(Mail).where(Mail.sender_id == peer_id, Mail.recipient_id == user.id, Mail.id <= data.through_id, Mail.read.is_(False))):
        m.read = True
    db.commit()
    return {'ok': True}
