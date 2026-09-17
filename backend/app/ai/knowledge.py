"""B 模块课程知识库与检索。

MVP 阶段使用本地纯 Python BM25（中文按字 bigram 切分）实现“可离线、可解释”的引用检索，
后续可把 ``retrieve`` 换成向量检索（pgvector 或外部 embedding 服务）而不改动调用方接口。

内容状态：``verified=False`` 表示该知识点尚未经课程资料复核，界面与文档需要如实标注。
"""
from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

HAN = re.compile(r'[\u4e00-\u9fff]')
WORD = re.compile(r'[a-z0-9]+')

TOPIC_ALIASES = {
    '函数与极限': '极限与连续',
    '极限': '极限与连续',
    '极限与连续': '极限与连续',
    '导数': '导数与微分',
    '导数与微分': '导数与微分',
}

DEFAULT_TOP_K = 4
BM25_K1 = 1.5
BM25_B = 0.75
TOPIC_BOOST = 1.8


def tokenize(text: str) -> list[str]:
    """中文按字 bigram + 单字、英文数字按词切分，用于本地检索。

    例：``洛必达`` -> ``['洛必', '必达', '洛', '必', '达']``
    """
    lowered = (text or '').lower()
    tokens = WORD.findall(lowered)
    han = HAN.findall(lowered)
    tokens.extend(han[index] + han[index + 1] for index in range(len(han) - 1))
    tokens.extend(han)
    return tokens


@dataclass(frozen=True)
class KnowledgePoint:
    """一个可被引用、可被练习的课程知识点。"""

    id: str
    topic: str
    title: str
    summary: str
    key_points: tuple[str, ...]
    signals: tuple[str, ...] = ()
    common_mistakes: tuple[str, ...] = ()
    example: str = ''
    practice: str = ''
    source: str = ''
    verified: bool = False


@dataclass(frozen=True)
class Retrieved:
    """检索命中：知识点 + 分数 + 命中词，便于前端展示“为什么引用它”。"""

    point: KnowledgePoint
    score: float
    matched: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self, index: int) -> dict:
        return {
            'index': index,
            'id': self.point.id,
            'title': self.point.title,
            'topic': self.point.topic,
            'source': self.point.source,
            'verified': self.point.verified,
            'score': round(self.score, 3),
            'matched': list(self.matched),
        }


