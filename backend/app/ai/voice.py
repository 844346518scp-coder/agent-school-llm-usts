"""B 模块语音服务适配（9/21–24 规划中的「语音服务适配」）。

分工定位：

- 会议约定语音输入归 A/C，**B 负责服务端适配层**：转写调用、入参校验、结果结构化与术语纠错。
- 没有配置语音服务时如实返回 503 并给出浏览器原生方案说明，**绝不返回编造的转写文本**。
- 语音转写只是“题目草稿”来源，和拍照识别一样必须由学生确认后才能进入问答/保存流程
  （`requires_confirmation=true`）。

术语纠错为什么放在后端：口语转写常把“x 的平方”写成“x 的平房/平方”、把“根号”写成“根号/跟号”，
这里用一份可复核的词表做确定性替换，并把每条替换都回传给前端展示，学生能看见“改了什么”。
"""
from __future__ import annotations

import base64
import binascii
import re
from urllib.parse import urlsplit

import httpx

from . import knowledge, resilience
from .config import AgentSettings, load_settings
from .llm import ModelCallFailed, ModelUnavailable

AUDIO_MEDIA_TYPES = (
    'audio/mpeg', 'audio/mp3', 'audio/wav', 'audio/x-wav', 'audio/webm',
    'audio/ogg', 'audio/mp4', 'audio/m4a', 'audio/x-m4a',
)

MAX_AUDIO_BYTES = 20 * 1024 * 1024
MIN_AUDIO_BYTES = 512
MAX_DURATION_SECONDS = 120

_EXTENSIONS = {
    'audio/mpeg': 'mp3', 'audio/mp3': 'mp3', 'audio/wav': 'wav', 'audio/x-wav': 'wav',
    'audio/webm': 'webm', 'audio/ogg': 'ogg', 'audio/mp4': 'm4a', 'audio/m4a': 'm4a',
    'audio/x-m4a': 'm4a',
}


class VoiceUnavailable(RuntimeError):
    """未配置语音服务，不能转写（调用方应返回 503 并说明原因）。"""


