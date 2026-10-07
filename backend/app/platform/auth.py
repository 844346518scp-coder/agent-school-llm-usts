import hashlib
import hmac
import os
import secrets
import time
import re
from uuid import uuid4
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DBSession

from .database import Session, User, Classroom, ClassMember, get_db, write_db

router = APIRouter(prefix='/api/auth', tags=['auth'])
COOKIE = 'shuxue_session'
SECURE_COOKIE = os.getenv('COOKIE_SECURE', 'false').lower() == 'true'


def session_cookie(request: Request):
    # Separate HttpOnly cookies keep demonstration windows independent.
    scope = request.headers.get('X-Demo-Window', '')
    if scope and scope not in ('teacher', 'student-1', 'student-2', 'student-3'):
        raise HTTPException(422, '无效的演示窗口。')
    return COOKIE + ('_' + scope if scope else '')


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 260000).hex()
    return f'{salt}${digest}'


def verify_password(password: str, stored: str) -> bool:
    if '$' not in stored:
        return False
    salt, expected = stored.split('$', 1)
    actual = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 260000).hex()
    return hmac.compare_digest(actual, expected)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def public_user(user: User):
    return {key: getattr(user, key) for key in ('id', 'username', 'name', 'role', 'active', 'must_change_password', 'is_demo')}


def current_user(request: Request, db: DBSession = Depends(get_db)) -> User:
    session = db.get(Session, token_hash(request.cookies.get(session_cookie(request), '')))
    if not session or session.expires <= int(time.time()):
        raise HTTPException(401, '登录已过期，请重新登录。')
    user = db.get(User, session.user_id)
    if not user or not user.active:
        raise HTTPException(401, '账号不存在或已停用。')
    if user.must_change_password and request.url.path not in ('/api/auth/me', '/api/auth/password', '/api/auth/logout'):
        raise HTTPException(403, '请先修改临时密码，再使用教学功能。')
    return user


def require_role(role: str):
    def check(user: User = Depends(current_user)):
        if user.role != role:
            raise HTTPException(403, '当前身份没有此操作权限。')
        return user
    return check


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


def validate_password(value):
    if len(value) < 10 or not re.search(r'[A-Za-z]', value) or not re.search(r'[0-9]', value):
        raise ValueError('密码至少10字符，且同时包含英文字母和数字')
    return value


def validate_name(value):
    if not value.strip():
        raise ValueError('姓名不能为空')
    return value.strip()


class AccountInput(Input):
    username: str = Field(min_length=3, max_length=80)
    name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=10, max_length=128)

    @field_validator('username')
    @classmethod
    def username_valid(cls, value):
        if not re.fullmatch(r'[A-Za-z0-9_.-]{3,80}', value):
            raise ValueError('账号使用3–80位英文字母、数字、点、短横线或下划线')
        return value

    _name = field_validator('name')(validate_name)
    _password = field_validator('password')(validate_password)


class PasswordInput(Input):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)
    _password = field_validator('new_password')(validate_password)


class StudentRegistration(AccountInput):
    class_code: str = Field(default='', max_length=20)


@router.post('/register/student', status_code=201)
def register_student(data: StudentRegistration, request: Request, response: Response, db: DBSession = Depends(write_db)):
    user = create_user(db, AccountInput(**data.model_dump(exclude={'class_code'})), 'student')
    if data.class_code.strip():
        from ..teaching.community import join_class
        join_class(db, user, data.class_code)
    db.execute(delete(Session).where(Session.token_hash == token_hash(request.cookies.get(session_cookie(request), ''))))
    issue_session(db, user, response, request=request)
    db.commit()
    return public_user(user)


class ProfileInput(Input):
    name: str = Field(min_length=1, max_length=80)
    _name = field_validator('name')(validate_name)


class LoginInput(Input):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=128)
    role: Literal['student', 'teacher']
    remember: bool = False


def create_user(db, data: AccountInput, role, created_by=None, temporary=False):
    if db.scalar(select(User.id).where(User.username == data.username)):
        raise HTTPException(409, '账号已存在，请使用其他账号。')
    user = User(id=str(uuid4()), username=data.username, name=data.name,
                password_hash=hash_password(data.password), role=role,
                active=True, must_change_password=temporary, is_demo=False, created_by=created_by)
    db.add(user)
    db.flush()
    return user


def issue_session(db, user, response, remember=False, request=None):
    timestamp = int(time.time())
    db.execute(delete(Session).where(Session.expires <= timestamp))
    lifetime = 7 * 86400 if remember else 8 * 3600
    token = secrets.token_urlsafe(32)
    db.add(Session(token_hash=token_hash(token), user_id=user.id, expires=timestamp + lifetime))
    response.set_cookie(session_cookie(request) if request is not None else COOKIE, token, httponly=True, secure=SECURE_COOKIE, samesite='strict',
                        max_age=lifetime if remember else None, path='/')


@router.get('/setup')
def setup_status(db: DBSession = Depends(get_db)):
    return {'required': db.scalar(select(User.id).where(User.role == 'teacher', User.is_demo.is_(False)).limit(1)) is None}


def demo_enabled():
    return os.getenv('SHUBAN_DEMO_LOGIN', 'false').lower() == 'true'


@router.get('/demo')
def demo_status():
    return {'enabled': demo_enabled()}


