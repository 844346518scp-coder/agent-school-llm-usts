"""B 模块刻意练习与苏格拉底追问（会议第 2 条「教学逻辑（刻意练习 / 苏格拉底）」的 B 侧实现）。

分工图中 B 负责「负责判断策略」：这里的策略都是可解释的规则，模型只在 live 模式下润色反馈文字。

刻意练习怎么定（写死在代码里，界面必须照原样说明）：

- 选题优先级：掌握度偏低/负面证据多的薄弱知识点 → 练过但没稳住 → 本章还没练过的；
- 一个知识点固定 4 步：复述条件 → 辨析易错 → 动手算一步 → 迁移自检（苏格拉底式逐层追问）；
- 达标规则：同一步骤「基本到位」才算过关；连续两次不足以判定掌握，掌握度仍以长期记忆口径为准；
- 每次只评价**当前这一步**，不给出完整解答；第 3 步如果学生写了结果，用本地数学工具核对数值。

诚实性约束：

- 公开的练习计划**不含**期望关键词与期望数值，避免把答案漏给学生（检验函数是私有的）；
- 数值核对只读取「= / 得 / 结果是 / 答案是」这类显式结果后面的数字，不做猜测；
- 规则覆盖率不是模型判断，也不等于掌握度；响应里 `method` 必须写明这一点。
"""
from __future__ import annotations

import math
import re
from typing import Sequence

from . import hints, knowledge, mathcheck, prompts, resilience
from .config import AgentSettings, load_settings
from .llm import ModelCallFailed, ModelUnavailable, chat, extract_json

TOTAL_STEPS = 4

STEP_TEMPLATES = (
    ('recall', '复述与条件', '用自己的话说明「{title}」：它刻画什么？成立需要什么条件？'),
    ('boundary', '辨析与易错', '下面这种说法对吗，为什么：「{mistake}」'),
    ('compute', '动手算一步', '{target}\n先只写第一步，不要一次写完整解答；如果你已经算出了结果，请写成「= 结果」的形式，系统会用本地数学工具核对。'),
    ('transfer', '迁移与自检', '换个条件再想一次：如果不能使用「{last_key_point}」，你的结论要改哪一步？'),
)

# 第 3 步的动手目标（每点一句，短且可核对）；没有可核对目标的点留空字符串。
TARGETS = {
    'limit-definition': '求 $\\lim_{x\\to 1}\\dfrac{x^{2}-1}{x-1}$。',
    'limit-techniques': '求 $\\lim_{x\\to\\infty}\\left(1+\\dfrac{1}{x}\\right)^{x}$。',
    'important-limits': '求 $\\lim_{x\\to 0}\\dfrac{\\sin x}{x}$。',
    'continuity': '求 $\\lim_{x\\to 0}\\dfrac{\\sin x}{x}$，并说明 $f(x)=\\dfrac{\\sin x}{x}$ 在 $x=0$ 处是否连续。',
    'derivative-definition': '用定义求 $f(x)=x^{2}$ 在 $x=3$ 处的导数。',
    'derivative-rules': '求 $y=x\\sin x$ 的导数，并算出 $x=1$ 处的取值（可写近似小数）。',
    'derivative-application': '求 $f(x)=x^{2}-1$ 的极小值。',
    'integral-antiderivative': '验证 $F(x)=\\dfrac{x^{3}}{3}$ 是 $f(x)=x^{2}$ 的原函数：求 $F\'(2)$ 的值。',
    'integral-definite': '求 $\\int_{0}^{1}x^{2}\\,\\mathrm{d}x$。',
    'integral-ftc': '已知 $F\'(x)=x^{2}$ 且 $F(0)=0$，用牛顿-莱布尼茨公式求 $F(2)$。',
    'integral-techniques': '验证 $F(x)=x\\ln x-x$ 是 $f(x)=\\ln x$ 的原函数：求 $F\'(e)$ 的值。',
    'series-convergence': '判断级数 $\\sum_{n=1}^{\\infty}\\dfrac{1}{n^{2}}$ 是否收敛；如果收敛，写出它的和（可选）。',
}