KNOWLEDGE_POINTS: tuple[KnowledgePoint, ...] = (
    KnowledgePoint(
        id='limit-definition',
        topic='极限与连续',
        title='函数极限的定义（ε-δ 语言）',
        summary='lim_{x→x0} f(x)=A 指：任意 ε>0，总存在 δ>0，使 0<|x-x0|<δ 时 |f(x)-A|<ε。极限刻画的是“趋近过程”，与 f(x0) 是否有定义无关。',
        key_points=(
            '双侧极限存在的充要条件是左极限与右极限都存在且相等',
            '极限存在不要求在 x0 处有定义，也不要求等于函数值',
            'ε-δ 是“任意小—存在小”的量化顺序，不能颠倒',
        ),
        signals=('极限的定义', 'ε-δ', 'epsilon', '左极限', '右极限', 'x趋于', '趋近'),
        common_mistakes=(
            '把 f(x0) 的函数值当成极限值',
            '只验证一侧极限就断言双侧极限存在',
            '把“趋于”当成“等于”直接代入',
        ),
        example=r'求 $\lim_{x\to 1}\frac{x^{2}-1}{x-1}$：约分后得 $\lim_{x\to 1}(x+1)=2$，注意 x=1 处原式无定义。',
        practice=r'求 $\lim_{x\to 2}\frac{x^{2}-4}{x-2}$；并判断 $\lim_{x\to 0}\frac{|x|}{x}$ 是否存在。',
        source='同济版《高等数学》上册 第一章 §3 函数极限（待课程资料复核）',
    ),
    KnowledgePoint(
        id='limit-techniques',
        topic='极限与连续',
        title='极限的四则运算与常见计算方法',
        summary='先尝试直接代入；遇到 0/0 或 ∞/∞ 等不定式，再考虑约分、通分、有理化、等价无穷小替换、洛必达法则或泰勒展开。',
        key_points=(
            '洛必达法则要求分子分母都可导，且导数之比的极限存在',
            '等价无穷小替换通常只在乘除结构中可直接使用',
            '0/0 与 ∞/∞ 是不定式，但 0/∞、∞+∞ 等不是',
            '有理化常用于含根号的差式，如 √(1+x)-1',
        ),
        signals=('洛必达', '不定式', '0/0', '无穷比无穷', '等价无穷小', '有理化', '泰勒', '通分', '约分'),
        common_mistakes=(
            '对非不定式直接使用洛必达法则',
            '在加减结构中随意做等价无穷小替换',
            '忽略洛必达法则的适用条件导致循环或错误',
        ),
        example=r'$\lim_{x\to 0}\frac{1-\cos x}{x^{2}}=\frac{1}{2}$，可用等价无穷小 $1-\cos x\sim\frac{x^{2}}{2}$ 快速得到。',
        practice=r'求 $\lim_{x\to 0}\frac{e^{x}-1-x}{x^{2}}$；求 $\lim_{x\to\infty}\frac{3x^{2}+1}{2x^{2}-5}$。',
        source='同济版《高等数学》上册 第一章 §5 极限运算法则（待课程资料复核）',
    ),
    KnowledgePoint(
        id='important-limits',
        topic='极限与连续',
        title='两个重要极限与 sin x / x',
        summary='lim_{x→0} sin x / x = 1（x 必须用弧度）与 lim_{x→∞}(1+1/x)^x = e 是解决三角函数与指幂型极限的基础工具。',
        key_points=(
            '第一个重要极限要求自变量趋于 0 且为弧度制',
            '第二个重要极限可变形为 lim_{u→0}(1+u)^{1/u}=e',
            '1^∞ 型极限常用取对数或凑 e 的形式处理',
        ),
        signals=('重要极限', 'sinx/x', 'sin x', '第二个重要极限', '1的无穷', '自然常数e'),
        common_mistakes=(
            '用角度制代入 sin x / x 得出错误结果',
            '把 x→∞ 时的 sin x / x 也写成 1',
            '对 1^∞ 型极限直接按普通幂运算处理',
        ),
        example=r'$\lim_{x\to 0}\frac{\sin 3x}{x}=3$，利用 $\sin 3x\sim 3x$。',
        practice=r'求 $\lim_{x\to 0}\frac{\tan x}{x}$；求 $\lim_{x\to 0}\frac{\sin 2x}{\sin 5x}$。',
        source='同济版《高等数学》上册 第一章 §4 两个重要极限（待课程资料复核）',
    ),
    KnowledgePoint(
        id='continuity',
        topic='极限与连续',
        title='连续性与间断点分类',
        summary='f 在 x0 连续需同时满足：x0 处有定义、极限存在、极限值等于函数值。间断点按左右极限情况分为可去、跳跃、无穷与振荡四类。',
        key_points=(
            '连续三个条件缺一不可，其中“有定义”最易被忽略',
            '可去间断点左右极限存在且相等，但不等于函数值',
            '闭区间上连续函数具有最值性、介值性与零点存在性',
        ),
        signals=('连续', '间断点', '可去间断点', '跳跃间断点', '零点存在', '介值定理'),
        common_mistakes=(
            '认为极限存在就是连续',
            '忘记检查函数在 x0 处是否有定义',
            '把跳跃间断点误判为可去间断点',
        ),
        example=r'$f(x)=\frac{\sin x}{x}$ 在 x=0 无定义，属于可去间断点，补充定义 f(0)=1 后即连续。',
        practice=r'讨论 $f(x)=\frac{x^{2}-1}{x-1}$ 在 x=1 处的连续性；判断 $\frac{1}{x}$ 在 x=0 的间断类型。',
        source='同济版《高等数学》上册 第一章 §8 连续性与间断点（待课程资料复核）',
    ),
    KnowledgePoint(
        id='derivative-definition',
        topic='导数与微分',
        title='导数的定义与可导性',
        summary="f'(x0)=lim_{Δx→0}[f(x0+Δx)-f(x0)]/Δx，即差商的极限；几何意义是曲线在该点切线的斜率。可导必连续，连续不一定可导。",
        key_points=(
            "导数刻画的是函数的局部变化率，与 f(x0) 的具体值无关",
            '可导 ⇒ 连续；连续 ⇏ 可导（如 y=|x| 在 x=0）',
            '分段函数在分界点处要用左右导数判断可导性',
        ),
        signals=('导数的定义', '差商', '可导', '切线斜率', '左右导数', '可导必连续'),
        common_mistakes=(
            "把 f'(x0) 与 f(x0) 混为一谈",
            '在约分前就令 Δx=0，出现 0/0',
            '认为连续一定可导',
        ),
        example=r"用定义求 $f(x)=x^{2}$ 在 x0 处的导数：$\lim_{\Delta x\to 0}\frac{(x_0+\Delta x)^2-x_0^2}{\Delta x}=2x_0$。",
        practice=r"用定义求 $f(x)=x^{3}$ 的导数；判断 $y=|x|$ 在 x=0 处是否可导。",
        source='同济版《高等数学》上册 第二章 §1 导数概念（待课程资料复核）',
    ),
    KnowledgePoint(
        id='derivative-rules',
        topic='导数与微分',
        title='求导法则：四则运算、复合函数与高阶导数',
        summary="(uv)'=u'v+uv'，(u/v)'=(u'v-uv')/v²；复合函数用链式法则 (f∘g)'(x)=f'(g(x))g'(x)；高阶导数记为 f''、f^(n)。",
        key_points=(
            '链式法则要逐层求导，容易漏掉内层导数',
            '商法则分子顺序为“分子导乘分母减分子乘分母导”',
            '隐函数求导对等式两边同时求导后再解出 y′',
        ),
        signals=('链式法则', '复合函数求导', '乘积法则', '商法则', '高阶导数', '隐函数求导'),
        common_mistakes=(
            '复合函数求导漏乘内层导数',
            '商法则中分子顺序写反导致符号错误',
            '对隐函数求导时漏掉 y 是 x 的函数这一步',
        ),
        example=r'求 $y=\sin(2x+1)$ 的导数：$y^{\prime}=\cos(2x+1)\cdot 2$。',
        practice=r'求 $y=(x^{2}+1)^{5}$ 与 $y=x\ln x$ 的导数。',
        source='同济版《高等数学》上册 第二章 §2 函数的求导法则（待课程资料复核）',
    ),
    KnowledgePoint(
        id='derivative-application',
        topic='导数与微分',
        title='微分与导数应用：单调性、极值与凹凸',
        summary="微分 dy=f'(x)dx 是函数增量的线性主部。f′>0 时函数单调递增；f′(x0)=0 只是极值的必要条件；f″ 的符号决定凹凸性。",
        key_points=(
            "f'(x0)=0 的点是驻点，未必是极值点",
            '判断极值需要看 f′ 的符号变化或使用二阶导判别',
            '求最值时必须比较区间端点值',
            '凹凸性与拐点由 f″ 的符号变化决定',
        ),
        signals=('微分', '单调性', '极值', '驻点', '凹凸性', '拐点', 'dy', '最值'),
        common_mistakes=(
            "把 f'(x0)=0 直接当作极值点",
            '求闭区间最值时漏掉端点值',
            '忽略函数定义域对单调区间的影响',
        ),
        example=r'$f(x)=x^{3}$ 在 x=0 有 f′(0)=0，但该点不是极值点，说明驻点不一定是极值点。',
        practice=r'求 $f(x)=x^{3}-3x$ 的单调区间与极值；求其在 [-2,2] 上的最值。',
        source='同济版《高等数学》上册 第二章 §4—§5 微分与函数性态（待课程资料复核）',
    ),
)

