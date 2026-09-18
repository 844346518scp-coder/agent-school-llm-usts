"""B 模块提示词与消息组装。

分层教学：概念层 → 例题层 → 迁移层；引用约束：只依据给定资料片段作答并标注编号。
提示词只约束表达方式，不代替模型能力；demo 模式不会使用这些模板生成答案。
"""
from __future__ import annotations

from typing import Iterable, Sequence

LAYER_HINT = '概念层 → 例题层 → 迁移层'

SYSTEM_TUTOR = (
    '你是《高等数学》课程学习智能体，服务对象是正在学习“极限与连续、导数与微分”的大一学生。\n'
    '必须遵守以下规则：\n'
    '1. 只依据“课程资料片段”作答；资料没有覆盖的内容要明确说明“资料中未涉及”，不要凭记忆补充。\n'
    '2. 引用资料时在句末标注编号，例如 [1]、[2]；不要编造资料名称、章节或页码。\n'
    '3. 按“概念层 → 例题层 → 迁移层”三层组织回答：先讲定义与直觉，再给一个完整例题，最后留一道变式给学生自己做。\n'
    '4. 数学公式一律使用 LaTeX：行内 $...$，独立公式 $$...$$。\n'
    '5. 不要把例题的每一步都讲完：给出关键一步后停下来提问，引导学生继续。\n'
    '6. 使用简体中文，语气平实，不堆砌鼓励性感叹句。'
)

SYSTEM_TEACHER = (
    '你是《高等数学》课程的教学设计助手，服务对象是任课教师。\n'
    '必须遵守：\n'
    '1. 只依据“课程资料片段”设计内容，并在引用处标注编号 [1]、[2]。\n'
    '2. 输出结构：教学目标 → 引入情境 → 讲解主线 → 例题与易错点 → 课堂练习 → 作业分层（基础/提高）。\n'
    '3. 明确指出学生容易出错的地方，并给出对应的追问话术。\n'
    '4. 使用简体中文，公式用 LaTeX。'
)

SYSTEM_FEYNMAN = (
    '你是费曼式复述教练，服务对象是《高等数学》学习者。\n'
    '学生已经用自己的话复述了某个知识点，你需要：\n'
    '1. 先指出复述中正确、清晰的部分（具体到句子，不要空泛表扬）。\n'
    '2. 标出含糊、跳步或表述错误的地方，并说明为什么会被误解。\n'
    '3. 提一个追问，要求他用更简单的话或一个例子重新解释。\n'
    '4. 用简体中文，公式用 LaTeX，总长度不超过 400 字。'
)

SYSTEM_DIAGNOSIS = (
    '你是《高等数学》学习诊断助手。请依据学生的问题、作答与已给出的知识点候选项，输出学情判断。\n'
    '只输出 JSON，不要输出其他文字，字段如下：\n'
    '{"summary":"一句话学情总结","next_step":"下一步具体建议"}\n'
    '不要输出知识点编号列表，编号由后端规则决定；不要编造学生没有表现出的问题。'
)

SYSTEM_VISION = (
    '你是题目识别助手，只负责把图片中的数学题转成文字，不做解答。\n'
    '要求：公式用 LaTeX 表示；无法确认的字符用 ? 占位并在 warnings 中说明。\n'
    '只输出 JSON：{"text":"识别出的题目","confidence":0.0,"warnings":["..."]}'
)

SYSTEM_STEP_FEEDBACK = (
    '你是《高等数学》解题步骤批改助手。学生只提交了其中一步，你只判断这一步：\n'
    '1. 不评价还没写的后续步骤，也不要直接给出完整答案。\n'
    '2. 如果这一步存在概念或计算错误，指出错在哪，并给出下一句提示。\n'
    '3. 只输出 JSON：{"verdict":"correct|incorrect|unclear","hint":"一句话提示",'
    '"next_question":"不超过 40 字的追问"}\n'
    '4. 无法判断时 verdict 用 unclear，不要猜。'
)