# 第 3 步的数值核对：kind ∈ limit / value / derivative_value / constant。
CHECKS = {
    'limit-definition': {'kind': 'limit', 'expr': '(x^2-1)/(x-1)', 'x0': 1.0, 'expected': 2.0},
    'limit-techniques': {'kind': 'limit', 'expr': '(1+1/x)^x', 'x0': 'inf', 'expected': math.e},
    'important-limits': {'kind': 'limit', 'expr': 'sin(x)/x', 'x0': 0.0, 'expected': 1.0},
    'continuity': {'kind': 'limit', 'expr': 'sin(x)/x', 'x0': 0.0, 'expected': 1.0},
    'derivative-definition': {'kind': 'derivative_value', 'expr': 'x^2', 'x': 3.0, 'expected': 6.0},
    'derivative-rules': {'kind': 'derivative_value', 'expr': 'x*sin(x)', 'x': 1.0, 'expected': 1.381773},
    'derivative-application': {'kind': 'value', 'expr': 'x^2-1', 'x': 0.0, 'expected': -1.0},
    'integral-antiderivative': {'kind': 'derivative_value', 'expr': 'x^3/3', 'x': 2.0, 'expected': 4.0},
    'integral-definite': {'kind': 'constant', 'expected': 1 / 3},
    'integral-ftc': {'kind': 'constant', 'expected': 8 / 3},
    'integral-techniques': {'kind': 'derivative_value', 'expr': 'x*ln(x)-x', 'x': math.e, 'expected': 1.0},
    'series-convergence': {'kind': 'constant', 'expected': math.pi ** 2 / 6},
}

# 第 3 步的动作词：答对第一步的做法应当出现其中至少一个。
ACTION_KEYWORDS = {
    'limit-definition': ('约分', '因式分解', '代入', '通分', '有理化'),
    'limit-techniques': ('等价无穷小', '取对数', '洛必达', '重要极限', 'e'),
    'important-limits': ('重要极限', '夹逼', '等价无穷小', 'sin'),
    'continuity': ('定义', '极限值', '函数值', '无定义', '左右极限'),
    'derivative-definition': ('差商', '定义', '增量', '求极限'),
    'derivative-rules': ('乘积', '法则', '链式', '求导公式', '逐项'),
    'derivative-application': ('一阶导', '驻点', 'f′', '符号', '单调'),
    'integral-antiderivative': ('求导', '验证', '求导公式', '原函数'),
    'integral-definite': ('原函数', '牛顿', '积分上限', '分割', '求和取极限'),
    'integral-ftc': ('牛顿-莱布尼茨', '原函数', '上下限', 'F(2)-F(0)'),
    'integral-techniques': ('换元', '分部', '求导验证', '乘积求导'),
    'series-convergence': ('比较判别', 'p 级数', '通项', '收敛'),
}

PRACTICE_BANDS = ((0.6, '基本到位', 1), (0.3, '有遗漏', 0), (0.0, '需要重讲', -1))

FOLLOW_UPS = {
    'recall': '你能不能再举一个反例，说明这个条件不能省？',
    'boundary': '如果把这句话改成正确的版本，该怎么写？',
    'compute': '这一步用到了哪条定义或定理？说出依据再往下。',
    'transfer': '条件改动后，哪一步的推导必须重做？',
}

FOCUS_RULE = ('优先练薄弱知识点；同一知识点连续两次「基本到位」也不等同于已掌握，'
              '掌握度仍按长期记忆的可核对证据计算。')
ANSWER_RULE = '每次只评价这一步，不给出完整解答；数值核对只读取显式写出的结果。'

# 结果数值只从显式标记后读取，避免把「x^2」「区间 [0,1]」里的数字当成答案。
NUMBER = r'-?\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)?'
RESULT_MARKER = re.compile(rf'(?:=|等于|得|得到|算出|求得|答案(?:是)?|结果(?:是)?)\s*({NUMBER})')


def _result_numbers(text: str) -> list[float]:
    values: list[float] = []
    for match in RESULT_MARKER.finditer(text or ''):
        raw = match.group(1)
        try:
            if '/' in raw:
                numerator, denominator = raw.split('/')
                if float(denominator) == 0:
                    continue
                values.append(float(numerator) / float(denominator))
            else:
                values.append(float(raw))
        except ValueError:
            continue
    return values


