"""B 模块数学工具（零第三方依赖）：表达式解析、数值求值、符号求导、极限数值探测、等价性校验。

边界与取舍（改动前必读）：

- 工具只做**可复核的计算**：符号求导给闭式，数值探测给区间上的证据；数值探测**不是证明**，
  所有结果都带 `method` 与 `note`，探测不到收敛时如实返回 `ok=False`，不猜结论。
- 不引入 sympy / numpy：嵌入式运行时（AGENTS.md 便携说明）不保证能安装第三方包，
  因此这里自己实现一个小表达式解析器（+ - * / ^、括号、sin/cos/tan/sqrt/exp/ln/log/abs、pi/e）。
- 求导不支持的函数（如 `abs`）抛出 `MathUnsupported`，由调用方降级说明，绝不静默返回错误结果。
"""
from __future__ import annotations

import math
import re
from typing import Iterable, Sequence

Node = tuple


class MathError(ValueError):
    """数学工具基础异常。"""


class MathParseError(MathError):
    """表达式无法解析。"""


class MathEvalError(MathError):
    """表达式能解析但无法求值（定义域、除零、溢出等）。"""


class MathUnsupported(MathError):
    """当前工具不支持该写法（例如对 abs 求导）。"""


CONSTANTS = {'pi': math.pi, 'e': math.e}
FUNCTIONS = ('sin', 'cos', 'tan', 'sqrt', 'exp', 'ln', 'log', 'abs')
# log 采用常用对数（底 10），ln 为自然对数；文档与提示里必须写清楚，避免学生误解。
LN10 = math.log(10)

_TOKEN = re.compile(r'\s*(\d+\.?\d*(?:[eE][-+]?\d+)?|[A-Za-z_][A-Za-z0-9_]*|[+\-*/^(),])')

_PREP = (
    ('−', '-'), ('–', '-'), ('×', '*'), ('÷', '/'), ('·', '*'),
    ('（', '('), ('）', ')'), ('，', ','), ('²', '^2'), ('³', '^3'),
)


def _preprocess(text: str) -> str:
    cleaned = (text or '').strip()
    for source, target in _PREP:
        cleaned = cleaned.replace(source, target)
    # 根号：先处理 √(...)，再处理 √后面的单个因子，避免把 sqrt(x) 拼成 sqrtx。
    cleaned = re.sub(r'√\s*\(', 'sqrt(', cleaned)
    cleaned = re.sub(r'√\s*([A-Za-z0-9.]+)', r'sqrt(\1)', cleaned)
    return cleaned


def _starts_operand(token: str) -> bool:
    return token == '(' or token in FUNCTIONS or bool(re.match(r'^[A-Za-z0-9.]', token))


def _ends_operand(token: str) -> bool:
    return token == ')' or bool(re.match(r'^[A-Za-z0-9.]', token))


def tokenize(text: str) -> list[str]:
    """切词并补上省略的乘号（如 ``2x``、``(x+1)(x-1)``、``3sin(x)``）。"""
    cleaned = _preprocess(text)
    if not cleaned:
        raise MathParseError('表达式为空')
    tokens: list[str] = []
    position = 0
    while position < len(cleaned):
        match = _TOKEN.match(cleaned, position)
        if not match:
            raise MathParseError(f'无法识别的字符：{cleaned[position]!r}')
        tokens.append(match.group(1))
        position = match.end()
    out: list[str] = []
    for token in tokens:
        if out:
            previous = out[-1]
            function_call = previous in FUNCTIONS and token == '('
            if not function_call and _ends_operand(previous) and _starts_operand(token):
                out.append('*')
        out.append(token)
    return out


def _parse_expr(tokens: Sequence[str], position: int) -> tuple[Node, int]:
    node, position = _parse_term(tokens, position)
    while position < len(tokens) and tokens[position] in ('+', '-'):
        operator = tokens[position]
        right, position = _parse_term(tokens, position + 1)
        node = ('add' if operator == '+' else 'sub', node, right)
    return node, position


