"""B 模块多题切分：把一次拍照/语音得到的整段文本切成若干道题（草稿，必须逐题确认）。

为什么需要：拍照识别与语音转写各返回**一段**文本，学生一次拍到两道题时无法直接提问。
这里用可解释的规则切分，和识别一样只给草稿：`requires_confirmation=true`，
学生逐题核对（改题、选主题）后再调用 `/api/conversations` 保存或提问。

规则（按优先级）：

1. 行首序号：`1.` `1、` `1)` `（1）` `第1题` `第一题` `①`，命中就按序号切；
2. 没有序号时，按句末标点切句，若下一句以常见的题目动词开头（求 / 计算 / 证明 / 判断 / 讨论 / 设 / 已知 / 解）
   且前一段已有实质内容，就当作新题；
3. 仍然只有一段时，如实返回单题并提示“没有识别到分题标记，请手动拆分”。

不做的事：不猜题目难度、不代替学生确认；模型不参与切分（避免把变式条件切丢）。
"""
from __future__ import annotations

import re

from . import knowledge

MAX_ITEMS = 10
MIN_FRAGMENT = 4

NUMBERED = re.compile(r'^\s*(?:第\s*)?(\d{1,2})\s*[、.．)）:：]')
CN_NUMBERED = re.compile(r'^\s*第\s*([一二三四五六七八九十]+)\s*题')
CIRCLED = re.compile(r'^\s*([①②③④⑤⑥⑦⑧⑨⑩])')
SENTENCE_SPLIT = re.compile(r'(?<=[。？?；;])')
QUESTION_STARTERS = ('求', '计算', '证明', '判断', '讨论', '设', '已知', '解', '试', '说明')


def _is_marker(line: str) -> bool:
    return bool(NUMBERED.match(line) or CN_NUMBERED.match(line) or CIRCLED.match(line))


def _strip_marker(line: str) -> str:
    for pattern in (NUMBERED, CN_NUMBERED, CIRCLED):
        cleaned = pattern.sub('', line, count=1)
        if cleaned != line:
            return cleaned.strip()
    return line.strip()


def _merge_short(parts: list[str]) -> list[str]:
    merged: list[str] = []
    for part in parts:
        text = part.strip()
        if not text:
            continue
        if merged and len(text) < MIN_FRAGMENT:
            merged[-1] = f'{merged[-1]}{text}'
            continue
        merged.append(text)
    return merged


def _split_by_markers(lines: list[str]) -> list[str] | None:
    has_marker = any(_is_marker(line) for line in lines)
    if not has_marker:
        return None
    parts: list[str] = []
    for line in lines:
        if _is_marker(line):
            parts.append(_strip_marker(line))
            continue
        if parts:
            parts[-1] = f'{parts[-1]} {line.strip()}'.strip()
        else:
            parts.append(line.strip())
    return _merge_short(parts)


def _split_by_sentence(text: str) -> list[str]:
    parts: list[str] = []
    for sentence in SENTENCE_SPLIT.split(text):
        cleaned = sentence.strip()
        if not cleaned:
            continue
        starts_question = cleaned.startswith(QUESTION_STARTERS)
        if parts and starts_question and len(parts[-1]) >= MIN_FRAGMENT:
            parts.append(cleaned)
        elif parts and not starts_question and len(cleaned) < MIN_FRAGMENT:
            parts[-1] = f'{parts[-1]} {cleaned}'.strip()
        else:
            parts.append(cleaned)
    return _merge_short(parts)


def split(text: str, max_items: int = MAX_ITEMS) -> dict:
    """切分多题文本；返回草稿题目列表（每题都带建议主题，需学生确认）。"""
    cleaned = (text or '').strip()
    limit = max(1, min(MAX_ITEMS, int(max_items)))
    result = {
        'mode': 'demo',
        'notice': None,
        'requires_confirmation': True,
        'method': '规则切分（行首序号 / 题目动词，未调用模型）',
        'rule': '序号优先；没有序号时按句末标点与题目动词切分；切分结果只是草稿。',
    }
    if not cleaned:
        result |= {'items': [], 'total': 0, 'truncated': False,
                   'notice': '没有收到可切分的文本，请先拍照识别或语音转写。'}
        return result

    lines = [line for line in cleaned.splitlines()]
    parts = _split_by_markers(lines)
    strategy = 'markers'
    if not parts:
        parts = _split_by_sentence(cleaned)
        strategy = 'sentences' if len(parts) > 1 else 'single'

    truncated = len(parts) > limit
    items = [{
        'index': index,
        'text': part,
        'char_count': len(part),
        'suggested_topic': knowledge.suggest_topic(part),
    } for index, part in enumerate(parts[:limit], 1)]

    if strategy == 'single':
        result['notice'] = '没有识别到分题标记，已按整段作为一道题返回；如果其实是多道题，请手动拆分。'
    if truncated:
        result['notice'] = (f"检测到超过 {limit} 道题，只返回前 {limit} 道；"
                            '请分批确认，避免把后面的条件漏掉。')
    result |= {
        'items': items,
        'total': len(items),
        'truncated': truncated,
        'strategy': strategy,
        'confirm_endpoint': '/api/conversations',
        'note': '每道题都要学生确认或修改后再提问/保存；切分不会自动入库。',
    }
    return result