def _band_of(coverage: float) -> tuple[str, int]:
    for threshold, label, weight in PRACTICE_BANDS:
        if coverage >= threshold:
            return label, weight
    return PRACTICE_BANDS[-1][1], PRACTICE_BANDS[-1][2]


def _focus_reason(item: dict | None, point: knowledge.KnowledgePoint) -> str:
    if item is None:
        return f'「{point.title}」还没有练习记录，属于本章基础内容，先从这里开始。'
    if item['status'] == 'weak':
        return (f"「{point.title}」掌握度 {item['mastery']}、负面证据 {item['negative']} 次，属于优先重练的内容。")
    if item['status'] == 'learning':
        return f"「{point.title}」练过 {item['attempts']} 次但还没稳住（掌握度 {item['mastery']}），再练一轮巩固。"
    return f"「{point.title}」已有 {item['attempts']} 条证据，掌握度 {item['mastery']}，用这组练习再确认一次。"


def _focus_point(state_data: dict | None, point_id: str | None, topic: str | None):
    wanted = knowledge.normalize_topic(topic)
    points = (state_data or {}).get('points', [])
    if point_id:
        point = knowledge.get_point(point_id)
        if point is None:
            raise ValueError(f'未知知识点：{point_id}')
        return point, _focus_reason(memory_point(points, point_id), point)

    ranked: list[tuple[int, float, int, dict, knowledge.KnowledgePoint]] = []
    for item in points:
        point = knowledge.get_point(item['point_id'])
        if point is None or (wanted and point.topic != wanted):
            continue
        order = {'weak': 0, 'learning': 1}.get(item['status'])
        if order is None:
            continue
        ranked.append((order, item['mastery'], -item['attempts'], item, point))
    if ranked:
        ranked.sort(key=lambda row: (row[0], row[1], row[2], row[4].id))
        _order, _mastery, _attempts, item, point = ranked[0]
        return point, _focus_reason(item, point)

    for point in knowledge.KNOWLEDGE_POINTS:
        if wanted and point.topic != wanted:
            continue
        return point, _focus_reason(None, point)
    raise ValueError('当前主题下没有可练习的知识点')


def memory_point(points: Sequence[dict], point_id: str) -> dict | None:
    for item in points:
        if item['point_id'] == point_id:
            return item
    return None


def _step_payload(point: knowledge.KnowledgePoint, index: int) -> dict:
    kind, title, template = STEP_TEMPLATES[index - 1]
    mistake = point.common_mistakes[0] if point.common_mistakes else '这个结论对所有情形都成立'
    last_key_point = point.key_points[-1] if point.key_points else point.title
    target = TARGETS.get(point.id) or f'用「{point.title}」的结论做一个小例子。'
    prompt = template.format(title=point.title, mistake=mistake,
                             last_key_point=last_key_point, target=target)
    return {'index': index, 'kind': kind, 'title': title, 'prompt': prompt}


def _expected_signals(point: knowledge.KnowledgePoint, kind: str) -> list[str]:
    """私有：期望命中词只用于评价，绝不放进公开的练习计划。"""
    if kind == 'recall':
        return list(point.signals[:3]) or ['定义']
    if kind == 'boundary':
        return list(point.signals[:2]) + ['不成立', '错误', '条件', '前提', '错']
    if kind == 'compute':
        return list(ACTION_KEYWORDS.get(point.id, ())) or ['第一步']
    return list(point.signals[:2]) + ['条件', '前提', '不成立', '改成', '仍然']


