"""B 模块基础诊断：规则优先、可解释，模型只做可选润色。

设计取舍：
- 薄弱知识点由本地规则 + 检索给出，结论可追溯（哪些关键词触发的），便于教师端复核；
- 真实模型只用于把结论写成更自然的学情总结；调用失败时保留规则结论并如实标注 demo。
"""
from __future__ import annotations

from typing import Iterable, Sequence

from . import knowledge, prompts
from .config import AgentSettings, load_settings
from .llm import ModelCallFailed, ModelUnavailable, chat, extract_json

MAX_WEAK_POINTS = 3
MAX_PRACTICE = 3


def _collect_text(question: str, answer: str, wrong_points: Iterable[str]) -> str:
    parts = [question or '', answer or '', ' '.join(wrong_points or [])]
    return ' '.join(part for part in parts if part)


def _signals_for(point: knowledge.KnowledgePoint, text: str) -> list[str]:
    return [signal for signal in point.signals if signal and signal in text]


def weak_points(text: str, topic: str | None = None) -> list[dict]:
    """按命中信号数量给出薄弱知识点候选（确定性、可复核）。"""
    wanted_topic = knowledge.normalize_topic(topic)
    scored: list[dict] = []
    for point in knowledge.KNOWLEDGE_POINTS:
        hits = _signals_for(point, text)
        if not hits:
            continue
        confidence = min(0.9, 0.35 + 0.15 * len(hits))
        if wanted_topic and point.topic == wanted_topic:
            confidence = min(0.95, confidence + 0.05)
        scored.append(
            {
                'id': point.id,
                'title': point.title,
                'topic': point.topic,
                'reason': '出现信号：' + '、'.join(hits[:3]),
                'confidence': round(confidence, 2),
                'source': point.source,
                'verified': point.verified,
            }
        )
    scored.sort(key=lambda item: (-item['confidence'], item['id']))
    return scored[:MAX_WEAK_POINTS]


def _rule_summary(weak: Sequence[dict]) -> str:
    if not weak:
        return '规则诊断：未发现明显薄弱点信号，建议先完成一道基础例题再回来诊断。'
    detail = '；'.join(f'{item["title"]}（规则匹配分 {item["confidence"]}）' for item in weak)
    return f'规则提示：以下内容需要核对，不能据此确定掌握程度： {detail}。'


def _rule_next_step(weak: Sequence[dict]) -> str:
    if not weak:
        return '先做一道基础例题，把解题步骤写下来，再提交诊断。'
    return f'建议先复习「{weak[0]["title"]}」，完成下方变式练习后重新提交。'


def diagnose(
    question: str = '',
    answer: str = '',
    wrong_points: Sequence[str] = (),
    topic: str | None = None,
    settings: AgentSettings | None = None,
) -> dict:
    """返回结构化诊断结果；``mode`` 表示结论来源，demo 即规则结果。"""
    settings = settings or load_settings()
    text = _collect_text(question, answer, wrong_points)

    weak = weak_points(text, topic) if text.strip() else []
    evidence = knowledge.retrieve(text, topic=topic, top_k=settings.top_k, min_score=settings.min_score) if text.strip() else []

    practice = knowledge.practice_for([item['id'] for item in weak] or [hit.point.id for hit in evidence], MAX_PRACTICE)

    summary = _rule_summary(weak)
    next_step = _rule_next_step(weak)
    mode = 'demo'
    notice = None

    if weak and settings.resolved_mode == 'live':
        try:
            raw = chat(prompts.build_diagnosis_messages(question, answer, wrong_points, evidence), settings)
        except (ModelUnavailable, ModelCallFailed) as exc:
            notice = f'模型润色失败，已使用规则结论（原因：{exc}）。'
        else:
            parsed = extract_json(raw)
            if parsed:
                summary = str(parsed.get('summary') or summary)
                next_step = str(parsed.get('next_step') or next_step)
                mode = 'live'
            else:
                notice = '模型返回未按约定给出 JSON，已使用规则结论。'

    return {
        'mode': mode,
        'notice': notice,
        'topic': knowledge.normalize_topic(topic),
        'weak_points': weak,
        'related_points': [hit.as_dict(index) for index, hit in enumerate(evidence, 1)],
        'suggested_practice': practice,
        'summary': summary,
        'next_step': next_step,
        'method': '规则关键词 + 本地 BM25 检索（可复核）；模型仅润色学情总结'
        if mode == 'live'
        else '规则关键词 + 本地 BM25 检索（可复核，未调用模型）',
    }


