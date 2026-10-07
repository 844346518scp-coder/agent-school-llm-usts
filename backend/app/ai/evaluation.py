"""B 模块准确性评测（9/25–27 交付项：准确性评测）。

评测什么：检索命中、主题推断、诊断命中、资源检索、数学工具、记忆口径、诚实性（demo 不得冒充模型）。
不评测什么：真实模型的语言质量 —— 没有配置凭据时无法评测，报告里明确写出未评测范围，不宣称模型效果。

设计原则：

- 评测集写在代码里（可评审、可回归），每个用例都给出“期望值 + 实际值”，失败可复现；
- 每条 suite 有独立阈值，整体通过要求所有 suite 都达标；
- 结果可用于交付材料：`python tests/check_agent_accuracy.py --out <文件>`。

新增用例时只加数据，不加逻辑分支；阈值调整必须同时更新 docs 里的评测报告。
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import corrections, hints, knowledge, mathcheck, memory, plotting, resilience, voice
from .config import AgentSettings, load_settings
from .llm import ModelCallFailed, ModelUnavailable

EVAL_VERSION = '0.4.0'

# ------------------------------------------------------------------ 评测集

# 9/20 最小版就有的题集，这里保留同样的期望，保证回归可比。
RETRIEVAL_CASES = (
    ('求 lim(x→0) sin(x)/x', 'important-limits'),
    ('函数极限的 ε-δ 定义是什么', 'limit-definition'),
    ('讨论 x=1 处是否连续', 'continuity'),
    ('用定义求导数', 'derivative-definition'),
    ('复合函数求导 链式法则', 'derivative-rules'),
    ('用洛必达法则求极限', 'limit-techniques'),
    ('求曲线的单调区间与极值', 'derivative-application'),
    ('不定积分与原函数', 'integral-antiderivative'),
    ('定积分求曲边梯形面积', 'integral-definite'),
    ('微积分基本定理 牛顿-莱布尼茨公式', 'integral-ftc'),
    ('换元积分法与分部积分法', 'integral-techniques'),
    ('正项级数收敛判别', 'series-convergence'),
)

TOPIC_CASES = (
    ('求 lim(x→0) sin x / x', '极限与连续'),
    ('用定义求 x^2 的导数', '导数与微分'),
    ('定积分换元法', '一元函数积分学'),
    ('幂级数的收敛半径', '无穷级数'),
    # 课本未覆盖的主题必须返回 None：猜成相邻主题会误导学生与教师。
    ("微分方程 y'=y 怎么解", None),
    ('概率论里的条件概率', None),
)

DIAGNOSIS_CASES = (
    ('我把 0/0 直接代入然后用洛必达法则', 'limit-techniques'),
    ('x=1 处看不出左右极限是否相等', 'limit-definition'),
    ('复合函数求导时漏乘内层导数', 'derivative-rules'),
)

RESOURCE_CASES = (
    ('极限的定义', 'limit-definition-concept'),
    ('洛必达法则', 'limit-techniques-concept'),
    ('分部积分', 'integral-techniques-example'),
    ('级数收敛判别', 'series-convergence-concept'),
    ('导数定义', 'derivative-definition-example'),
    ('单调性判别', 'derivative-application-concept'),
)

EVALUATE_CASES = (
    ('x^2', 3.0, 9.0),
    ('x^2-1', -1.0, 0.0),
    ('2x+1', 2.0, 5.0),
    ('(x+1)(x-1)', 3.0, 8.0),
    ('sqrt(1+x^2)', 0.0, 1.0),
    ('exp(-x^2)', 0.0, 1.0),
    ('ln(x)', math.e, 1.0),
)

DERIVATIVE_CASES = (
    ('x^2', '2*x'),
    ('sin(x)', 'cos(x)'),
    ('1/x', '-1/x^2'),
    ('ln(x)', '1/x'),
    ('sqrt(x)', '1/(2*sqrt(x))'),
    ('x^3-3*x', '3*x^2-3'),
    ('exp(-x^2)', '-2*x*exp(-x^2)'),
)

LIMIT_CASES = (
    ('sin(x)/x', 0.0, 1.0),
    ('(x^2-1)/(x-1)', 1.0, 2.0),
    ('(1+1/x)^x', 'inf', math.e),
    ('1/x', 0.0, None),
)

STATUS_RULE_CASES = (
    (0.5, 0, 'unseen'),
    (0.3, 3, 'weak'),
    (0.8, 2, 'mastered'),
    (0.6, 1, 'learning'),
)

HINT_LEVEL_CASES = (
    ('求 lim(x→0) sin(x)/x 的极限', 1),
    ('用定义求 x^2 的导数', 2),
    ('换元法求不定积分', 3),
)


def _case(name: str, expected, actual, ok: bool | None = None) -> dict:
    return {'case': name, 'expected': expected, 'actual': actual,
            'ok': bool(expected == actual) if ok is None else bool(ok)}


# ------------------------------------------------------------------ 各 suite

def suite_retrieval() -> list[dict]:
    rows: list[dict] = []
    for query, expected in RETRIEVAL_CASES:
        hits = knowledge.retrieve(query, top_k=3)
        top = hits[0].point.id if hits else None
        rows.append(_case(query, expected, top))
    return rows


def suite_topic() -> list[dict]:
    return [_case(text, expected, knowledge.suggest_topic(text)) for text, expected in TOPIC_CASES]


def suite_diagnosis() -> list[dict]:
    from . import diagnosis

    rows: list[dict] = []
    for text, expected in DIAGNOSIS_CASES:
        weak = diagnosis.weak_points(text)
        rows.append(_case(text, expected, weak[0]['id'] if weak else None))
    return rows


def suite_resources() -> list[dict]:
    rows: list[dict] = []
    for query, expected_id in RESOURCE_CASES:
        items = knowledge.search_resources(query, limit=3)
        ids = [item['id'] for item in items]
        rows.append(_case(query, f'{expected_id} in top3',
                          expected_id if expected_id in ids else ids, expected_id in ids))
    return rows


def suite_math() -> list[dict]:
    rows: list[dict] = []
    for expr, x, expected in EVALUATE_CASES:
        actual = mathcheck.safe_value(expr, x)
        ok = actual is not None and abs(actual - expected) <= 1e-9 * max(1.0, abs(expected))
        rows.append(_case(f'evaluate {expr} at x={x}', expected, actual, ok))
    for expr, expected_derivative in DERIVATIVE_CASES:
        report = mathcheck.derivative_report(expr)
        if not report['ok']:
            rows.append(_case(f"d/dx {expr}", expected_derivative, report['error'], False))
            continue
        check = mathcheck.equivalent(report['derivative'], expected_derivative, x_min=0.5, x_max=3.0)
        rows.append(_case(f"d/dx {expr}", expected_derivative, report['derivative'], check['ok']))
    for expr, x0, expected in LIMIT_CASES:
        probe = mathcheck.probe_limit(expr, x0)
        if expected is None:
            rows.append(_case(f'limit {expr} at {x0}', 'not detected', probe['candidate'], probe['ok'] is False))
        else:
            candidate = probe['candidate']
            ok = probe['ok'] and candidate is not None and abs(candidate - expected) <= 5e-3
            rows.append(_case(f'limit {expr} at {x0}', expected, candidate, ok))
    return rows


def suite_memory_rules() -> list[dict]:
    rows = [_case(f'status({mastery}, {attempts})', expected, memory._status_of(mastery, attempts))
            for mastery, attempts, expected in STATUS_RULE_CASES]
    positives = [{'weight': 1, 'created_at': '2026-09-01T00:00:00+00:00'},
                 {'weight': 1, 'created_at': '2026-09-02T00:00:00+00:00'}]
    aggregate = memory._aggregate_point('limit-definition', positives)
    rows.append(_case('mastery of 2 positive events', 0.75, aggregate['mastery']))
    rows.append(_case('status of 2 positive events', 'mastered', aggregate['status']))
    negatives = positives + [{'weight': -2, 'created_at': '2026-09-03T00:00:00+00:00'}]
    rows.append(_case('mastery penalty for negative evidence', 0.5, memory._aggregate_point('limit-definition', negatives)['mastery']))
    rows.append(_case('teacher correction default weight (correct)', 2, corrections.weight_for('correct')))
    rows.append(_case('teacher correction default weight (incorrect)', -2, corrections.weight_for('incorrect')))
    rows.append(_case('teacher correction weight is clamped', 3, corrections.weight_for('correct', weight=99)))
    return rows


def suite_honesty(settings: AgentSettings | None = None) -> list[dict]:
    """诚实性不变量：演示内容不得冒充模型输出，功能未配置时不得返回编造结果。"""
    from . import diagnosis, service

    settings = settings or load_settings()
    rows: list[dict] = []

    answer, mode, _notice = service.compose_answer('求 lim(x→0) sin x/x', '函数与极限', 'student', 'demo',
                                                  knowledge.retrieve('sin(x)/x', top_k=1))
    rows.append(_case('demo answer mode', 'demo', mode))
    rows.append(_case('demo answer carries preset marker', True, '【固定例题演示】' in answer))

    feedback = diagnosis.step_feedback('求 x^2 的导数', '先写出差商 (x+h)^2 - x^2', topic='导数与微分')
    rows.append(_case('demo step feedback never claims correct', 'unclear', feedback['verdict']))

    distinct = True
    for query, level in HINT_LEVEL_CASES:
        built = hints.build(query, level=level, settings=settings)
        if built['answer_leaked'] is not False or not built['hint'].strip():
            distinct = False
    rows.append(_case('hints never leak a final answer', True, distinct))

    if not settings.voice_ready:
        try:
            voice.transcribe({'bytes': b'\x00' * 1024, 'media_type': 'audio/wav', 'size': 1024})
        except (VoiceUnavailable_ := voice.VoiceUnavailable):  # noqa: F841 - 只关心被抛出
            rows.append(_case('voice without credentials is refused', 'raised', 'raised'))
        except Exception as exc:  # noqa: BLE001
            rows.append(_case('voice without credentials is refused', 'raised', type(exc).__name__, False))
        else:
            rows.append(_case('voice without credentials is refused', 'raised', 'returned text', False))
    else:
        rows.append(_case('voice without credentials is refused', 'skipped (credentials configured)', 'skipped', True))

    demo_plot = plotting.annotate('画 f(x)=x^2-1 的图像并标出零点', settings=settings)
    rows.append(_case('plot annotations come from the local tool', True,
                      demo_plot['function'] is not None and bool(demo_plot['samples'])))
    rows.append(_case('plot keeps its数值来源声明', True, '本地' in demo_plot['method']))
    return rows


SUITE_SPECS = (
    ('retrieval', '课程检索命中率（12 题，期望 top-1 命中）', 0.9, suite_retrieval),
    ('topic', '主题推断（含“覆盖不足必须返回 null”的负例）', 1.0, suite_topic),
    ('diagnosis', '薄弱知识点诊断命中（规则诊断）', 1.0, suite_diagnosis),
    ('resources', '资源检索命中（期望条目进入 top-3）', 0.8, suite_resources),
    ('math', '数学工具（求值 / 符号求导 / 极限探测）', 0.95, suite_math),
    ('memory_rules', '记忆与纠错口径（掌握度、状态阈值、纠错权重）', 1.0, suite_memory_rules),
    ('honesty', '诚实性不变量（demo 不冒充模型、未配置不编造）', 1.0, suite_honesty),
)

SUITE_NAMES = tuple(name for name, _title, _threshold, _runner in SUITE_SPECS)

SCOPE = ('只评测规则与本地检索（demo 模式即可复现）；真实模型的表达质量需要配置凭据后另行评测，'
         '本报告不据此宣称模型效果，也不代表学生学习效果。')

LIMITATIONS = (
    '极限与等价性由数值取样给出证据，不是严格证明；评测通过只说明取样点上一致。',
    '检索为本地 BM25（中文 bigram），没有语义向量；同义改写会掉分。',
    '诊断只覆盖关键词信号能触发的知识点，未覆盖的情形不会出现在评测集里。',
    '11–12 个知识点的内容仍是 verified=false，需课程资料复核后重跑本评测。',
)


def run(suites: tuple[str, ...] | None = None, settings: AgentSettings | None = None) -> dict:
    """运行评测并返回可序列化报告。"""
    settings = settings or load_settings()
    selected = tuple(suites) if suites else SUITE_NAMES
    unknown = [name for name in selected if name not in SUITE_NAMES]
    if unknown:
        raise ValueError(f'未知评测套件：{", ".join(unknown)}；可用：{", ".join(SUITE_NAMES)}')

    report_suites: list[dict] = []
    total = {'cases': 0, 'passed': 0}
    for name, title, threshold, runner in SUITE_SPECS:
        if name not in selected:
            continue
        rows = runner(settings) if name == 'honesty' else runner()
        passed = sum(1 for row in rows if row['ok'])
        rate = round(passed / len(rows), 3) if rows else 0.0
        report_suites.append({
            'name': name,
            'title': title,
            'cases': len(rows),
            'passed': passed,
            'failed': len(rows) - passed,
            'rate': rate,
            'threshold': threshold,
            'ok': rate >= threshold,
            'failures': [row for row in rows if not row['ok']][:5],
            'results': rows,
        })
        total['cases'] += len(rows)
        total['passed'] += passed

    overall_rate = round(total['passed'] / total['cases'], 3) if total['cases'] else 0.0
    return {
        'evaluation': 'b-module-accuracy',
        'version': EVAL_VERSION,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'mode': settings.resolved_mode,
        'knowledge': knowledge.stats(),
        'suites': report_suites,
        'overall': {
            'cases': total['cases'],
            'passed': total['passed'],
            'failed': total['cases'] - total['passed'],
            'rate': overall_rate,
            'ok': all(item['ok'] for item in report_suites) and bool(report_suites),
            'threshold_note': '每个 suite 必须分别达到各自阈值；任一套件未达标即整体不通过。',
        },
        'degradation': resilience.stats(),
        'scope': SCOPE,
        'limitations': list(LIMITATIONS),
        'known_fixed': [
            '「微分方程」等课本外主题曾被猜成“导数与微分”，已在 suggest_topic 增加范围外词表并加评测负例。',
            '表达式解析曾把 -x^2 当成 (-x)^2（乘方优先级低于一元负号），已修正为教材写法 -(x^2) 并加回归用例。',
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='B 模块准确性评测（规则与本地检索）')
    parser.add_argument('--suite', action='append', choices=SUITE_NAMES,
                        help='只跑指定套件，可重复；默认全部')
    parser.add_argument('--out', help='把完整 JSON 报告写到该路径（UTF-8）')
    parser.add_argument('--quiet', action='store_true', help='只输出总结行')
    args = parser.parse_args(argv)

    report = run(tuple(args.suite) if args.suite else None)
    for item in report['suites']:
        print(f"[{item['name']:<13}] cases={item['cases']:<3} passed={item['passed']:<3} "
              f"rate={item['rate']:.3f} threshold={item['threshold']:.2f} "
              f"{'OK' if item['ok'] else 'FAIL'}")
        if not item['ok'] and not args.quiet:
            for row in item['failures']:
                print(f"    - {row['case']}: expected {row['expected']!r}, got {row['actual']!r}")
    print(f"overall: {report['overall']['passed']}/{report['overall']['cases']} "
          f"rate={report['overall']['rate']:.3f} -> {'PASS' if report['overall']['ok'] else 'FAIL'}")

    if args.out:
        target = Path(args.out)
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'report written: {target}')
    return 0 if report['overall']['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