def plan(state_data: dict | None = None, point_id: str | None = None, topic: str | None = None,
         settings: AgentSettings | None = None) -> dict:
    """生成一组刻意练习：4 步苏格拉底式追问，公开计划不含期望答案。"""
    settings = settings or load_settings()
    point, reason = _focus_point(state_data, point_id, topic)
    steps = [_step_payload(point, index) for index in range(1, TOTAL_STEPS + 1)]
    hits = knowledge.retrieve(f'{point.title} {point.topic}', topic=point.topic, top_k=2)
    result = {
        'mode': 'demo',
        'notice': None,
        'session': {
            'point_id': point.id,
            'title': point.title,
            'topic': point.topic,
            'total_steps': TOTAL_STEPS,
            'source': point.source,
            'verified': point.verified,
        },
        'why': reason,
        'steps': steps,
        'focus_rule': FOCUS_RULE,
        'answer_rule': ANSWER_RULE,
        'leak_guard': '公开的练习计划不包含期望关键词与期望数值；它们只用于评价你的作答。',
        'references': [hit.as_dict(index) for index, hit in enumerate(hits, 1)],
        'method': '长期记忆 + 课程知识点派生（规则，未调用模型）',
    }
    if settings.resolved_mode == 'live':
        # 练习计划本身是规则生成的（不依赖模型），这里只如实说明，不冒充模型输出。
        result['notice'] = '练习题目由本地规则生成；模型的角色只在评价反馈（/practice/answer）里润色文字。'
    return result


def _numeric_check(point: knowledge.KnowledgePoint, answer: str) -> dict | None:
    spec = CHECKS.get(point.id)
    if not spec:
        return None
    given = _result_numbers(answer)
    if not given:
        return {
            'ok': None,
            'expected': spec['expected'],
            'given': [],
            'method': '结果数值比对（只读取「= / 得 / 结果是」后面的数值）',
            'note': '你的回答里没有写出显式结果，本轮不做数值核对。',
        }
    actual = None
    note = ''
    kind = spec['kind']
    try:
        if kind == 'limit':
            probe = mathcheck.probe_limit(spec['expr'], spec['x0'])
            actual = probe['candidate']
            if not probe['ok']:
                note = '本地工具在该点没有探测到收敛的极限值，无法核对。'
        elif kind == 'value':
            actual = mathcheck.safe_value(spec['expr'], spec['x'])
        elif kind == 'derivative_value':
            report = mathcheck.derivative_report(spec['expr'])
            if report['ok']:
                actual = mathcheck.safe_value(report['derivative'], spec['x'])
            else:
                note = f'本工具无法对该函数求导（{report["error"]}）。'
        elif kind == 'constant':
            actual = spec['expected']
    except mathcheck.MathError as exc:
        note = f'数值核对未能完成：{exc}'

    if actual is None:
        return {'ok': None, 'expected': spec['expected'], 'given': given, 'note': note or '无法核对。',
                'method': '结果数值比对（只读取「= / 得 / 结果是」后面的数值）'}

    tolerance = max(5e-3, abs(actual) * 5e-3)
    matched = [value for value in given if abs(value - actual) <= tolerance]
    return {
        'ok': bool(matched),
        'expected': round(actual, 6),
        'given': [round(value, 6) for value in given],
        'matched': [round(value, 6) for value in matched],
        'tolerance': round(tolerance, 6),
        'note': note,
        'method': '本地数学工具数值核对（'+ {
            'limit': '极限取样探测', 'value': '函数求值', 'derivative_value': '符号求导后求值',
            'constant': '已知结果比对'}[kind] +'）；仍是数值证据，不是证明',
    }