def _parse_term(tokens: Sequence[str], position: int) -> tuple[Node, int]:
    node, position = _parse_unary(tokens, position)
    while position < len(tokens) and tokens[position] in ('*', '/'):
        operator = tokens[position]
        right, position = _parse_unary(tokens, position + 1)
        node = ('mul' if operator == '*' else 'div', node, right)
    return node, position


def _parse_unary(tokens: Sequence[str], position: int) -> tuple[Node, int]:
    """一元正负号。注意它比乘方低：-x^2 是 -(x^2)，与教材写法一致。"""
    if position < len(tokens) and tokens[position] in ('+', '-'):
        operator = tokens[position]
        node, position = _parse_unary(tokens, position + 1)
        return (node if operator == '+' else ('neg', node)), position
    return _parse_power(tokens, position)


def _parse_power(tokens: Sequence[str], position: int) -> tuple[Node, int]:
    node, position = _parse_primary(tokens, position)
    if position < len(tokens) and tokens[position] == '^':
        right, position = _parse_unary(tokens, position + 1)  # 右结合，且允许 x^-2
        return ('pow', node, right), position
    return node, position


def _parse_primary(tokens: Sequence[str], position: int) -> tuple[Node, int]:
    if position >= len(tokens):
        raise MathParseError('表达式不完整')
    token = tokens[position]
    if token == '(':
        node, position = _parse_expr(tokens, position + 1)
        if position >= len(tokens) or tokens[position] != ')':
            raise MathParseError('括号不匹配')
        return node, position + 1
    if token in FUNCTIONS:
        if position + 1 >= len(tokens) or tokens[position + 1] != '(':
            raise MathParseError(f'{token} 需要写成 {token}(...) 的形式')
        argument, position = _parse_expr(tokens, position + 2)
        if position >= len(tokens) or tokens[position] != ')':
            raise MathParseError('函数括号不匹配')
        return ('call', token, argument), position + 1
    if token in CONSTANTS:
        return ('num', CONSTANTS[token]), position + 1
    if re.match(r'^\d', token):
        try:
            return ('num', float(token)), position + 1
        except ValueError as exc:  # 理论上不会发生，兜底避免异常逃逸
            raise MathParseError(f'无法解析数字：{token}') from exc
    if re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', token):
        return ('var', token), position + 1
    raise MathParseError(f'无法解析的记号：{token}')


def parse(text: str) -> Node:
    """把表达式文本解析成语法树；失败抛 ``MathParseError``。"""
    tokens = tokenize(text)
    node, position = _parse_expr(tokens, 0)
    if position != len(tokens):
        raise MathParseError(f'表达式末尾有多余内容：{" ".join(tokens[position:])}')
    return node


def variables(node: Node) -> set[str]:
    kind = node[0]
    if kind == 'var':
        return {node[1]}
    if kind in ('num',):
        return set()
    if kind == 'neg':
        return variables(node[1])
    if kind == 'call':
        return variables(node[2])
    return variables(node[1]) | variables(node[2])


def evaluate(expr: str | Node, values: dict | float | int | None = None) -> float:
    """数值求值；``values`` 可传 ``{'x': 1.5}`` 或直接传 x 的值。"""
    node = parse(expr) if isinstance(expr, str) else expr
    if isinstance(values, (int, float)):
        values = {'x': float(values)}
    scope = {name: float(value) for name, value in (values or {}).items()}
    return _evaluate(node, scope)


