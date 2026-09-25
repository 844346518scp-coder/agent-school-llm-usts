"""B 模块分层提示（9/25–27 补齐项）：概念提示 → 方法提示 → 关键步骤提示。

为什么要分三级：

- 直接给完整解答会让学生跳过思考；只给“再想想”又没有帮助。三级提示让学生自己选择
  需要的帮助量，第 3 级也只给出**第一步动作**，不给出最终结果，配合步骤反馈形成苏格拉底式闭环。
- 提示内容在 demo 模式完全由课程知识点派生（可复核、可测试）；live 模式由模型按同一层级要求生成，
  但必须遵守“不给出完整解答与最终答案”的硬约束，模型返回不可解析时退回规则提示并说明。

硬约束：任何级别的 `hint` 都不得包含最终答案；响应固定带 `answer_leaked: False` 与 `guard` 说明。
"""
from __future__ import annotations

from typing import Sequence

from . import knowledge, prompts
from .config import AgentSettings, load_settings
from .llm import ModelCallFailed, ModelUnavailable, chat, extract_json

MAX_LEVEL = 3
LEVEL_TITLES = {1: '概念提示', 2: '方法提示', 3: '关键步骤提示'}

# 第 3 级提示的“第一步动作”按知识点手工编写：只描述动作与形式，不给最终结果。
START_ACTIONS = {
    'limit-definition': '先把要求解的极限写成 lim 的形式，标出趋近点，并判断是否需要分别讨论左、右极限。',
    'limit-techniques': '先直接代入趋近点，判断是否出现 0/0 或 ∞/∞；若是，再写成“分子分母同时约去公因子”或“有理化”的第一行。',
    'important-limits': '先把原式整理成 sin u / u 的形状（注意 u 是同一个表达式），并写下 u 的趋近值。',
    'continuity': '先把定义域的三个条件逐条列出：该点有定义、极限存在、极限值等于函数值，然后只检查第一条。',
    'derivative-definition': '先写出差商 [f(x+h)-f(x)]/h 的完整表达式，先不要展开化简。',
    'derivative-rules': '先判断函数是四则运算还是复合结构，并在草稿上标出外层函数与内层函数（或逐项拆分）。',
    'derivative-application': '先求一阶导数并解 f′(x)=0，把驻点列成表格，再讨论单调性或极值。',
    'integral-antiderivative': '先判断被积函数能否化为基本积分表的形式，并写出你打算使用的第一个公式。',
    'integral-definite': '先写出积分区间的上下限与被积函数，并判断是否需要分割区间或利用对称性。',
    'integral-ftc': '先把牛顿-莱布尼茨公式的右侧写成 F(b)-F(a) 的形式，再去找原函数 F。',
    'integral-techniques': '先观察被积函数的结构（含根式、乘积还是复合），据此写出你选择的换元变量或分部对象。',
    'series-convergence': '先判断级数是一般项级数还是正项级数，再把通项 un 的表达式明确写出来。',
}

GENERIC_ACTION = '先把题目的已知条件与要求解的目标写成式子，再写下你打算使用的第一个定义或定理。'

SELF_CHECKS = {
    1: '用自己的话说明「{title}」刻画的是什么，再说出它成立的前提条件。',
    2: '写出你打算用的方法，并说明它的适用条件（为什么这里能用）。',
    3: '把第一步写出来，然后回答：这一步的依据是哪条定义或定理？',
}

GUARD = ('提示按 1→2→3 逐级更具体，任何级别都不包含最终答案；'
         '如果第 3 级之后仍然卡住，请把已写出的步骤提交「步骤反馈」，由它只评价这一步。')


def _first_sentences(text: str, count: int = 2) -> str:
    parts = [part.strip() for part in (text or '').replace('\n', '').split('。') if part.strip()]
    return '。'.join(parts[:count]) + '。' if parts else ''


def _rule_hint(point: knowledge.KnowledgePoint | None, level: int, question: str) -> str:
    if point is None:
        return (f'没有检索到与「{question}」匹配的课程知识点，无法给出第 {level} 级提示。'
                '可以补充章节或题型（例如“极限的计算”“复合函数求导”），或先做一次诊断。')
    if level == 1:
        return (f'先明确概念：{point.title}。{_first_sentences(point.summary, 2)}'
                f'请先用自己的话写下这个概念的要点，再往下看。')
    if level == 2:
        lines = ['可以沿这个方向试：']
        for item in point.key_points[:2]:
            lines.append(f'· {item}')
        if point.common_mistakes:
            lines.append(f'注意常见错误：{point.common_mistakes[0]}')
        lines.append('这一步只定方向，不要急着算出结果。')
        return '\n'.join(lines)
    action = START_ACTIONS.get(point.id, GENERIC_ACTION)
    return f'{action}\n（这里只给出第一步的动作，不给出后续推导与最终结果。）'


def _self_check(point: knowledge.KnowledgePoint | None, level: int) -> str:
    template = SELF_CHECKS.get(level, SELF_CHECKS[1])
    return template.format(title=point.title if point else '这个概念')


def build(question: str, level: int = 1, topic: str | None = None,
          settings: AgentSettings | None = None) -> dict:
    """生成指定层级的提示；``level`` 只能是 1/2/3。"""
    settings = settings or load_settings()
    try:
        wanted_level = int(level)
    except (TypeError, ValueError):
        wanted_level = 1
    wanted_level = min(MAX_LEVEL, max(1, wanted_level))

    hits = knowledge.retrieve(question, topic=topic, top_k=3)
    point = hits[0].point if hits else None
    references = [hit.as_dict(index) for index, hit in enumerate(hits, 1)]

    result = {
        'mode': 'demo',
        'notice': None,
        'question': question,
        'level': wanted_level,
        'level_title': LEVEL_TITLES[wanted_level],
        'levels_total': MAX_LEVEL,
        'topic': knowledge.normalize_topic(topic),
        'point': None if point is None else {
            'id': point.id, 'title': point.title, 'topic': point.topic,
            'source': point.source, 'verified': point.verified,
        },
        'hint': _rule_hint(point, wanted_level, question),
        'self_check': _self_check(point, wanted_level),
        'next_level': wanted_level + 1 if wanted_level < MAX_LEVEL else None,
        'next_level_action': ('可以再要一级更具体的提示。' if wanted_level < MAX_LEVEL
                              else '已到最具体一级；请提交「步骤反馈」核对这一步。'),
        'answer_leaked': False,
        'guard': GUARD,
        'references': references,
        'method': '课程知识点派生（规则，未调用模型）',
    }

    if point is not None and settings.resolved_mode == 'live':
        try:
            raw = chat(prompts.build_hint_messages(question, wanted_level, LEVEL_TITLES[wanted_level], topic, hits),
                       settings)
        except (ModelUnavailable, ModelCallFailed) as exc:
            result['notice'] = f'模型提示生成失败，已使用知识点派生的规则提示（原因：{exc}）。'
        else:
            parsed = extract_json(raw)
            hint = str((parsed or {}).get('hint') or '').strip()
            if hint:
                result['hint'] = hint
                result['self_check'] = str((parsed or {}).get('self_check') or result['self_check']).strip()
                result['mode'] = 'live'
                result['method'] = '模型按层级要求生成（提示词强制不得给出最终答案，规则依据仍随响应返回）'
            else:
                result['notice'] = '模型未按约定返回 JSON，已使用规则提示。'
    return result
