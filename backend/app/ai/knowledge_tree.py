"""B 模块知识讲解拆解（会议第 1 条「知识讲解重构（AI 拆解 → 树状图）」的 B 侧输出）。

分工：B 输出**结构化的知识树**（章节 → 知识点 → 分支 → 叶子），A 端负责画成树状图/思维导图。

设计取舍：

- 先修关系（prerequisites / unlocks）由人工按课程顺序整理并写在代码里，**不是模型猜的**；
- demo 模式下的树完全由 `knowledge` 的字段派生，因此可复核、可测试、可离线演示；
- live 模式允许模型重组讲解文字（`explanation`），但要点、误区、例题与出处仍来自课程库，
  模型的输出只做长度与层级校验：不合格就退回规则树并说明（`notice`）；
- 知识点仍全部 `verified=false`，树上必须如实标注“待课程资料复核”。
"""
from __future__ import annotations

from typing import Sequence

from . import hints, knowledge, prompts, resilience
from .config import AgentSettings, load_settings
from .llm import ModelCallFailed, ModelUnavailable, chat, extract_json

TOPIC_ORDER = ('极限与连续', '导数与微分', '一元函数积分学', '无穷级数')

# 先修关系：按同济版课程顺序人工整理；仅在知识点内部使用 id，避免前端再查一次。
PREREQUISITES = {
    'limit-definition': (),
    'important-limits': ('limit-definition',),
    'limit-techniques': ('limit-definition', 'important-limits'),
    'continuity': ('limit-definition',),
    'derivative-definition': ('limit-definition',),
    'derivative-rules': ('derivative-definition',),
    'derivative-application': ('derivative-rules',),
    'integral-antiderivative': ('derivative-rules',),
    'integral-definite': ('limit-techniques', 'integral-antiderivative'),
    'integral-ftc': ('integral-definite', 'derivative-application'),
    'integral-techniques': ('integral-antiderivative', 'derivative-rules'),
    'series-convergence': ('limit-techniques', 'continuity'),
}

MAX_BRANCHES = 6
MAX_CHILDREN = 6
MAX_LABEL = 40
MAX_TEXT = 500

HONESTY = ('要点、误区、例题与出处来自课程知识点库，模型只允许重组讲解文字，'
           '不得新增或删除要点；知识点当前均为待复核状态，界面上要照实标注。')


def _titles(point_ids: Sequence[str]) -> list[dict]:
    rows: list[dict] = []
    for point_id in point_ids:
        point = knowledge.get_point(point_id)
        if point is not None:
            rows.append({'id': point.id, 'title': point.title, 'topic': point.topic})
    return rows


def _unlocks(point_id: str) -> list[dict]:
    return _titles([other.id for other in knowledge.KNOWLEDGE_POINTS
                    if point_id in PREREQUISITES.get(other.id, ())])


def tree() -> dict:
    """完整知识树：章节 → 知识点（含先修与解锁关系），供 A 端画树状图。"""
    topics: list[dict] = []
    for topic in TOPIC_ORDER:
        points = [point for point in knowledge.KNOWLEDGE_POINTS if point.topic == topic]
        topics.append({
            'topic': topic,
            'points': [{
                'id': point.id,
                'title': point.title,
                'summary': point.summary,
                'key_point_count': len(point.key_points),
                'verified': point.verified,
                'source': point.source,
                'prerequisites': _titles(PREREQUISITES.get(point.id, ())),
                'unlocks': _unlocks(point.id),
            } for point in points],
        })
    edges = [{'from': prerequisite, 'to': point_id}
             for point_id, prerequisites in PREREQUISITES.items() for prerequisite in prerequisites]
    stats = knowledge.stats()
    return {
        'mode': 'demo',
        'notice': None,
        'order': list(TOPIC_ORDER),
        'topics': topics,
        'edges': edges,
        'total_points': sum(len(item['points']) for item in topics),
        'verified_points': stats['verified_points'],
        'pending_review': stats['pending_review'],
        'note': '先修关系由 B 按课程顺序人工整理，仍需课程资料复核确认；知识点当前全部待复核。',
        'method': '课程知识点 + 人工整理的先修关系（未调用模型）',
    }