def _evaluate(node: Node, scope: dict) -> float:
    kind = node[0]
    if kind == 'num':
        return float(node[1])
    if kind == 'var':
        if node[1] not in scope:
            raise MathEvalError(f'缺少变量取值：{node[1]}')
        return float(scope[node[1]])
    if kind == 'neg':
        return -_evaluate(node[1], scope)
    if kind == 'add':
        return _finite(_evaluate(node[1], scope) + _evaluate(node[2], scope))
    if kind == 'sub':
        return _finite(_evaluate(node[1], scope) - _evaluate(node[2], scope))
    if kind == 'mul':
        return _finite(_evaluate(node[1], scope) * _evaluate(node[2], scope))
    if kind == 'div':
        denominator = _evaluate(node[2], scope)
        if denominator == 0:
            raise MathEvalError('出现除以零，该点不在定义域内')
        return _finite(_evaluate(node[1], scope) / denominator)
    if kind == 'pow':
        base = _evaluate(node[1], scope)
        exponent = _evaluate(node[2], scope)
        if base < 0 and abs(exponent - round(exponent)) > 1e-12:
            raise MathEvalError('负数取非整数次幂，该点不在实数定义域内')
        return _finite(base ** exponent)
    if kind == 'call':
        name = node[1]
        argument = _evaluate(node[2], scope)
        if name == 'sin':
            return math.sin(argument)
        if name == 'cos':
            return math.cos(argument)
        if name == 'tan':
            return math.tan(argument)
        if name == 'exp':
            return _finite(math.exp(argument))
        if name == 'ln':
            if argument <= 0:
                raise MathEvalError('ln 的定义域是正数')
            return math.log(argument)
        if name == 'log':
            if argument <= 0:
                raise MathEvalError('log 的定义域是正数')
            return math.log10(argument)
        if name == 'sqrt':
            if argument < 0:
                raise MathEvalError('sqrt 的定义域是非负数')
            return math.sqrt(argument)
        if name == 'abs':
            return abs(argument)
    raise MathUnsupported(f'不支持的运算：{kind}')


def _finite(value: float) -> float:
    if not math.isfinite(value):
        raise MathEvalError('计算结果溢出或未定义')
    return value


# ------------------------------------------------------------------ 符号求导

def differentiate(expr: str | Node) -> Node:
    """对变量 x 求导，返回语法树；不支持的写法抛 ``MathUnsupported``。"""
    node = parse(expr) if isinstance(expr, str) else expr
    return _diff(node)


def _diff(node: Node) -> Node:
    kind = node[0]
    if kind == 'num':
        return ('num', 0.0)
    if kind == 'var':
        return ('num', 1.0 if node[1] == 'x' else 0.0)
    if kind == 'neg':
        return ('neg', _diff(node[1]))
    if kind in ('add', 'sub'):
        return (kind, _diff(node[1]), _diff(node[2]))
    if kind == 'mul':
        left, right = node[1], node[2]
        return ('add', ('mul', _diff(left), right), ('mul', left, _diff(right)))
    if kind == 'div':
        numerator, denominator = node[1], node[2]
        return ('div',
                ('sub', ('mul', _diff(numerator), denominator), ('mul', numerator, _diff(denominator))),
                ('pow', denominator, ('num', 2.0)))
    if kind == 'pow':
        base, exponent = node[1], node[2]
        base_diff = _diff(base)
        if exponent[0] == 'num':  # 幂函数：n·u^(n-1)·u'
            power = ('num', exponent[1] - 1)
            return ('mul', ('mul', ('num', exponent[1]), ('pow', base, power)), base_diff)
        # 一般幂指函数：u^v = exp(v·ln u)，按链式法则展开
        exponent_diff = _diff(exponent)
        return ('mul', node, ('add', ('mul', exponent_diff, ('call', 'ln', base)),
                              ('div', ('mul', exponent, base_diff), base)))
    if kind == 'call':
        name, argument = node[1], node[2]
        argument_diff = _diff(argument)
        if name == 'sin':
            outer: Node = ('call', 'cos', argument)
        elif name == 'cos':
            outer = ('neg', ('call', 'sin', argument))
        elif name == 'tan':
            outer = ('div', ('num', 1.0), ('pow', ('call', 'cos', argument), ('num', 2.0)))
        elif name == 'exp':
            outer = ('call', 'exp', argument)
        elif name == 'ln':
            outer = ('div', ('num', 1.0), argument)
        elif name == 'log':
            outer = ('div', ('num', 1.0), ('mul', argument, ('num', LN10)))
        elif name == 'sqrt':
            outer = ('div', ('num', 1.0), ('mul', ('num', 2.0), ('call', 'sqrt', argument)))
        elif name == 'abs':
            raise MathUnsupported('abs 的导数在 0 处不存在，本工具不给出结果')
        else:
            raise MathUnsupported(f'不支持的函数求导：{name}')
        return ('mul', outer, argument_diff)
    raise MathUnsupported(f'不支持的运算求导：{kind}')