def decode_audio(payload: str) -> bytes:
    """严格解 base64；非法字符直接报错，不把脏数据送给语音服务。"""
    cleaned = ''.join((payload or '').split())
    try:
        return base64.b64decode(cleaned, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError('audio_base64 不是合法的 base64 数据') from exc


def detect_audio_type(raw: bytes) -> str | None:
    """按文件头判断音频格式：不接受伪装成音频的其它载荷。"""
    if raw.startswith(b'ID3') or raw[:2] in (b'\xff\xfb', b'\xff\xf3', b'\xff\xf2', b'\xff\xfa'):
        return 'audio/mpeg'
    if raw.startswith(b'RIFF') and raw[8:12] == b'WAVE':
        return 'audio/wav'
    if raw.startswith(b'\x1aE\xdf\xa3'):
        return 'audio/webm'
    if raw.startswith(b'OggS'):
        return 'audio/ogg'
    if len(raw) > 12 and raw[4:8] == b'ftyp':
        return 'audio/mp4'
    return None


def check_audio(payload: str, media_type: str, duration_seconds: float | None = None) -> dict:
    """校验音频载荷，返回可安全送入适配层的中间结果（失败抛 ValueError）。"""
    normalized = (media_type or '').strip().lower()
    if normalized == 'audio/mpeg3':
        normalized = 'audio/mpeg'
    if normalized not in AUDIO_MEDIA_TYPES:
        raise ValueError('仅支持 MP3 / WAV / WEBM / OGG / M4A 音频')
    raw = decode_audio(payload)
    if len(raw) < MIN_AUDIO_BYTES:
        raise ValueError('音频数据过小，无法转写')
    if len(raw) > MAX_AUDIO_BYTES:
        raise ValueError('音频过大，请压缩或分段后重试（单段不超过 20 MB）')
    detected = detect_audio_type(raw)
    if detected is None:
        raise ValueError('音频数据缺少 MP3/WAV/WEBM/OGG/M4A 文件头，无法转写')
    if duration_seconds is not None and duration_seconds > MAX_DURATION_SECONDS:
        raise ValueError(f'单段语音请控制在 {MAX_DURATION_SECONDS} 秒以内')
    return {
        'bytes': raw,
        'declared_media_type': normalized,
        'media_type': detected,
        'size': len(raw),
        'duration_seconds': duration_seconds,
    }


# 口语 → 数学记号。key 会按长度倒序匹配，保证“乘以”不会被“乘”抢先替换。
TERM_MAP: tuple[tuple[str, str], ...] = (
    ('趋近于', '→'), ('趋于', '→'), ('无穷大', '∞'), ('无穷小', '无穷小'),
    ('自然对数', 'ln'), ('对数', 'ln'), ('以e为底', 'e'), ('平方', '^2'), ('立方', '^3'),
    ('根号', '√'), ('开方', '√'), ('乘以', '×'), ('乘', '×'), ('除以', '÷'),
    ('等于', '='), ('正弦', 'sin'), ('余弦', 'cos'), ('正切', 'tan'), ('派', 'π'),
    ('艾克斯', 'x'), ('阿尔法', 'α'), ('贝塔', 'β'), ('西格玛', 'Σ'), ('极限', '极限'),
)

FILLERS = ('嗯', '那个', '然后呢', '这个这个')

_TERM_PATTERN = re.compile('|'.join(re.escape(term) for term, _ in sorted(TERM_MAP, key=lambda item: -len(item[0]))))
_TERM_LOOKUP = dict(TERM_MAP)


def normalize_transcript(text: str) -> dict:
    """把口语转写收敛成数学写法，并回传每条替换，便于学生核对。"""
    original = (text or '').strip()
    counted: dict[str, int] = {}

    def replace(match: re.Match) -> str:
        term = match.group(0)
        counted[term] = counted.get(term, 0) + 1
        return _TERM_LOOKUP.get(term, term)

    converted = _TERM_PATTERN.sub(replace, original)
    for filler in FILLERS:
        converted = converted.replace(filler, '')
    converted = re.sub(r'\s+', ' ', converted).strip()
    # 全角数字与常见全角符号转半角，避免学生看到“１＋２”这类字符。
    converted = converted.translate(str.maketrans('０１２３４５６７８９＋－＝（），．', '0123456789+-=(),.'))
    corrections = [
        {'from': term, 'to': _TERM_LOOKUP[term], 'count': count}
        for term, count in sorted(counted.items(), key=lambda item: item[0])
    ]
    warnings: list[str] = []
    if not converted:
        warnings.append('转写结果为空，请重录或改用键盘输入。')
    if original and not corrections:
        warnings.append('未发现需要替换的口语词，已按原转写文本返回。')
    return {
        'text': converted,
        'original_text': original,
        'corrections': corrections,
        'changed': converted != original,
        'warnings': warnings,
    }


def status(settings: AgentSettings | None = None) -> dict:
    """语音能力探针：只说是否可用与走哪套凭据，不返回密钥。"""
    settings = settings or load_settings()
    host = None
    if settings.voice_base_url:
        try:
            parts = urlsplit(settings.voice_base_url)
            host = f'{parts.scheme}://{parts.hostname}' if parts.hostname else None
        except ValueError:
            host = None
    return {
        'ready': settings.voice_ready,
        'credential_source': settings.voice_credential_source,
        'model': settings.voice_model or None,
        'endpoint': host,
        'timeout_seconds': settings.voice_timeout,
        'limits': {
            'formats': list(AUDIO_MEDIA_TYPES),
            'max_bytes': MAX_AUDIO_BYTES,
            'max_duration_seconds': MAX_DURATION_SECONDS,
        },
        'text_to_speech': False,
        'browser_fallback': {
            'available': True,
            'method': 'Web Speech API（Chrome/Edge 的 SpeechRecognition）',
            'note': '浏览器本地识别不需要服务端凭据，可作为无语音服务时的输入方式；'
                    '识别质量取决于浏览器与麦克风，且结果同样需要学生确认。',
        },
        'note': '服务端只做转写适配与术语纠错，不保存音频；未配置语音服务时返回 503，不返回编造文本。',
    }


def _extension(media_type: str) -> str:
    return _EXTENSIONS.get(media_type, 'webm')


def transcribe(checked: dict, settings: AgentSettings | None = None,
               language: str = 'zh', hint: str = '') -> dict:
    """调用 OpenAI 兼容的 ``/audio/transcriptions``；失败抛 ModelCallFailed。"""
    settings = settings or load_settings()
    if not settings.voice_ready:
        raise VoiceUnavailable(
            '未配置语音服务（VOICE_BASE_URL / VOICE_API_KEY / VOICE_MODEL，'
            '也可复用 MODEL_* 凭据）；演示模式不会返回编造的转写结果。'
        )
    media_type = checked['media_type']
    endpoint = f'{settings.voice_base_url}/audio/transcriptions'

    def call() -> str:
        files = {'file': (f'clip.{_extension(media_type)}', checked['bytes'], media_type)}
        data = {'model': settings.voice_model, 'language': language}
        if hint:
            data['prompt'] = hint[:200]
        try:
            with httpx.Client(timeout=settings.voice_timeout) as client:
                response = client.post(endpoint, headers={'Authorization': f'Bearer {settings.voice_api_key}'},
                                       files=files, data=data)
        except httpx.HTTPError as exc:
            raise ModelCallFailed('语音服务连接失败或超时。') from exc
        if response.status_code >= 400:
            raise ModelCallFailed(f'语音服务返回 HTTP {response.status_code}。')
        try:
            payload = response.json()
        except ValueError:
            payload = {'text': response.text}
        if isinstance(payload, dict):
            text = payload.get('text')
        else:
            text = None
        if not isinstance(text, str) or not text.strip():
            raise ModelCallFailed('语音服务返回的转写内容为空。')
        return text.strip()

    raw, meta = resilience.call_model(call, endpoint='POST /api/agent/voice/transcribe')
    normalized = normalize_transcript(raw)
    return {
        'mode': 'live',
        'notice': None,
        'raw_text': raw,
        'text': normalized['text'],
        'corrections': normalized['corrections'],
        'warnings': normalized['warnings'],
        'changed': normalized['changed'],
        'suggested_topic': knowledge.suggest_topic(normalized['text']),
        'requires_confirmation': True,
        'attempts': meta['attempts'],
        'method': '服务端语音服务转写 + 本地术语纠错（纠错条目可复核）',
    }


def mock_unavailable(settings: AgentSettings | None = None) -> dict:
    """未配置语音服务时的说明载荷，供路由拼进 503 的 detail。"""
    return status(settings)
