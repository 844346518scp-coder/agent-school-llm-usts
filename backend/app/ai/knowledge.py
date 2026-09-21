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
    lowered = (text or '').lower().replace('∫', ' 积分 ')
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
    KnowledgePoint(
        id='integral-antiderivative',
        topic='一元函数积分学',
        title='原函数与不定积分',
        summary='若 F′(x)=f(x)，则 F 是 f 的原函数，f 的全体原函数记为 ∫f(x)dx=F(x)+C；求导与积分互为逆运算，结果必须带任意常数 C。',
        key_points=(
            '原函数不唯一，彼此相差一个常数',
            '不定积分结果必须写 +C',
            '基本积分表由基本导数公式反推得到',
        ),
        signals=('原函数', '不定积分', '积分表', '逆运算', '积分常数'),
        common_mistakes=('忘记写积分常数 C', '把积分当作求导的简单逆运算而漏掉系数'),
        example=r'$\int 2x\,dx=x^{2}+C$；因为 $(x^{2}+C)^{\prime}=2x$。',
        practice=r'求 $\int(3x^{2}-2x+1)\,dx$。',
        source='同济版《高等数学》上册 第五章 §1 不定积分概念（待课程资料复核）',
    ),
    KnowledgePoint(
        id='integral-definite',
        topic='一元函数积分学',
        title='定积分的定义与几何意义',
        summary=r'定积分 $\int_{a}^{b}f(x)\,dx$ 是黎曼和的极限，几何上等于曲线与 x 轴围成的代数面积；它是确定的数，与积分变量记号无关。',
        key_points=(
            '定积分是极限，结果是一个数，不含 +C',
            '几何意义是代数面积，x 轴下方部分取负',
            '交换上下限，定积分变号',
        ),
        signals=('定积分', '黎曼和', '积分上限', '积分下限', '代数面积', '区间划分'),
        common_mistakes=('把定积分结果写成含 C 的表达式', '忽略 x 轴下方面积为负'),
        example=r'$\int_{0}^{1}x^{2}\,dx=\frac{1}{3}$，可由 $\frac{1}{3}x^{3}$ 在端点取值相减得到。',
        practice=r'计算 $\int_{0}^{1}(x^{2}+1)\,dx$；并说明 $\int_{1}^{0}x\,dx$ 与 $\int_{0}^{1}x\,dx$ 的关系。',
        source='同济版《高等数学》上册 第五章 §1 定积分概念（待课程资料复核）',
    ),
    KnowledgePoint(
        id='integral-ftc',
        topic='一元函数积分学',
        title='微积分基本定理与牛顿-莱布尼茨公式',
        summary='若 f 在 [a,b] 上连续，则 Φ(x)=∫_a^x f(t)dt 可导且 Φ′(x)=f(x)；由此得到 ∫_a^b f(x)dx=F(b)−F(a)，即牛顿-莱布尼茨公式。',
        key_points=(
            '变上限积分是被积函数的一个原函数',
            '公式要求 f 在积分区间上连续、F 是 f 的原函数',
            '代入顺序是上限减下限',
        ),
        signals=('牛顿', '莱布尼茨', '变上限', '微积分基本定理', '原函数求值'),
        common_mistakes=('被积函数在区间内有瑕点仍直接套用公式', '上下限代入顺序写反'),
        example=r'$\int_{1}^{2}\frac{1}{x}\,dx=\ln x\Big|_{1}^{2}=\ln 2$。',
        practice=r'计算 $\int_{0}^{\pi/2}\cos x\,dx$；并说明公式成立需要的条件。',
        source='同济版《高等数学》上册 第五章 §2 微积分基本定理（待课程资料复核）',
    ),
    KnowledgePoint(
        id='integral-techniques',
        topic='一元函数积分学',
        title='积分方法：换元法与分部积分法',
        summary=r'第一类换元（凑微分）与第二类换元（三角代换、根式代换）用于化归基本积分表；分部积分 $\int u\,dv=uv-\int v\,du$ 用于乘积形式以及对数、反三角函数。',
        key_points=(
            '换元后必须同时把 dx 与积分限一起换掉',
            '定积分换元改用新变量的积分限，且不必回代',
            '分部积分选取 u 的方向可记为“反对幂指三”',
        ),
        signals=('换元积分', '分部积分', '凑微分', '三角代换', '变量替换'),
        common_mistakes=('换元后忘记换积分限', '分部积分中 u、dv 选择不当导致越算越复杂'),
        example=r'$\int x e^{x}\,dx=x e^{x}-e^{x}+C$，取 u=x、dv=e^{x}dx。',
        practice=r'求 $\int 2x\cos(x^{2})\,dx$ 与 $\int \ln x\,dx$。',
        source='同济版《高等数学》上册 第五章 §3—§4 换元与分部积分（待课程资料复核）',
    ),
    KnowledgePoint(
        id='series-convergence',
        topic='无穷级数',
        title='常数项级数的收敛与判别',
        summary='级数收敛指部分和数列有极限；若级数收敛则通项趋于 0，但通项趋于 0 不能保证收敛（如调和级数）。正项级数常用比较判别法、比值判别法与 p 级数结论。',
        key_points=(
            '收敛的必要条件是通项趋于 0，不是充分条件',
            'p 级数当 p>1 时收敛，p≤1 时发散',
            '比较判别法要找到可比的正项级数',
            '比值判别法适用于含阶乘或幂的结构',
        ),
        signals=('级数', '收敛', '发散', '判别法', '部分和', 'p级数', '调和级数'),
        common_mistakes=('用“通项趋于 0”直接断言级数收敛', '忽略正项级数判别法的适用前提'),
        example=r'$\sum_{n=1}^{\infty}\frac{1}{n^{2}}$ 收敛（p=2>1）；$\sum_{n=1}^{\infty}\frac{1}{n}$ 发散。',
        practice=r'判断 $\sum_{n=1}^{\infty}\frac{1}{\sqrt{n}}$ 是否收敛，并说明依据。',
        source='同济版《高等数学》下册 第十二章 §1 常数项级数（待课程资料复核）',
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


TOPIC_SUGGESTION_MIN_SCORE = 1.5
TOPIC_SUGGESTION_DOMINANCE = 0.5


def suggest_topic(text: str, min_score: float = TOPIC_SUGGESTION_MIN_SCORE) -> str | None:
    """按检索得分推断最可能的课程模块，供拍照识别后的“确认”环节提示。"""
    hits = retrieve(text, top_k=3, min_score=min_score)
    if not hits:
        return None
    top = hits[0]
    informative = [term for term in top.matched if len(term) > 1]
    title_terms = [term for term in informative if term in tokenize(top.point.title)]
    if len(informative) < 2 and not title_terms:
        # 只命中单字或仅一个泛词时不下结论，避免把“微分方程”猜成“导数与微分”。
        return None
    totals: dict[str, float] = {}
    for hit in hits:
        totals[hit.point.topic] = totals.get(hit.point.topic, 0.0) + hit.score
    overall = sum(totals.values())
    if overall <= 0:
        return None
    best_topic, best_score = max(totals.items(), key=lambda item: item[1])
    if best_score / overall < TOPIC_SUGGESTION_DOMINANCE:
        return None
    return best_topic


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
        'resources': len(RESOURCES),
        'topics': topics,
        'verified_points': sum(1 for point in KNOWLEDGE_POINTS if point.verified),
        'pending_review': sum(1 for point in KNOWLEDGE_POINTS if not point.verified),
        'note': '知识点与资源条目待课程资料复核；复核后把 verified 置为 True。',
    }