# ------------------------------------------------------------------ 文本化

def simplify(node: Node) -> Node:
    """轻量化简：去 0/1、折叠常量、合并双重负号，让展示文本接近教材写法。

    只做恒等变形，不改变函数值；不追求最简形式（本工具的定位是可复核，不是 CAS）。
    """
    kind = node[0]
    if kind in ('num', 'var'):
        return node
    if kind == 'neg':
        inner = simplify(node[1])
        if inner[0] == 'num':
            return ('num', -inner[1])
        if inner[0] == 'neg':
            return inner[1]
        return ('neg', inner)
    if kind == 'call':
        return ('call', node[1], simplify(node[2]))
    if kind == 'pow':
        base, exponent = simplify(node[1]), simplify(node[2])
        if exponent[0] == 'num':
            if exponent[1] == 0:
                return ('num', 1.0)
            if exponent[1] == 1:
                return base
        if base[0] == 'num' and exponent[0] == 'num':
            try:
                return ('num', float(_evaluate(('pow', base, exponent), {})))
            except MathError:
                return ('pow', base, exponent)
        return ('pow', base, exponent)

    left, right = simplify(node[1]), simplify(node[2])
    if kind in ('add', 'sub'):
        if kind == 'add' and left[0] == 'num' and right[0] == 'num':
            return ('num', left[1] + right[1])
        if kind == 'sub' and left[0] == 'num' and right[0] == 'num':
            return ('num', left[1] - right[1])
        if right[0] == 'num' and right[1] == 0:
            return left
        if kind == 'add' and left[0] == 'num' and left[1] == 0:
            return right
        if kind == 'sub' and left[0] == 'num' and left[1] == 0:
            return simplify(('neg', right))
        return (kind, left, right)
    if kind == 'mul':
        if (left[0] == 'num' and left[1] == 0) or (right[0] == 'num' and right[1] == 0):
            return ('num', 0.0)
        if left[0] == 'num' and left[1] == 1:
            return right
        if right[0] == 'num' and right[1] == 1:
            return left
        if left[0] == 'num' and right[0] == 'num':
            return ('num', left[1] * right[1])
        return ('mul', left, right)
    if kind == 'div':
        if right[0] == 'num' and right[1] == 1:
            return left
        if left[0] == 'num' and left[1] == 0:
            return ('num', 0.0)
        return ('div', left, right)
    return (kind, left, right)


def _number_text(value: float) -> str:
    if value == int(value) and abs(value) < 1e15:
        return str(int(value))
    return f'{value:.6g}'


def to_text(node: Node, parent_precedence: int = 0) -> str:
    """把语法树还原成可读文本（带必要括号）。"""
    kind = node[0]
    if kind == 'num':
        return _number_text(node[1])
    if kind == 'var':
        return node[1]
    if kind == 'neg':
        inner = to_text(node[1], 3)
        return f'-{inner}' if parent_precedence > 3 else f'(-{inner})'
    if kind == 'call':
        return f'{node[1]}({to_text(node[2])})'
    if kind == 'pow':
        return f'{to_text(node[1], 4)}^{to_text(node[2])}'
    precedence = 1 if kind in ('add', 'sub') else 2
    symbol = {'add': ' + ', 'sub': ' - ', 'mul': ' * ', 'div': ' / '}[kind]
    text = f'{to_text(node[1], precedence)}{symbol}{to_text(node[2], precedence + 1)}'
    return f'({text})' if parent_precedence > precedence else text


_LATEX_WRAP = {'sin': r'\sin', 'cos': r'\cos', 'tan': r'\tan', 'exp': r'\exp',
               'ln': r'\ln', 'log': r'\log', 'sqrt': r'\sqrt', 'abs': r'\left|\right|'}