POINT_INDEX = {point.id: point for point in KNOWLEDGE_POINTS}


def _doc_text(point: KnowledgePoint) -> str:
    return ' '.join(
        [
            point.title,
            point.summary,
            *point.key_points,
            *point.signals,
            *point.common_mistakes,
            point.example,
            point.practice,
        ]
    )


class _BM25Index:
    """极简 BM25 索引，语料是固定知识点集合，构建一次即可。"""

    def __init__(self, points: tuple[KnowledgePoint, ...]) -> None:
        self.points = points
        self.docs = [Counter(tokenize(_doc_text(point))) for point in points]
        self.lengths = [float(sum(doc.values())) or 1.0 for doc in self.docs]
        self.avg_length = sum(self.lengths) / len(self.lengths) if self.lengths else 1.0
        self.df: Counter = Counter()
        for doc in self.docs:
            self.df.update(doc.keys())
        self.total = len(points)

    def idf(self, term: str) -> float:
        df = self.df.get(term, 0)
        return math.log(1.0 + (self.total - df + 0.5) / (df + 0.5))

    def score(self, tokens: list[str], position: int) -> float:
        doc = self.docs[position]
        length = self.lengths[position]
        total = 0.0
        for term in tokens:
            freq = doc.get(term, 0)
            if not freq:
                continue
            denominator = freq + BM25_K1 * (1 - BM25_B + BM25_B * length / self.avg_length)
            total += self.idf(term) * freq * (BM25_K1 + 1) / denominator
        return total


