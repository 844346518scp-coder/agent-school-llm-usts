"""B 模块图形批注（模块衔接图中的「圆圈图注：B 输出步骤、坐标与讲解」）。

分工：A 负责把这里返回的坐标与讲解渲染到画布上；B 负责**算出**坐标与步骤，并保证数值可复核。

硬约束：

- `samples` 与 `key_points` 一律由 `mathcheck` 本地算出（demo 模式也完全可用），模型只写讲解文字；
- 响应固定带 `honesty` 说明“模型不得改动数值”，前端展示时不要把讲解文字当结论；
- 题目里解析不出函数时如实返回 `plot_unparsed`，只给文字步骤，不编造图形；
- 数值探测（零点、极值）用取样定位，响应里带上方法说明，不宣称是严格推导。
"""
from __future__ import annotations

import math
import re
from typing import Sequence

from . import knowledge, mathcheck, prompts, resilience
from .config import AgentSettings, load_settings
from .llm import ModelCallFailed, ModelUnavailable, chat, extract_json

SPLIT_MARKS = re.compile(r'[，。；,;、?？!！\n]')
DEFAULT_X_MIN = -6.0
DEFAULT_X_MAX = 6.0
DEFAULT_SAMPLES = 49
MAX_SAMPLES = 241
CIRCLE_SAMPLES = 73

BOUNDARY_NOTE = ('图形与坐标用于帮助理解，不构成证明；结论仍要回到定义与定理的推导。'
                 '数值零点与极值由取样定位，可能存在遗漏。')


def _trim_to_parseable(text: str) -> str | None:
    """从左侧起保留最长的可解析前缀（要求含自变量 x），用于从题干里剥出表达式。"""
    candidate = (text or '').strip().rstrip('的')
    for cut in range(len(candidate), 0, -1):
        piece = candidate[:cut].strip()
        if not piece:
            continue
        try:
            node = mathcheck.parse(piece)
        except mathcheck.MathError:
            continue
        if 'x' in mathcheck.variables(node):
            return piece
    return None


def extract_expression(question: str) -> str | None:
    """从题目文本里提取函数表达式；提取不到返回 None（不猜）。"""
    text = (question or '').strip()
    if not text:
        return None
    for chunk in SPLIT_MARKS.split(text):
        if '=' not in chunk:
            continue
        found = _trim_to_parseable(chunk.split('=', 1)[1])
        if found:
            return found
    return _trim_to_parseable(text)


def _circle_samples(center: Sequence[float], radius: float, samples: int = CIRCLE_SAMPLES) -> list[list[float]]:
    cx, cy = float(center[0]), float(center[1])
    return [[round(cx + radius * math.cos(2 * math.pi * index / samples), 6),
             round(cy + radius * math.sin(2 * math.pi * index / samples), 6)]
            for index in range(samples + 1)]


def _key_points(expr: str, at: float | None, x_min: float, x_max: float) -> list[dict]:
    rows: list[dict] = []
    for zero in mathcheck.find_zeros(expr, x_min, x_max):
        rows.append({
            'kind': 'zero',
            'label': '与 x 轴交点',
            'x': zero,
            'y': 0.0,
            'explain': f'在 x≈{zero} 处函数值为 0（取样定位）。',
        })
    for extremum in mathcheck.find_extrema(expr, x_min, x_max):
        rows.append({
            'kind': 'extremum',
            'label': extremum['kind'],
            'x': extremum['x'],
            'y': extremum['y'],
            'explain': f"由 f′(x)=0 定位的{extremum['kind']}，坐标 ({extremum['x']}, {extremum['y']})。",
        })
    if at is not None:
        y = mathcheck.safe_value(expr, at)
        report = mathcheck.derivative_report(expr)
        if y is not None:
            slope = None
            if report['ok']:
                slope = mathcheck.safe_value(report['derivative'], at)
            rows.append({
                'kind': 'tangent',
                'label': '切点',
                'x': round(float(at), 6),
                'y': round(y, 6),
                'slope': None if slope is None else round(slope, 6),
                'explain': (f'切点 ({round(float(at), 6)}, {round(y, 6)})'
                            + (f'，切线斜率 k≈{round(slope, 6)}。' if slope is not None else '，切线斜率暂无法确认。')),
            })
    return rows