def answer(point_id: str, step_index: int, text: str, settings: AgentSettings | None = None) -> dict:
    """评价某一步的作答：规则覆盖率 + 可选数值核对，并给出苏格拉底式追问。"""
    settings = settings or load_settings()
    point = knowledge.get_point(point_id)
    if point is None:
        raise ValueError(f'未知知识点：{point_id}')
    try:
        index = int(step_index)
    except (TypeError, ValueError):
        raise ValueError('step_index 必须是 1 到 4 的整数') from None
    if not 1 <= index <= TOTAL_STEPS:
        raise ValueError('step_index 必须是 1 到 4 的整数')
    cleaned = (text or '').strip()
    if not cleaned:
        raise ValueError('请先写下你的作答')

    step = _step_payload(point, index)
    signals = _expected_signals(point, step['kind'])
    hits = [signal for signal in signals if signal and signal in cleaned]
    missing = [signal for signal in signals if signal not in cleaned]
    coverage = round(len(hits) / max(1, len(signals)), 2)
    band, weight = _band_of(coverage)

    numeric = _numeric_check(point, cleaned) if step['kind'] == 'compute' else None
    verdict = 'unverifiable'
    if numeric is not None and numeric['ok'] is True:
        verdict = 'correct'
        band, weight = '数值核对通过', 2
    elif numeric is not None and numeric['ok'] is False:
        verdict = 'incorrect'
        band, weight = '数值核对未通过', -2

    if verdict == 'correct':
        feedback = ('数值核对通过：结果与本地数学工具的结论一致。'
                    '接下来请补一句依据 —— 你用的是哪条定义或定理？')
    elif verdict == 'incorrect':
        feedback = (f"你写出的结果 {numeric['given']} 与数值核对结果 {numeric['expected']} 不一致。"
                    '先别改答案：回头检查你用的公式或条件是否适用，再算一次。')
    elif band == '基本到位':
        feedback = ('要点基本说到了。' + (f"还差一点：{'、'.join(missing[:2])}。" if missing else ''))
    elif band == '有遗漏':
        feedback = f"你提到了{'、'.join(hits[:2]) or '一部分要点'}，但还缺{'、'.join(missing[:3])}。先补上这些再往下。"
    else:
        feedback = (f"先回到定义：{point.key_points[0] if point.key_points else point.summary}"
                    '用自己的话把这条说清楚，再回来做这一步。')

    nxt = _step_payload(point, index + 1) if index < TOTAL_STEPS else None
    result = {
        'mode': 'demo',
        'notice': None,
        'point': {'id': point.id, 'title': point.title, 'topic': point.topic,
                  'source': point.source, 'verified': point.verified},
        'step': step,
        'verdict': verdict,
        'band': band,
        'coverage': coverage,
        'signals_hit': hits,
        'signals_missing': missing,
        'numeric_check': numeric,
        'feedback': feedback,
        'follow_up': FOLLOW_UPS.get(step['kind'], '你能用一句话说明这一步的依据吗？'),
        'next_step': nxt,
        'completed': nxt is None,
        'memory_weight': weight,
        'repeat_rule': ('按长期记忆口径记一条证据；同一知识点连续两次「基本到位」不代表已掌握，'
                        '掌握度仍由全部可核对证据汇总。'),
        'references': [hit.as_dict(position) for position, hit in enumerate(
            knowledge.retrieve(f'{point.title} {cleaned[:200]}', topic=point.topic, top_k=2), 1)],
        'method': '规则关键词覆盖率 + 本地数学工具数值核对（演示模式未调用模型）',
    }

    if settings.resolved_mode == 'live':
        try:
            raw, _meta = resilience.call_model(
                lambda: chat(prompts.build_practice_messages(result, point, cleaned), settings),
                endpoint='POST /api/agent/practice/answer',
            )
        except (ModelUnavailable, ModelCallFailed) as exc:
            result['notice'] = f'模型反馈生成失败，已保留规则结论（原因：{exc}）。'
        else:
            parsed = extract_json(raw)
            feedback = resilience.coerce_text((parsed or {}).get('feedback'), '', 800)
            if feedback:
                result['feedback'] = feedback
                result['follow_up'] = resilience.coerce_text((parsed or {}).get('follow_up'),
                                                             result['follow_up'], 200)
                result['mode'] = 'live'
                result['notice'] = None
                result['method'] = ('规则覆盖率 + 数值核对 + 模型润色反馈'
                                    '（模型不得改动 band、verdict 与数值核对结论）')
            else:
                result['notice'] = '模型未按约定返回 JSON，已使用规则反馈。'
    return result


def step_count() -> int:
    return TOTAL_STEPS


def describe() -> dict:
    """给能力探针用的说明。"""
    return {
        'total_steps': TOTAL_STEPS,
        'step_titles': [title for _kind, title, _template in STEP_TEMPLATES],
        'focus_rule': FOCUS_RULE,
        'answer_rule': ANSWER_RULE,
        'numeric_topics': sorted(CHECKS),
        'hint_levels_reused': sorted(hints.LEVEL_TITLES),
    }