_INDEX = _BM25Index(KNOWLEDGE_POINTS)


def normalize_topic(topic: str | None) -> str | None:
    if not topic:
        return None
    text = topic.strip()
    return TOPIC_ALIASES.get(text, text)


def retrieve(
    query: str,
    topic: str | None = None,
    top_k: int = DEFAULT_TOP_K,
    min_score: float = 0.0,
) -> list[Retrieved]:
    """检索课程资料片段；返回按分数降序的结果，query 为空时返回空列表。"""
    if not (query or '').strip():
        return []
    tokens = tokenize(query)
    if not tokens:
        return []
    wanted_topic = normalize_topic(topic)
    results: list[Retrieved] = []
    for position, point in enumerate(_INDEX.points):
        score = _INDEX.score(tokens, position)
        if score <= 0:
            continue
        if wanted_topic and point.topic == wanted_topic:
            score *= TOPIC_BOOST
        if score < min_score:
            continue
        doc_terms = _INDEX.docs[position]
        candidates = [term for term in dict.fromkeys(tokens) if term in doc_terms and len(term) > 1]
        if not candidates:
            candidates = [term for term in dict.fromkeys(tokens) if term in doc_terms]
        candidates.sort(key=lambda term: (-_INDEX.idf(term), -doc_terms[term], term))
        matched = tuple(candidates[:6])
        results.append(Retrieved(point=point, score=score, matched=matched))
    results.sort(key=lambda item: item.score, reverse=True)
    return results[: max(0, top_k)]


def get_point(point_id: str) -> KnowledgePoint | None:
    return POINT_INDEX.get(point_id)


def suggest_topic(text: str) -> str | None:
    """按检索得分推断最可能的课程模块，供拍照识别后的“确认”环节提示。"""
    hits = retrieve(text, top_k=3)
    if not hits:
        return None
    totals: dict[str, float] = {}
    for hit in hits:
        totals[hit.point.topic] = totals.get(hit.point.topic, 0.0) + hit.score
    return max(totals.items(), key=lambda item: item[1])[0]


def practice_for(point_ids, limit: int = 3) -> list[dict]:
    """按薄弱知识点给出变式练习，附带资料出处。"""
    items: list[dict] = []
    for point_id in point_ids:
        point = get_point(point_id)
        if point is None or not point.practice:
            continue
        items.append(
            {
                'point_id': point.id,
                'topic': point.topic,
                'title': f'{point.title} · 变式练习',
                'prompt': point.practice,
                'source': point.source,
                'verified': point.verified,
            }
        )
        if len(items) >= limit:
            break
    return items


def stats() -> dict:
    topics = sorted({point.topic for point in KNOWLEDGE_POINTS})
    return {
        'engine': 'local-bm25-bigram',
        'points': len(KNOWLEDGE_POINTS),
        'topics': topics,
        'verified_points': sum(1 for point in KNOWLEDGE_POINTS if point.verified),
        'pending_review': sum(1 for point in KNOWLEDGE_POINTS if not point.verified),
        'note': '知识点待课程资料复核；复核后把 verified 置为 True。',
    }