def to_latex(node: Node, parent_precedence: int = 0) -> str:
    """把语法树渲染成 LaTeX（前端可直接交给 KaTeX）。"""
    kind = node[0]
    if kind == 'num':
        return _number_text(node[1])
    if kind == 'var':
        return node[1]
    if kind == 'neg':
        inner = to_latex(node[1], 3)
        return f'-{inner}' if parent_precedence > 3 else f'\\left(-{inner}\\right)'
    if kind == 'call':
        name, argument = node[1], node[2]
        if name == 'sqrt':
            return rf'\sqrt{{{to_latex(argument)}}}'
        if name == 'abs':
            return rf'\left|{to_latex(argument)}\right|'
        function = _LATEX_WRAP.get(name, name)
        return f'{function}\\left({to_latex(argument)}\\right)'
    if kind == 'pow':
        return f'{to_latex(node[1], 4)}^{{{to_latex(node[2])}}}'
    if kind == 'div':
        return rf'\frac{{{to_latex(node[1])}}}{{{to_latex(node[2])}}}'
    precedence = 1 if kind in ('add', 'sub') else 2
    symbol = {'add': '+', 'sub': '-', 'mul': r'\cdot '}[kind]
    text = f'{to_latex(node[1], precedence)} {symbol} {to_latex(node[2], precedence + 1)}'
    return f'\\left({text}\\right)' if parent_precedence > precedence else text


def derivative_report(expr: str) -> dict:
    """符号求导结果（含文本与 LaTeX，失败时说明原因）。"""
    node = parse(expr)
    try:
        derived = simplify(_diff(node))
    except MathUnsupported as exc:
        return {
            'ok': False,
            'error': str(exc),
            'expression': to_text(node),
            'latex': to_latex(node),
            'derivative': None,
            'derivative_latex': None,
            'method': '符号求导（本工具支持多项式、幂、sin/cos/tan、exp/ln/log、sqrt）',
        }
    return {
        'ok': True,
        'error': None,
        'expression': to_text(node),
        'latex': to_latex(node),
        'derivative': to_text(derived),
        'derivative_latex': to_latex(derived),
        'numeric_agreement': numeric_derivative_agreement(node, derived),
        'method': '符号求导（零依赖内置实现，可被数值取样复核）',
    }


DERIVATIVE_CHECK_POINTS = (0.4, 0.9, 1.7, 2.3)


def numeric_derivative_agreement(node: Node, derived: Node, points: Sequence[float] = DERIVATIVE_CHECK_POINTS,
                                h: float = 1e-5, tolerance: float = 1e-4) -> dict:
    """用中心差商复核符号求导结果：两边都算得出时才比较，得出结果不一致就如实报告。"""
    checked = 0
    matched = 0
    worst = 0.0
    mismatches: list[float] = []
    for x in points:
        symbolic = safe_value(derived, x)
        forward = safe_value(node, x + h)
        backward = safe_value(node, x - h)
        if symbolic is None or forward is None or backward is None:
            continue
        approximate = (forward - backward) / (2 * h)
        checked += 1
        scale = max(1.0, abs(symbolic), abs(approximate))
        difference = abs(symbolic - approximate) / scale
        worst = max(worst, difference)
        if difference <= tolerance:
            matched += 1
        elif len(mismatches) < 4:
            mismatches.append(round(x, 4))
    return {
        'checked': checked,
        'matched': matched,
        'ok': checked > 0 and matched == checked,
        'max_relative_diff': round(worst, 9),
        'mismatch_at': mismatches,
        'method': '中心差商数值复核（h=1e-5）；等价性为近似证据，可用于发现实现错误',
    }


# ------------------------------------------------------------------ 数值工具

MAX_ABS_VALUE = 1e12


def safe_value(expr: str | Node, x: float) -> float | None:
    """求值失败返回 None（不抛异常），供取样与探测循环使用。"""
    try:
        value = evaluate(expr, {'x': x})
    except MathError:
        return None
    return value if abs(value) <= MAX_ABS_VALUE else None