@dataclass(frozen=True)
class Resource:
    """可检索的学习资源条目（当前由知识点派生，外部课件与视频待补充）。"""

    id: str
    kind: str
    topic: str
    title: str
    summary: str
    point_id: str | None
    source: str
    verified: bool = False

    def as_dict(self, score: float | None = None) -> dict:
        data = {
            'id': self.id,
            'kind': self.kind,
            'topic': self.topic,
            'title': self.title,
            'summary': self.summary,
            'point_id': self.point_id,
            'source': self.source,
            'verified': self.verified,
        }
        if score is not None:
            data['score'] = round(score, 3)
        return data


def _build_resources() -> tuple[Resource, ...]:
    items: list[Resource] = []
    for point in KNOWLEDGE_POINTS:
        items.append(
            Resource(id=f'{point.id}-concept', kind='概念讲解', topic=point.topic,
                     title=f'{point.title} · 概念梳理', summary=point.summary,
                     point_id=point.id, source=point.source, verified=point.verified)
        )
        if point.example:
            items.append(
                Resource(id=f'{point.id}-example', kind='例题', topic=point.topic,
                         title=f'{point.title} · 例题精讲', summary=point.example,
                         point_id=point.id, source=point.source, verified=point.verified)
            )
        if point.practice:
            items.append(
                Resource(id=f'{point.id}-practice', kind='练习', topic=point.topic,
                         title=f'{point.title} · 变式练习', summary=point.practice,
                         point_id=point.id, source=point.source, verified=point.verified)
            )
    for extra in RESOURCE_EXTRAS:
        items.append(extra)
    return tuple(items)