def _steps(expr: str, derived: dict, key_points: Sequence[dict], x_min: float, x_max: float,
           samples: int) -> list[dict]:
    rows: list[dict] = [{
        'index': 1,
        'title': '写出函数与定义域',
        'detail': f'$f(x)={derived["latex"]}$；绘图前先确认在区间内哪些点没有定义（分式看分母、偶次根式看被开方式）。',
        'points': [],
    }]
    rows.append({
        'index': 2,
        'title': '选定绘图区间并采样',
        'detail': f'在 $x\\in[{x_min},{x_max}]$ 上等距取 {samples} 个点连线；超出视窗的点会被裁掉，避免个别大值把图像压平。',
        'points': [],
    })
    if derived['ok']:
        rows.append({
            'index': 3,
            'title': '求导定位关键点',
            'detail': f'$f\'(x)={derived["derivative_latex"]}$，令 $f\'(x)=0$ 求驻点，再按符号变化判断极值。',
            'points': [],
        })
    else:
        rows.append({
            'index': 3,
            'title': '关键点定位受限',
            'detail': f'本工具未能对该函数求导（{derived["error"]}），只给出零点与采样图像。',
            'points': [],
        })
    coordinates = [[item['x'], item.get('y')] for item in key_points]
    if key_points:
        described = '；'.join(
            f"{item['label']}({item['x']}, {item.get('y')})" if item.get('y') is not None
            else f"{item['label']}(x={item['x']})" for item in key_points
        )
        detail = f'关键点：{described}。请对照图像确认这些点是否与你的计算一致。'
    else:
        detail = '在绘图区间内未定位到零点或极值点；这不等于不存在，可能落在区间之外。'
    rows.append({'index': 4, 'title': '标注关键点坐标', 'detail': detail, 'points': coordinates})
    rows.append({
        'index': 5,
        'title': '读图结论与自检',
        'detail': f'{BOUNDARY_NOTE} 试着只凭图像读出单调区间，再用导数符号验证一次。',
        'points': [],
    })
    return rows