# 步骤反馈的规则表：命中关键词就提示对应的常见错误。
STEP_MISTAKE_HINTS = {
    '洛必达': '使用洛必达法则前先确认是 0/0 或 ∞/∞ 型，且分子分母可导。',
    '等价无穷小': '等价无穷小替换一般只在乘除结构中直接使用，加减结构里要先变形。',
    '0/0': '0/0 是不定式，不是结果，需要先约分、通分或有理化再求极限。',
    '链式法则': '复合函数求导要逐层求导，检查是否漏乘内层导数。',
    '左右导数': '分段函数在分界点要分别求左右导数，两者相等才可导。',
    '连续': '连续需要同时满足：在该点有定义、极限存在、极限值等于函数值。',
    '可导': '可导必连续，连续不一定可导；请检查引用可导性时是否已证明。',
    '极值': 'f′(x0)=0 只是极值的必要条件，还要看 f′ 的符号变化或二阶导。',
    '端点': '求闭区间最值要比较端点值与驻点处的函数值。',
    '直接代入': '不要直接代入 0 或 ∞，先判断是不是不定式。',
}

UNVERIFIABLE_HINT = '关键词规则不能判断这一步的对错；请对照引用的定义与要点自检。'
DEFAULT_NEXT_QUESTION = '这一步为什么成立？请说出用到的定义或定理。'


def step_feedback(
    question: str,
    step: str,
    steps: Sequence[str] = (),
    topic: str | None = None,
    settings: AgentSettings | None = None,
) -> dict:
    """判断学生提交的“某一步”。

    demo 模式关键词只用于生成自检提示，统一返回 unclear，不给出确定对错，
    避免把规则判断包装成真实的解题批改。
    """
    settings = settings or load_settings()
    evidence = (
        knowledge.retrieve(f'{question} {step}', topic=topic, top_k=settings.top_k, min_score=settings.min_score)
        if (step or '').strip()
        else []
    )
    flagged = [key for key in STEP_MISTAKE_HINTS if key in (step or '')]
    verdict = 'unclear'
    hint = STEP_MISTAKE_HINTS[flagged[0]] if flagged else UNVERIFIABLE_HINT
    next_question = DEFAULT_NEXT_QUESTION
    mode = 'demo'
    notice = (
        f'演示模式按关键词规则标出风险点：{flagged[0]}，结论需人工复核。'
        if flagged
        else '演示模式无法判定这一步是否正确，只提供自检提示。'
    )

    if settings.resolved_mode == 'live':
        try:
            raw = chat(prompts.build_step_feedback_messages(question, step, steps, evidence), settings)
        except (ModelUnavailable, ModelCallFailed) as exc:
            notice = f'模型调用失败，已改用规则结论（原因：{exc}）。'
        else:
            parsed = extract_json(raw)
            if parsed and parsed.get('verdict') in {'correct', 'incorrect', 'unclear'}:
                verdict = parsed['verdict']
                hint = str(parsed.get('hint') or hint)
                next_question = str(parsed.get('next_question') or next_question)
                mode = 'live'
                notice = None
            else:
                notice = '模型未按约定返回 JSON，已使用规则结论。'

    return {
        'mode': mode,
        'notice': notice,
        'verdict': verdict,
        'hint': hint,
        'next_question': next_question,
        'flagged': flagged,
        'references': [hit.as_dict(index) for index, hit in enumerate(evidence, 1)],
        'method': '模型逐步批改（只判断本次提交的这一步）' if mode == 'live' else '关键词规则 + 本地 BM25 检索（未调用模型）',
    }