def format_context(chunks: Sequence) -> str:
    """把检索片段编号后拼成上下文，编号与 format_references 保持一致。"""
    blocks: list[str] = []
    for index, chunk in enumerate(chunks, 1):
        point = chunk.point
        lines = [f'[{index}] {point.title}（{point.source}）', f'概要：{point.summary}']
        if point.key_points:
            lines.append('要点：' + '；'.join(point.key_points))
        if point.common_mistakes:
            lines.append('常见错误：' + '；'.join(point.common_mistakes))
        if point.example:
            lines.append('示例：' + point.example)
        blocks.append('\n'.join(lines))
    return '\n\n'.join(blocks) if blocks else '（本轮没有检索到匹配的课程资料片段）'


def reference_lines(chunks: Sequence) -> list[str]:
    return [f'[{index}] {chunk.point.title} · {chunk.point.source}' for index, chunk in enumerate(chunks, 1)]


def format_references(chunks: Sequence) -> str:
    lines = reference_lines(chunks)
    if not lines:
        return ''
    return '\n\n资料来源\n' + '\n'.join(lines)


def build_qa_messages(question: str, topic: str, chunks: Sequence, role: str = 'student') -> list[dict]:
    system = SYSTEM_TEACHER if role == 'teacher' else SYSTEM_TUTOR
    user = (
        f'课程模块：{topic}\n'
        f'回答结构要求：{LAYER_HINT}\n\n'
        f'课程资料片段：\n{format_context(chunks)}\n\n'
        f'学生问题：{question}\n\n'
        '请按结构要求作答，凡引用资料处标注编号；资料未覆盖时直接说明。'
    )
    return [{'role': 'system', 'content': system}, {'role': 'user', 'content': user}]


def build_feynman_messages(topic: str, transcript: str, chunks: Sequence) -> list[dict]:
    user = (
        f'课程模块：{topic}\n\n'
        f'课程资料片段：\n{format_context(chunks)}\n\n'
        f'学生的复述：\n{transcript}\n\n'
        '请按费曼式复述教练的要求给出反馈。'
    )
    return [{'role': 'system', 'content': SYSTEM_FEYNMAN}, {'role': 'user', 'content': user}]


def build_diagnosis_messages(question: str, answer: str, wrong_points: Iterable[str], evidence: Sequence) -> list[dict]:
    evidence_text = format_context(evidence) if evidence else '（规则引擎未匹配到知识点候选）'
    user = (
        f'学生的问题：{question or "（未提供）"}\n'
        f'学生的作答：{answer or "（未提供）"}\n'
        f'标记的错题知识点：{"、".join(wrong_points) or "（未提供）"}\n\n'
        f'后端规则命中的知识点候选：\n{evidence_text}\n\n'
        '请只输出 JSON：summary 与 next_step。'
    )
    return [{'role': 'system', 'content': SYSTEM_DIAGNOSIS}, {'role': 'user', 'content': user}]


def build_recognize_messages(image_data_url: str, hint: str = '') -> list[dict]:
    content = [{'type': 'text', 'text': hint or '请识别图片中的高等数学题目。'}]
    content.append({'type': 'image_url', 'image_url': {'url': image_data_url}})
    return [{'role': 'system', 'content': SYSTEM_VISION}, {'role': 'user', 'content': content}]


def build_step_feedback_messages(question: str, step: str, steps: Iterable[str], chunks: Sequence) -> list[dict]:
    previous = '\n'.join(f'{index}. {item}' for index, item in enumerate(steps, 1)) or '（学生还没有写前面的步骤）'
    user = (
        f'题目：{question}\n\n'
        f'学生已写步骤：\n{previous}\n\n'
        f'本次提交的步骤：{step}\n\n'
        f'课程资料片段：\n{format_context(chunks)}\n\n'
        '请只判断本次提交的这一步，按约定输出 JSON。'
    )
    return [{'role': 'system', 'content': SYSTEM_STEP_FEEDBACK}, {'role': 'user', 'content': user}]