def annotate(question: str = '', *, topic: str | None = None, expr: str | None = None,
             at: float | None = None, x_min: float = DEFAULT_X_MIN, x_max: float = DEFAULT_X_MAX,
             samples: int = DEFAULT_SAMPLES, circle: dict | None = None,
             settings: AgentSettings | None = None) -> dict:
    """生成图形批注：函数/圆 → 采样坐标 + 关键点 + 分步讲解（+ live 模式的文字讲解）。"""
    settings = settings or load_settings()
    low, high = (float(x_min), float(x_max)) if float(x_min) < float(x_max) else (DEFAULT_X_MIN, DEFAULT_X_MAX)
    count = max(2, min(MAX_SAMPLES, int(samples)))

    hits = knowledge.retrieve(f'{question} {expr or ""}'.strip(), topic=topic, top_k=3)
    references = [hit.as_dict(index) for index, hit in enumerate(hits, 1)]

    result = {
        'mode': 'demo',
        'notice': None,
        'question': question,
        'shape': 'function',
        'topic': knowledge.normalize_topic(topic),
        'function': None,
        'viewport': None,
        'samples': [],
        'key_points': [],
        'steps': [],
        'explanation': None,
        'step_notes': [],
        'references': references,
        'method': '本地数学工具采样与求导（未调用模型）',
        'honesty': '坐标与关键点由本地数学工具算出；模型只写讲解文字，不得改动任何数值。',
    }

    if circle:
        try:
            center = (float(circle.get('cx', 0.0)), float(circle.get('cy', 0.0)))
            radius = abs(float(circle.get('radius', 1.0)))
        except (TypeError, ValueError):
            result['notice'] = '圆心或半径不是合法数值，已忽略圆的参数。'
        else:
            result['shape'] = 'circle'
            result['samples'] = _circle_samples(center, radius)
            result['viewport'] = {
                'x_min': round(center[0] - radius - 1, 6), 'x_max': round(center[0] + radius + 1, 6),
                'y_min': round(center[1] - radius - 1, 6), 'y_max': round(center[1] + radius + 1, 6),
            }
            result['key_points'] = [
                {'kind': 'center', 'label': '圆心', 'x': center[0], 'y': center[1],
                 'explain': f'圆心 ({center[0]}, {center[1]})，半径 r={radius}。'},
                {'kind': 'radius_end', 'label': '半径端点', 'x': center[0] + radius, 'y': center[1],
                 'explain': '从圆心向右量出半径，用于确认圆的大小。'},
            ]
            result['steps'] = [
                {'index': 1, 'title': '确定圆心与半径', 'detail': f'圆心 ({center[0]}, {center[1]})，半径 {radius}。',
                 'points': [[center[0], center[1]]]},
                {'index': 2, 'title': '按定义采样画圆',
                 'detail': '按 x=cx+r·cos t、y=cy+r·sin t 取点连线，保证到圆心距离恒等于 r。',
                 'points': [[center[0] + radius, center[1]]]},
                {'index': 3, 'title': '核对图形', 'detail': f'{BOUNDARY_NOTE}', 'points': []},
            ]
            result['method'] = '本地采样画圆（未调用模型）'
            return result

    target = (expr or '').strip() or extract_expression(question)
    if not target:
        resilience.record('plot_unparsed', 'POST /api/agent/plot/annotate', '题干中没有可解析的函数表达式')
        result['notice'] = ('没有从题目里解析出函数表达式，无法生成图形批注；'
                           '可以把函数写成 f(x)=… 或 y=… 的形式，或直接传 expr 参数。')
        result['steps'] = [{
            'index': 1,
            'title': '需要先明确函数',
            'detail': '例如「画 f(x)=x^2-1 的图像并标出零点」，或在请求里直接给出 expr。',
            'points': [],
        }]
        return result

    try:
        node = mathcheck.parse(target)
    except mathcheck.MathError as exc:
        result['notice'] = f'表达式无法解析（{exc}），未生成图形批注。'
        return result

    derived = mathcheck.derivative_report(target)
    curve = mathcheck.sample_curve(target, x_min=low, x_max=high, samples=count)
    key_points = _key_points(target, at, low, high)

    result |= {
        'function': {
            'expr': mathcheck.to_text(mathcheck.simplify(node)),
            'latex': mathcheck.to_latex(node),
            'derivative': derived['derivative'],
            'derivative_latex': derived['derivative_latex'],
            'derivative_checked': None if not derived['ok'] else derived['numeric_agreement'],
        },
        'viewport': {'x_min': curve['x_min'], 'x_max': curve['x_max'],
                     'y_min': curve['y_min'], 'y_max': curve['y_max']},
        'samples': curve['points'],
        'clipped': curve['clipped'],
        'key_points': key_points,
        'steps': _steps(target, derived, key_points, low, high, count),
        'method': '本地数学工具：符号求导 + 数值采样 + 取样定位关键点（未调用模型）',
    }

    if settings.resolved_mode == 'live':
        try:
            raw, _meta = resilience.call_model(
                lambda: chat(prompts.build_plot_messages(result, hits), settings),
                endpoint='POST /api/agent/plot/annotate',
            )
        except (ModelUnavailable, ModelCallFailed) as exc:
            result['notice'] = f'模型讲解生成失败，已只返回本地坐标与步骤（原因：{exc}）。'
        else:
            parsed = extract_json(raw)
            explanation = resilience.coerce_text((parsed or {}).get('explanation'), '', 1200)
            if explanation:
                notes = (parsed or {}).get('step_notes')
                if isinstance(notes, (list, tuple)):
                    result['step_notes'] = [resilience.coerce_text(item, '', 300) for item in notes if
                                            resilience.coerce_text(item, '', 300)][:5]
                result['explanation'] = explanation
                result['mode'] = 'live'
                result['method'] = '本地坐标与步骤 + 模型讲解（模型不得改动数值）'
            else:
                result['notice'] = '模型未按约定返回 JSON，已只返回本地坐标与步骤。'
    return result