def _rule_branches(point: knowledge.KnowledgePoint) -> list[dict]:
    branches: list[dict] = [{
        'id': 'concept',
        'label': '它解决什么问题',
        'children': [{'id': 'concept-0', 'label': '概念定位', 'text': point.summary}],
    }]
    if point.key_points:
        branches.append({
            'id': 'key-points',
            'label': '关键要点',
            'children': [{'id': f'key-{index}', 'label': f'要点 {index}', 'text': text}
                         for index, text in enumerate(point.key_points, 1)],
        })
    if point.common_mistakes:
        branches.append({
            'id': 'mistakes',
            'label': '常见误区',
            'children': [{'id': f'mistake-{index}', 'label': f'误区 {index}', 'text': text}
                         for index, text in enumerate(point.common_mistakes, 1)],
        })
    branches.append({
        'id': 'example',
        'label': '例题拆解',
        'children': [
            {'id': 'example-0', 'label': '典型例题',
             'text': point.example or '这个知识点暂时还没有配例题，可先用下面的变式练习。'},
            {'id': 'example-first', 'label': '第一步怎么做',
             'text': hints.START_ACTIONS.get(point.id, '先把已知条件与要求解的目标写成式子，再选定义或定理。')},
            {'id': 'example-boundary', 'label': '做完要自检什么',
             'text': '结论要不要附加条件？把条件去掉一个再看结论是否仍然成立。'},
        ],
    })
    prerequisites = _titles(PREREQUISITES.get(point.id, ()))
    unlocks = _unlocks(point.id)
    branches.append({
        'id': 'position',
        'label': '在知识体系里的位置',
        'children': [
            {'id': 'position-pre', 'label': '先修',
             'text': '、'.join(item['title'] for item in prerequisites) or '本章的起点，可先复习函数与数列极限的直觉。'},
            {'id': 'position-next', 'label': '学完可以继续',
             'text': '、'.join(item['title'] for item in unlocks) or '本章后续内容。'},
        ],
    })
    branches.append({
        'id': 'practice',
        'label': '怎么练',
        'children': [
            {'id': 'practice-0', 'label': '变式练习',
             'text': point.practice or '先用本地练习模块做一组 4 步刻意练习。'},
            {'id': 'practice-1', 'label': '练习方式',
             'text': '先自己写第一步 → 提交步骤反馈 → 再要一级分层提示，不要直接看完整解答。'},
        ],
    })
    return branches


def _coerce_branches(raw: dict | None) -> list[dict] | None:
    """校验模型返回的树：层级、数量与长度不合格就返回 None（调用方退回规则树）。"""
    if not isinstance(raw, dict):
        return None
    branches = raw.get('branches')
    if not isinstance(branches, (list, tuple)) or len(branches) < 3:
        return None
    cleaned: list[dict] = []
    for branch_index, branch in enumerate(list(branches)[:MAX_BRANCHES], 1):
        if not isinstance(branch, dict):
            return None
        label = resilience.coerce_text(branch.get('label'), '', MAX_LABEL)
        children = branch.get('children')
        if not label or not isinstance(children, (list, tuple)) or not children:
            return None
        rows: list[dict] = []
        for child_index, child in enumerate(list(children)[:MAX_CHILDREN], 1):
            if not isinstance(child, dict):
                return None
            child_label = resilience.coerce_text(child.get('label'), '', MAX_LABEL)
            child_text = resilience.coerce_text(child.get('text'), '', MAX_TEXT)
            if not child_label or not child_text:
                return None
            rows.append({'id': f'm{branch_index}-{child_index}', 'label': child_label, 'text': child_text})
        cleaned.append({'id': f'm{branch_index}', 'label': label, 'children': rows})
    return cleaned or None


def explain(point_id: str, question: str | None = None, settings: AgentSettings | None = None) -> dict:
    """把一个知识点拆成树：章节定位 → 概念 → 要点 → 误区 → 例题 → 练习。"""
    settings = settings or load_settings()
    point = knowledge.get_point(point_id)
    if point is None:
        raise ValueError(f'未知知识点：{point_id}')

    hits = knowledge.retrieve(f'{point.title} {question or ""}'.strip(), topic=point.topic, top_k=3)
    branches = _rule_branches(point)
    result = {
        'mode': 'demo',
        'notice': None,
        'question': question or '',
        'root': {
            'id': point.id,
            'label': point.title,
            'topic': point.topic,
            'summary': point.summary,
            'verified': point.verified,
            'source': point.source,
        },
        'branches': branches,
        'prerequisites': _titles(PREREQUISITES.get(point.id, ())),
        'unlocks': _unlocks(point.id),
        'branch_count': len(branches),
        'leaf_count': sum(len(branch['children']) for branch in branches),
        'honesty': HONESTY,
        'references': [hit.as_dict(index) for index, hit in enumerate(hits, 1)],
        'method': '课程知识点派生的树状拆解（规则，未调用模型）',
    }

    if settings.resolved_mode == 'live':
        try:
            raw, _meta = resilience.call_model(
                lambda: chat(prompts.build_tree_messages(result, hits), settings),
                endpoint='POST /api/agent/knowledge/explain',
            )
        except (ModelUnavailable, ModelCallFailed) as exc:
            result['notice'] = f'模型拆解生成失败，已保留规则树（原因：{exc}）。'
        else:
            parsed = extract_json(raw)
            summary = resilience.coerce_text((parsed or {}).get('summary'), '', MAX_TEXT)
            branches_from_model = _coerce_branches(parsed)
            if branches_from_model:
                result['branches'] = branches_from_model
                result['branch_count'] = len(branches_from_model)
                result['leaf_count'] = sum(len(branch['children']) for branch in branches_from_model)
                if summary:
                    result['root']['summary'] = summary
                result['mode'] = 'live'
                result['notice'] = None
                result['method'] = ('课程知识点 + 模型重组讲解文字'
                                    '（模型不得新增/删除要点，结构校验不通过即退回规则树）')
            else:
                result['notice'] = '模型返回的拆解结构不符合约定（层级/长度校验未通过），已使用规则树。'
    return result


def describe() -> dict:
    return {
        'topics': list(TOPIC_ORDER),
        'points': len(knowledge.KNOWLEDGE_POINTS),
        'edges': sum(len(value) for value in PREREQUISITES.values()),
        'max_branches': MAX_BRANCHES,
        'max_children': MAX_CHILDREN,
        'note': '先修关系由 B 人工整理；知识点待课程资料复核。',
    }
