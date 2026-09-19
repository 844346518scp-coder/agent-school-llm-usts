import hashlib
import hmac
import os
import secrets
import time
import re
from uuid import uuid4
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DBSession

from .database import Session, User, get_db, write_db

router = APIRouter(prefix='/api/auth', tags=['auth'])
COOKIE = 'shuxue_session'
SECURE_COOKIE = os.getenv('COOKIE_SECURE', 'false').lower() == 'true'


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
    session = db.get(Session, token_hash(request.cookies.get(COOKIE, '')))
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


def issue_session(db, user, response, remember=False):
    timestamp = int(time.time())
    db.execute(delete(Session).where(Session.expires <= timestamp))
    lifetime = 7 * 86400 if remember else 8 * 3600
    token = secrets.token_urlsafe(32)
    db.add(Session(token_hash=token_hash(token), user_id=user.id, expires=timestamp + lifetime))
    response.set_cookie(COOKIE, token, httponly=True, secure=SECURE_COOKIE, samesite='strict',
                        max_age=lifetime if remember else None, path='/')


@router.get('/setup')
def setup_status(db: DBSession = Depends(get_db)):
    return {'required': db.scalar(select(User.id).where(User.role == 'teacher').limit(1)) is None}


@router.post('/setup', status_code=201)
def setup(data: AccountInput, request: Request, response: Response, db: DBSession = Depends(write_db)):
    if db.scalar(select(User.id).where(User.role == 'teacher').limit(1)):
        raise HTTPException(409, '教师账号已初始化，请登录。')
    user = create_user(db, data, 'teacher')
    db.execute(delete(Session).where(Session.token_hash == token_hash(request.cookies.get(COOKIE, ''))))
    issue_session(db, user, response)
    db.commit()
    return public_user(user)


@router.post('/teachers', status_code=201)
def create_teacher(data: AccountInput, db: DBSession = Depends(write_db), user: User = Depends(require_role('teacher'))):
    teacher = create_user(db, data, 'teacher', created_by=user.id, temporary=True)
    db.commit()
    return public_user(teacher)


@router.post('/password')
def change_password(data: PasswordInput, response: Response, db: DBSession = Depends(write_db), user: User = Depends(current_user)):
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(403, '当前密码不正确。')
    if data.current_password == data.new_password:
        raise HTTPException(422, '新密码不能与当前密码相同。')
    user.password_hash = hash_password(data.new_password)
    user.must_change_password = False
    # A former publicly documented account becomes private only after password change.
    user.is_demo = False
    db.execute(delete(Session).where(Session.user_id == user.id))
    issue_session(db, user, response)
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
    old = request.cookies.get(COOKIE)
    if old:
        db.execute(delete(Session).where(Session.token_hash == token_hash(old)))
    issue_session(db, user, response, data.remember)
    db.commit()
    return public_user(user)


@router.get('/me')
def me(user: User = Depends(current_user)):
    return public_user(user)


@router.post('/logout')
def logout(request: Request, response: Response, db: DBSession = Depends(get_db)):
    db.execute(delete(Session).where(Session.token_hash == token_hash(request.cookies.get(COOKIE, ''))))
    db.commit()
    response.delete_cookie(COOKIE, path='/', httponly=True, secure=SECURE_COOKIE, samesite='strict')
    return {'ok': True}