def equivalent(left: str | Node, right: str | Node, x_min: float = -4.0, x_max: float = 4.0,
               samples: int = 33, tolerance: float = 1e-6) -> dict:
    """数值等价性校验：在区间上取样比较两个表达式，返回可比点数与最大偏差。"""
    matched = 0
    checked = 0
    worst = 0.0
    failures: list[float] = []
    for index in range(samples):
        x = x_min + (x_max - x_min) * index / max(1, samples - 1)
        first = safe_value(left, x)
        second = safe_value(right, x)
        if first is None or second is None:
            continue
        checked += 1
        scale = max(1.0, abs(first), abs(second))
        difference = abs(first - second) / scale
        worst = max(worst, difference)
        if difference <= tolerance:
            matched += 1
        elif len(failures) < 5:
            failures.append(round(x, 4))
    ok = checked >= max(5, samples // 3) and matched == checked
    return {
        'ok': ok,
        'checked': checked,
        'matched': matched,
        'max_relative_diff': round(worst, 9),
        'counter_examples': failures,
        'tolerance': tolerance,
        'method': f'数值等价性校验（区间 [{x_min}, {x_max}] 内 {samples} 个取样点）',
        'note': '数值等价不是严格证明；取样点全部吻合可作复核证据，不吻合则一定不等价。',
    }


def probe_limit(expr: str, x0: float | str, side: str = 'both', tolerance: float = 1e-3) -> dict:
    """数值探测极限：不承诺严格证明，只报告两侧取样是否收敛及候选值。"""
    if side not in ('both', 'left', 'right'):
        raise MathError('side 只能是 both / left / right')
    steps = (1e-1, 5e-2, 1e-2, 1e-3, 1e-4, 1e-5)
    try:
        target = math.inf if str(x0).lower() in ('inf', '+inf', 'infinity') else (
            -math.inf if str(x0).lower() in ('-inf', '-infinity') else float(x0))
    except (TypeError, ValueError) as exc:
        raise MathError('x0 不是合法的趋近点') from exc

    def samples_for(direction: str) -> list[dict]:
        rows: list[dict] = []
        for h in steps:
            if math.isinf(target):
                if target > 0:
                    x = 1.0 / h if direction == 'right' else -1.0 / h
                else:
                    x = -1.0 / h if direction == 'right' else 1.0 / h
            else:
                x = target - h if direction == 'left' else target + h
            value = safe_value(expr, x)
            rows.append({'x': x, 'value': None if value is None else round(value, 8)})
        return rows

    directions = ['left', 'right'] if side == 'both' else [side]
    sides: list[dict] = []
    for direction in directions:
        rows = samples_for(direction)
        values = [row['value'] for row in rows if row['value'] is not None]
        converges = False
        candidate = None
        if len(values) >= 3:
            tail = values[-3:]
            spread = max(tail) - min(tail)
            converges = spread <= max(tolerance, 1e-2) * max(1.0, abs(tail[-1]))
            candidate = tail[-1]
        sides.append({
            'side': direction,
            'converges': converges,
            'candidate': None if candidate is None else round(candidate, 6),
            'samples': rows,
        })

    converging = [item for item in sides if item['converges']]
    ok = bool(converging) and (side != 'both' or len(converging) == len(sides))
    candidates = [item['candidate'] for item in converging]
    if ok and len(candidates) == 2 and abs(candidates[0] - candidates[1]) > max(tolerance, 1e-2):
        ok = False  # 左右极限不同：双侧极限不存在
    return {
        'ok': ok,
        'x0': 'inf' if target == math.inf else ('-inf' if target == -math.inf else target),
        'candidate': None if not ok else round(sum(candidates) / len(candidates), 6),
        'sides': sides,
        'tolerance': tolerance,
        'method': '数值取样探测（步长 1e-1 递减到 1e-5）；不是严格证明',
        'note': '探测到收敛只作为复核证据；要作为结论必须配合定义或定理的推导。',
    }


def find_zeros(expr: str, x_min: float = -6.0, x_max: float = 6.0, steps: int = 240) -> list[float]:
    """在区间上扫描符号变化并用二分法细化，返回零点近似值。"""
    zeros: list[float] = []
    previous_x = x_min
    previous_y = safe_value(expr, previous_x)
    for index in range(1, steps + 1):
        x = x_min + (x_max - x_min) * index / steps
        y = safe_value(expr, x)
        if y is None:
            previous_x, previous_y = x, None
            continue
        if y == 0:
            zeros.append(round(x, 6))
        elif previous_y is not None and previous_y * y < 0:
            low, high = previous_x, x
            for _ in range(60):
                middle = (low + high) / 2
                middle_y = safe_value(expr, middle)
                if middle_y is None:
                    break
                if middle_y == 0:
                    low = high = middle
                    break
                if previous_y * middle_y < 0:
                    high = middle
                else:
                    low, previous_y = middle, middle_y
            zeros.append(round((low + high) / 2, 6))
        previous_x, previous_y = x, y
    unique: list[float] = []
    for value in zeros:
        if not unique or abs(value - unique[-1]) > 1e-4:
            unique.append(value)
    return unique


def find_extrema(expr: str, x_min: float = -6.0, x_max: float = 6.0) -> list[dict]:
    """用导数零点定位极值点，并给出该点坐标与类型（数值判定）。"""
    try:
        derived = simplify(_diff(parse(expr)))
    except (MathError, MathUnsupported):
        return []
    derivative_text = to_text(simplify(derived))
    rows: list[dict] = []
    epsilon = max(1e-4, (x_max - x_min) / 2000)
    for root in find_zeros(derivative_text, x_min, x_max):
        if root <= x_min + epsilon or root >= x_max - epsilon:
            continue
        value = safe_value(expr, root)
        left = safe_value(expr, root - epsilon)
        right = safe_value(expr, root + epsilon)
        if value is None or left is None or right is None:
            continue
        kind = '极小值' if value <= left and value <= right else ('极大值' if value >= left and value >= right else '驻点（非极值）')
        rows.append({'x': round(root, 6), 'y': round(value, 6), 'kind': kind})
    return rows


def sample_curve(expr: str, x_min: float = -6.0, x_max: float = 6.0, samples: int = 49,
                 y_limit: float = 25.0) -> dict:
    """把函数采样成前端可直接画的折线点，并给出视窗范围（超界点被裁掉并计数）。"""
    points: list[list[float]] = []
    all_values: list[float] = []
    clipped = 0
    for index in range(max(2, samples)):
        x = x_min + (x_max - x_min) * index / max(1, samples - 1)
        value = safe_value(expr, x)
        points.append([round(x, 6), None if value is None else round(value, 6)])
        if value is not None:
            if abs(value) > y_limit:
                clipped += 1
            else:
                all_values.append(value)
    y_min = min(all_values) if all_values else -1.0
    y_max = max(all_values) if all_values else 1.0
    if y_max - y_min < 1e-9:
        y_min -= 1.0
        y_max += 1.0
    return {
        'x_min': x_min,
        'x_max': x_max,
        'y_min': round(y_min, 6),
        'y_max': round(y_max, 6),
        'points': points,
        'clipped': clipped,
        'samples': len(points),
    }


def check_value(expr: str, x: float, expected: float, tolerance: float = 1e-6) -> dict:
    """核对某点函数值（例如学生算得的 f(1)=3 是否与表达式一致）。"""
    actual = safe_value(expr, x)
    if actual is None:
        return {'ok': False, 'reason': f'x={x} 处表达式无定义，无法核对', 'actual': None,
                'expected': expected, 'method': '数值代入核对'}
    scale = max(1.0, abs(actual), abs(expected))
    difference = abs(actual - expected) / scale
    return {
        'ok': difference <= tolerance,
        'actual': round(actual, 9),
        'expected': expected,
        'relative_diff': round(difference, 9),
        'tolerance': tolerance,
        'reason': None if difference <= tolerance else f'实际值 {round(actual, 6)} 与给定值 {expected} 不一致',
        'method': '数值代入核对（用表达式在该点的值比对）',
    }


def capabilities() -> dict:
    """供 /api/agent/status 展示的能力清单（不暴露任何密钥）。"""
    return {
        'expressions': '多项式、分式、幂、根式、sin/cos/tan、exp/ln/log、abs，变量以 x 为默认自变量',
        'features': ['evaluate', 'differentiate', 'equivalent', 'probe_limit', 'find_zeros', 'find_extrema', 'sample_curve'],
        'exact_derivative': True,
        'numeric_probe': True,
        'dependencies': 'none (built-in)',
        'limits_of_tool': '极限与等价性为数值证据，不是严格证明；多变量、积分、级数暂不支持。',
    }
