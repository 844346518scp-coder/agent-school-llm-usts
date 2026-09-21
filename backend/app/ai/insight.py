"""B 模块第二阶段：推荐练习、评价（费曼/自评）、阶段总结复习。

设计原则：

- 推荐与总结由**可核对的本地数据**得出（长期记忆 + 课程检索），demo 模式下不调用模型；
- live 模式下模型只润色文字表达，规则结论（掌握度、覆盖率、薄弱项）始终保留原样；
- 每条结论都给出依据与资料出处，教师与学生都能复核。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable, Sequence

from . import knowledge, prompts
from .config import AgentSettings, load_settings
from .llm import ModelCallFailed, ModelUnavailable, chat, extract_json

RECOMMEND_REASONS = {
    'weak': '负面证据较多，建议优先重练',
    'learning': '练过但还没稳住，再练一轮巩固',
    'unseen': '还没有练习记录，属于本阶段基础内容',
}

REVIEW_BANDS = (
    (0.6, '基本到位', 1),
    (0.3, '有遗漏', -1),
    (0.0, '需要重讲', -2),
)

MAX_ADVICE = 3


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _band_of(coverage: float) -> tuple[str, int]:
    for threshold, label, weight in REVIEW_BANDS:
        if coverage >= threshold:
            return label, weight
    return REVIEW_BANDS[-1][1], REVIEW_BANDS[-1][2]


def _band_explanations(point: knowledge.KnowledgePoint, hits: Sequence[str], missing: Sequence[str]) -> list[str]:
    advice: list[str] = []
    if hits:
        advice.append('已经提到：' + '、'.join(hits[:3]) + '。这部分表述可以保留。')
    if missing:
        advice.append('建议补上：' + '、'.join(missing[:3]) + '。')
    if point.common_mistakes:
        advice.append('注意常见错误：' + point.common_mistakes[0])
    return advice[:MAX_ADVICE]


def evaluate(text: str, topic: str | None = None, kind: str = 'feynman',
             settings: AgentSettings | None = None) -> dict:
    """评价学生复述/自评：按知识点信号覆盖率给出结果，live 模式另附模型点评。"""
    settings = settings or load_settings()
    cleaned = (text or '').strip()
    if not cleaned:
        return {
            'mode': 'demo',
            'notice': '没有收到可评价的内容。',
            'kind': kind,
            'band': '无法评价',
            'coverage': 0.0,
            'memory_weight': 0,
            'point': None,
            'signals_hit': [],
            'signals_missing': [],
            'advice': ['先写下你的理解，再提交评价。'],
            'follow_up': '你能用一句话说明这个概念解决什么问题吗？',
            'model_comment': None,
            'references': [],
            'method': '规则覆盖率（未调用模型）',
        }

    candidates = knowledge.retrieve(cleaned, topic=topic, top_k=3)
    target = candidates[0].point if candidates else None
    if target is None:
        return {
            'mode': 'demo',
            'notice': '这篇复述没有匹配到课程知识点，暂不能给出覆盖率评价。',
            'kind': kind,
            'band': '无法评价',
            'coverage': 0.0,
            'memory_weight': 0,
            'point': None,
            'signals_hit': [],
            'signals_missing': [],
            'advice': ['可以先对照课程目录，说明你要复述的是哪个知识点。'],
            'follow_up': '你这次想复述的是哪一章的哪个概念？',
            'model_comment': None,
            'references': [],
            'method': '规则覆盖率（未调用模型）',
        }

    signals = [signal for signal in target.signals if signal]
    hits = [signal for signal in signals if signal in cleaned]
    missing = [signal for signal in signals if signal not in cleaned]
    coverage = round(len(hits) / max(1, len(signals)), 2)
    band, weight = _band_of(coverage)

    result = {
        'mode': 'demo',
        'notice': '演示模式下按知识点信号覆盖率评价，未调用模型。',
        'kind': kind,
        'band': band,
        'coverage': coverage,
        'memory_weight': weight,
        'point': {
            'id': target.id,
            'title': target.title,
            'topic': target.topic,
            'source': target.source,
            'verified': target.verified,
        },
        'signals_hit': hits,
        'signals_missing': missing,
        'advice': _band_explanations(target, hits, missing),
        'follow_up': f'你能用一个反例说明「{target.title}」的限制条件吗？',
        'model_comment': None,
        'references': [hit.as_dict(index) for index, hit in enumerate(candidates, 1)],
        'method': '规则覆盖率 + 本地 BM25 检索（未调用模型）',
    }

    if settings.resolved_mode == 'live':
        try:
            comment = chat(prompts.build_feynman_messages(target.topic, cleaned, candidates), settings)
        except (ModelUnavailable, ModelCallFailed) as exc:
            result['notice'] = f'模型点评失败，已保留规则结论（原因：{exc}）。'
        else:
            result['model_comment'] = comment
            result['mode'] = 'live'
            result['notice'] = None
            result['method'] = '规则覆盖率 + 模型点评（模型只润色表达，不改变覆盖率结论）'
    return result


def recommend(state_data: dict, topic: str | None = None, limit: int = 3,
              exclude: Iterable[str] = ()) -> dict:
    """按长期记忆推荐下一批练习；排除 `exclude` 里的知识点以支持“换一批”。"""
    wanted = knowledge.normalize_topic(topic)
    excluded = {item for item in (exclude or ()) if item}
    seen = {item['point_id']: item for item in state_data.get('points', [])}
    candidates: list[tuple[int, float, str, str]] = []

    for item in state_data.get('points', []):
        if item['point_id'] in excluded or item['point_id'] in {row[2] for row in candidates}:
            continue
        if wanted and item['topic'] != wanted:
            continue
        if item['status'] == 'weak':
            candidates.append((0, item['mastery'], item['point_id'],
                               f"{RECOMMEND_REASONS['weak']}（掌握度 {item['mastery']}，负面证据 {item['negative']} 次）"))
    for item in state_data.get('points', []):
        if item['point_id'] in excluded or item['point_id'] in {row[2] for row in candidates}:
            continue
        if wanted and item['topic'] != wanted:
            continue
        if item['status'] == 'learning':
            candidates.append((1, item['mastery'], item['point_id'],
                               f"{RECOMMEND_REASONS['learning']}（练过 {item['attempts']} 次，掌握度 {item['mastery']}）"))

    for point in knowledge.KNOWLEDGE_POINTS:
        if point.id in excluded or point.id in seen or point.id in {row[2] for row in candidates}:
            continue
        if wanted and point.topic != wanted:
            continue
        candidates.append((2, 0.5, point.id, RECOMMEND_REASONS['unseen']))

    candidates.sort(key=lambda row: (row[0], row[1], row[2]))
    items: list[dict] = []
    for _, mastery, point_id, reason in candidates:
        if len(items) >= max(0, limit):
            break
        point = knowledge.get_point(point_id)
        if point is None:
            continue
        record = seen.get(point_id)
        items.append({
            'point_id': point.id,
            'title': point.title,
            'topic': point.topic,
            'reason': reason,
            'prompt': point.practice,
            'source': point.source,
            'verified': point.verified,
            'mastery': record['mastery'] if record else None,
            'status': record['status'] if record else 'unseen',
        })

    return {
        'mode': 'demo',
        'topic': wanted,
        'items': items,
        'empty_reason': None if items else '当前主题下没有可推荐的练习；可以换一个主题或先做一次诊断。',
        'method': '长期记忆掌握度 + 课程练习库（规则排序，未调用模型）',
        'note': '推荐依据是学生自己的练习与反馈证据，不是模型生成的学习计划。',
    }


def summarize(state_data: dict, conversations: Sequence[dict], days: int = 7,
              topic: str | None = None, settings: AgentSettings | None = None) -> dict:
    """阶段总结复习：汇总学习记录与长期记忆，给出下一步建议。"""
    settings = settings or load_settings()
    window = max(1, int(days))
    cutoff = datetime.now(timezone.utc) - timedelta(days=window)
    wanted = knowledge.normalize_topic(topic)

    recent = []
    for item in conversations:
        created = _parse_time(item.get('created_at'))
        if created is None or created < cutoff:
            continue
        if wanted and knowledge.normalize_topic(item.get('topic')) != wanted:
            continue
        recent.append(item)

    topic_counts: dict[str, int] = {}
    for item in recent:
        key = item.get('topic') or '未分类'
        topic_counts[key] = topic_counts.get(key, 0) + 1

    weak = [item for item in state_data.get('points', []) if item['status'] == 'weak']
    mastered = [item for item in state_data.get('points', []) if item['status'] == 'mastered']

    highlights: list[str] = [f'本次统计窗口 {window} 天，提问 {len(recent)} 次，长期记忆中有 {state_data.get("event_count", 0)} 条学习证据。']
    if topic_counts:
        top_topic = max(topic_counts.items(), key=lambda kv: kv[1])
        highlights.append(f'提问集中在「{top_topic[0]}」（{top_topic[1]} 次）。')
    if mastered:
        highlights.append('已经比较稳的知识点：' + '、'.join(item['title'] for item in mastered[:3]) + '。')
    if weak:
        highlights.append('仍然薄弱的知识点：' + '、'.join(item['title'] for item in weak[:3]) + '。')
    if not weak and not mastered and not state_data.get('points'):
        highlights.append('还没有练习证据，暂时无法判断掌握情况。')

    next_steps: list[str] = []
    if weak:
        next_steps.append(f"优先复习「{weak[0]['title']}」，并完成它对应的变式练习。")
    if len(weak) > 1:
        next_steps.append(f"其次复习「{weak[1]['title']}」，做完后到诊断接口重新检查。")
    if not weak:
        next_steps.append('先做一次步骤反馈或复述评价，让系统有据可依。')
    next_steps.append('把这次总结里提到的薄弱点加入错题收藏，方便下次直接找到。')

    evidence = knowledge.retrieve(' '.join(item['title'] for item in weak[:2]) if weak else (topic or ''), top_k=3)

    result = {
        'mode': 'demo',
        'notice': '演示模式下总结由本地记录与长期记忆汇总得到，未调用模型。',
        'period_days': window,
        'topic': wanted,
        'question_count': len(recent),
        'topics': [{'topic': key, 'count': value} for key, value in sorted(topic_counts.items(), key=lambda kv: -kv[1])],
        'covered_points': len(state_data.get('points', [])),
        'weak_points': [{'point_id': item['point_id'], 'title': item['title'],
                         'mastery': item['mastery'], 'attempts': item['attempts']} for item in weak[:5]],
        'mastered_points': [{'point_id': item['point_id'], 'title': item['title'],
                             'mastery': item['mastery']} for item in mastered[:5]],
        'highlights': highlights,
        'next_steps': next_steps,
        'model_summary': None,
        'references': [hit.as_dict(index) for index, hit in enumerate(evidence, 1)],
        'method': '本地学习记录 + 长期记忆汇总（未调用模型）',
    }

    if settings.resolved_mode == 'live' and (weak or recent):
        try:
            text = chat(prompts.build_summary_messages(result, evidence), settings)
        except (ModelUnavailable, ModelCallFailed) as exc:
            result['notice'] = f'模型润色失败，已保留规则总结（原因：{exc}）。'
        else:
            result['model_summary'] = text
            result['mode'] = 'live'
            result['notice'] = None
            result['method'] = '本地汇总 + 模型润色（模型不改动薄弱项与下一步结论）'
    return result


def parse_model_json(raw: str) -> dict | None:
    """给需要结构化模型输出的调用方使用。"""
    return extract_json(raw)
