import hashlib
import hmac
import os
import secrets
import time
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DBSession

from .database import Session, User, get_db

router = APIRouter(prefix='/api/auth', tags=['auth'])
COOKIE = 'shuxue_session'
SECURE_COOKIE = os.getenv('COOKIE_SECURE', 'false').lower() == 'true'


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 260000).hex()
    return f'{salt}${digest}'


def verify_password(password: str, stored: str) -> bool:
    salt, expected = stored.split('$')
    actual = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 260000).hex()
    return hmac.compare_digest(actual, expected)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def public_user(user: User):
    return {'id': user.id, 'username': user.username, 'name': user.name, 'role': user.role}


def current_user(request: Request, db: DBSession = Depends(get_db)) -> User:
    session = db.get(Session, token_hash(request.cookies.get(COOKIE, '')))
    if not session or session.expires <= int(time.time()):
        raise HTTPException(401, '登录已过期，请重新登录。')
    user = db.get(User, session.user_id)
    if not user:
        raise HTTPException(401, '账号不存在。')
    return user


def require_role(role: str):
    def check(user: User = Depends(current_user)):
        if user.role != role:
            raise HTTPException(403, '当前身份没有此操作权限。')
        return user
    return check


class LoginInput(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=128)
    role: Literal['student', 'teacher']
    remember: bool = False


@router.post('/login')
def login(data: LoginInput, request: Request, response: Response, db: DBSession = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == data.username.strip()))
    if not user or not verify_password(data.password, user.password_hash) or user.role != data.role:
        raise HTTPException(401, '账号、密码或所选身份不正确，请检查后重试。')
    old = request.cookies.get(COOKIE)
    if old:
        db.execute(delete(Session).where(Session.token_hash == token_hash(old)))
    now = int(time.time())
    db.execute(delete(Session).where(Session.expires <= now))
    lifetime = 7 * 86400 if data.remember else 8 * 3600
    token = secrets.token_urlsafe(32)
    db.add(Session(token_hash=token_hash(token), user_id=user.id, expires=now + lifetime))
    db.commit()
    response.set_cookie(COOKIE, token, httponly=True, secure=SECURE_COOKIE, samesite='strict',
                        max_age=lifetime if data.remember else None, path='/')
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