class DemoLoginInput(Input):
    role: Literal['student', 'teacher']
    student: Literal[1, 2, 3] = 1


@router.post('/demo')
def demo_login(data: DemoLoginInput, request: Request, response: Response, db: DBSession = Depends(write_db)):
    if not demo_enabled():
        raise HTTPException(403, '当前服务未启用演示登录。')
    # Only these dedicated accounts may bypass passwords; never reuse real accounts.
    accounts = {}
    newly_created = set()
    for key, role, name in [('teacher', 'teacher', '演示老师'),
                             ('student', 'student', '演示同学'),
                             ('student-2', 'student', '演示同学 2'),
                             ('student-3', 'student', '演示同学 3')]:
        identity = 'quick-demo-' + key
        user = db.get(User, identity)
        if user is None:
            user = User(id=identity, username='demo-' + key + '-' + secrets.token_hex(4),
                        name=name, role=role, password_hash=hash_password(secrets.token_urlsafe(32)),
                        active=True, is_demo=True, must_change_password=False,
                        created_by='quick-demo-teacher' if role == 'student' else None)
            db.add(user)
            db.flush()
            newly_created.add(identity)
        accounts[key] = user
    selected = 'teacher' if data.role == 'teacher' else 'student' if data.student == 1 else f'student-{data.student}'
    for key in ('teacher', selected):
        user = accounts[key]
        if not user.is_demo or not user.active or user.must_change_password or user.role != ('teacher' if key == 'teacher' else 'student'):
            raise HTTPException(409, '演示账号已停用或转为正式账号，请使用账号密码登录。')
    classroom = db.get(Classroom, 'quick-demo-class')
    if classroom is None:
        classroom = Classroom(id='quick-demo-class', teacher_id=accounts['teacher'].id,
                              name='一键体验演示班', course='高等数学', term='演示学期', archived=False,
                              created_at=datetime.now(timezone.utc).isoformat())
        db.add(classroom)
        db.flush()
        newly_created.update(u.id for u in accounts.values() if u.role == 'student' and u.is_demo and u.active)
    if not classroom.archived and classroom.teacher_id == accounts['teacher'].id:
        for identity in newly_created:
            if accounts['teacher'].id != identity and not db.get(ClassMember, (classroom.id, identity)):
                db.add(ClassMember(class_id=classroom.id, student_id=identity, active=True))
    from ..teaching.community import ensure_code
    ensure_code(db, 'quick-demo-class')
    db.execute(delete(Session).where(Session.token_hash == token_hash(request.cookies.get(session_cookie(request), ''))))
    issue_session(db, accounts[selected], response, request=request)
    db.commit()
    return public_user(accounts[selected])


@router.post('/setup', status_code=201)
def setup(data: AccountInput, request: Request, response: Response, db: DBSession = Depends(write_db)):
    if db.scalar(select(User.id).where(User.role == 'teacher', User.is_demo.is_(False)).limit(1)):
        raise HTTPException(409, '教师账号已初始化，请登录。')
    user = create_user(db, data, 'teacher')
    db.execute(delete(Session).where(Session.token_hash == token_hash(request.cookies.get(session_cookie(request), ''))))
    issue_session(db, user, response, request=request)
    db.commit()
    return public_user(user)


@router.post('/teachers', status_code=201)
def create_teacher(data: AccountInput, db: DBSession = Depends(write_db), user: User = Depends(require_role('teacher'))):
    teacher = create_user(db, data, 'teacher', created_by=user.id, temporary=True)
    db.commit()
    return public_user(teacher)


@router.post('/password')
def change_password(data: PasswordInput, request: Request, response: Response, db: DBSession = Depends(write_db), user: User = Depends(current_user)):
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(403, '当前密码不正确。')
    if data.current_password == data.new_password:
        raise HTTPException(422, '新密码不能与当前密码相同。')
    user.password_hash = hash_password(data.new_password)
    user.must_change_password = False
    # A former publicly documented account becomes private only after password change.
    user.is_demo = False
    db.execute(delete(Session).where(Session.user_id == user.id))
    issue_session(db, user, response, request=request)
    db.commit()
    return public_user(user)


@router.patch('/profile')
def change_profile(data: ProfileInput, db: DBSession = Depends(write_db), user: User = Depends(current_user)):
    user.name = data.name
    db.commit()
    return public_user(user)


@router.post('/login')
def login(data: LoginInput, request: Request, response: Response, db: DBSession = Depends(write_db)):
    user = db.scalar(select(User).where(User.username == data.username.strip()))
    if not user or not user.active or not verify_password(data.password, user.password_hash) or user.role != data.role:
        raise HTTPException(401, '账号、密码或所选身份不正确，请检查后重试。')
    old = request.cookies.get(session_cookie(request))
    if old:
        db.execute(delete(Session).where(Session.token_hash == token_hash(old)))
    issue_session(db, user, response, data.remember, request=request)
    db.commit()
    return public_user(user)


@router.get('/me')
def me(user: User = Depends(current_user)):
    return public_user(user)


@router.post('/logout')
def logout(request: Request, response: Response, db: DBSession = Depends(get_db)):
    db.execute(delete(Session).where(Session.token_hash == token_hash(request.cookies.get(session_cookie(request), ''))))
    db.commit()
    response.delete_cookie(session_cookie(request), path='/', httponly=True, secure=SECURE_COOKIE, samesite='strict')
    return {'ok': True}
