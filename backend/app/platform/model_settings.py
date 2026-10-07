"""Per-account local API configuration. Secrets use Windows user DPAPI."""
import base64
import ctypes
import hashlib
import json
import os
from pathlib import Path
import threading
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field, field_validator
from .auth import Input, current_user
from . import database
from .database import User
from ..ai.config import load_settings, personal_settings
from ..ai.llm import chat, ModelCallFailed, ModelUnavailable

router = APIRouter(prefix='/api/model-settings', tags=['model-settings'])
lock = threading.RLock()


def config_path(user_id):
    database_path = database.engine.url.database
    root = Path(os.getenv('SHUBAN_API_SETTINGS_DIR') or (Path(database_path).resolve().parent if database.engine.dialect.name == 'sqlite' and database_path != ':memory:' else database.ROOT / 'backend'))
    return root / ('.env.api-settings-' + hashlib.sha256(user_id.encode()).hexdigest())


def crypt(data: bytes, decrypt=False):
    if os.name != 'nt':
        raise HTTPException(503, '当前版本的密钥保存需要 Windows 数据保护服务。')
    class Blob(ctypes.Structure):
        _fields_ = [('size', ctypes.c_ulong), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    fn = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not fn(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise HTTPException(503, '无法读取或保存本机加密配置，请清除配置后重新填写。')
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        ctypes.windll.kernel32.LocalFree(ctypes.cast(target.data, ctypes.c_void_p))


def read_config(user_id):
    path = config_path(user_id)
    with lock:
        if not path.exists():
            return None
        try:
            return json.loads(crypt(base64.b64decode(path.read_bytes()), decrypt=True))
        except HTTPException:
            raise
        except (ValueError, OSError):
            raise HTTPException(503, '本机 API 配置无法读取，请清除后重新填写。') from None


class ModelInput(Input):
    base_url: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=120)
    vision_model: str = Field(default='', max_length=120)
    api_key: str = Field(default='', max_length=1024, repr=False)

    @field_validator('base_url')
    @classmethod
    def url_valid(cls, value):
        value = value.strip().rstrip('/')
        url = urlsplit(value)
        if not url.hostname or url.username or url.password or url.query or url.fragment or (url.scheme != 'https' and not (url.scheme == 'http' and url.hostname in ('localhost', '127.0.0.1', '::1'))):
            raise ValueError('请填写HTTPS API地址（本机服务可用HTTP），不要包含密钥、查询参数或账号信息')
        return value

    @field_validator('model', 'vision_model', 'api_key')
    @classmethod
    def clean(cls, value):
        if any(ord(c) < 32 for c in value):
            raise ValueError('配置不能包含换行或控制字符')
        return value.strip()


def candidate(data, user):
    old = read_config(user.id)
    key = data.api_key
    if not key and old:
        if old['base_url'] != data.base_url:
            raise HTTPException(422, '更改API地址时请重新填写密钥，避免将原密钥发送到其他服务。')
        key = old['api_key']
    if not key or not data.model:
        raise HTTPException(422, '请填写API Key和模型名称。')
    return dict(base_url=data.base_url, model=data.model, vision_model=data.vision_model or data.model, api_key=key)


@router.get('')
def get_config(user: User = Depends(current_user)):
    saved = read_config(user.id)
    return {'configured': bool(saved), 'base_url': saved['base_url'] if saved else 'https://api.deepseek.com',
            'model': saved['model'] if saved else 'deepseek-flash',
            'vision_model': saved['vision_model'] if saved else 'deepseek-flash',
            'has_key': bool(saved and saved['api_key']), 'shared_account': user.is_demo}


@router.put('')
def save_config(data: ModelInput, user: User = Depends(current_user)):
    with lock:
        value = candidate(data, user)
        path = config_path(user.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_name(path.name + '.tmp')
        try:
            temp.write_bytes(base64.b64encode(crypt(json.dumps(value).encode())))
            temp.replace(path)
        finally:
            temp.unlink(missing_ok=True)
    return get_config(user)


@router.delete('')
def clear_config(user: User = Depends(current_user)):
    with lock:
        config_path(user.id).unlink(missing_ok=True)
    return {'ok': True}


@router.post('/test')
def test_config(data: ModelInput, user: User = Depends(current_user)):
    value = candidate(data, user)
    token = personal_settings.set(value)
    try:
        chat([{'role': 'user', 'content': '请只回复 OK，用于测试API连接。'}], load_settings())
        return {'ok': True, 'message': '连接成功，模型已返回文字回复。此测试不验证图片识别。'}
    except (ModelCallFailed, ModelUnavailable):
        raise HTTPException(502, '连接测试失败，请检查API地址、密钥、模型名称、账户额度或网络。') from None
    finally:
        personal_settings.reset(token)