RESOURCE_EXTRAS: tuple[Resource, ...] = (
    Resource(id='handbook-formulas', kind='资料', topic='跨模块',
             title='高数常用公式速查（极限、导数、积分）',
             summary='汇总两个重要极限、基本求导公式、基本积分表与牛顿-莱布尼茨公式，用于做题时快速对照。',
             point_id=None, source='待课程资料复核后补充正式版本'),
    Resource(id='handbook-mistakes', kind='资料', topic='跨模块',
             title='高频易错清单',
             summary='包含忽略积分常数 C、链式法则漏乘内层导数、在非不定式上使用洛必达法则、把驻点当作极值点等常见错误。',
             point_id=None, source='待课程资料复核后补充正式版本'),
    Resource(id='handbook-arc-length-example', kind='资料', topic='跨模块',
             title='定积分应用示例：平面图形面积',
             summary='用定积分求曲线围成图形面积的步骤：求交点定上下限、判断上下曲线、写出面积表达式再计算。',
             point_id='integral-definite', source='待课程资料复核后补充正式版本'),
)


RESOURCES: tuple[Resource, ...] = _build_resources()


class _ResourceIndex:
    """资源条目索引；与知识点索引用同一套 BM25 参数，单独维护以便日后换向量检索。"""

    def __init__(self, resources: tuple[Resource, ...]) -> None:
        self.resources = resources
        texts = [f'{item.title} {item.summary} {item.kind} {item.topic}' for item in resources]
        self.docs = [Counter(tokenize(text)) for text in texts]
        self.lengths = [float(sum(doc.values())) or 1.0 for doc in self.docs]
        self.avg_length = sum(self.lengths) / len(self.lengths) if self.lengths else 1.0
        self.df: Counter = Counter()
        for doc in self.docs:
            self.df.update(doc.keys())
        self.total = len(resources)

    def score(self, tokens: list[str], position: int) -> float:
        doc = self.docs[position]
        length = self.lengths[position]
        total = 0.0
        for term in tokens:
            freq = doc.get(term, 0)
            if not freq:
                continue
            df = self.df.get(term, 0)
            idf = math.log(1.0 + (self.total - df + 0.5) / (df + 0.5))
            denominator = freq + BM25_K1 * (1 - BM25_B + BM25_B * length / self.avg_length)
            total += idf * freq * (BM25_K1 + 1) / denominator
        return total


_RESOURCE_INDEX = _ResourceIndex(RESOURCES)


def search_resources(
    query: str,
    topic: str | None = None,
    limit: int = 5,
    min_score: float = 0.0,
) -> list[dict]:
    """资源检索：返回可引用的概念/例题/练习/资料条目，按相关度降序。"""
    if not (query or '').strip():
        return []
    tokens = tokenize(query)
    if not tokens:
        return []
    wanted_topic = normalize_topic(topic)
    scored: list[tuple[float, Resource]] = []
    for position, resource in enumerate(_RESOURCE_INDEX.resources):
        score = _RESOURCE_INDEX.score(tokens, position)
        if score <= 0:
            continue
        if wanted_topic and resource.topic == wanted_topic:
            score *= TOPIC_BOOST
        if score < min_score:
            continue
        scored.append((score, resource))
    scored.sort(key=lambda item: (-item[0], item[1].id))
    return [resource.as_dict(score) for score, resource in scored[: max(0, limit)]]
