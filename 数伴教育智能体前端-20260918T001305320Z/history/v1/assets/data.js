/* SECTION: data-source
   数伴演示数据。账号、页面文案、课程条目、示例问题与预设讲解回复
   均取自项目现有前端页面（frontend/src）与后端演示逻辑（backend/app/ai/service.py）。
   所有回复为固定示例，不代表真实模型能力。 */
(function () {
  'use strict';

  /* SECTION: users */
  var USERS = [
    { id: 'u-student', username: 'student', password: 'Student123!', name: '林同学', role: 'student', avatar: '林' },
    { id: 'u-teacher', username: 'teacher', password: 'Teacher123!', name: '陈老师', role: 'teacher', avatar: '陈' }
  ];

  /* SECTION: navigation */
  var NAV_STUDENT = [
    { id: 'dashboard', label: '学习概览', icon: '▦' },
    { id: 'agent', label: '数伴智能体', icon: '✦', ai: true },
    { id: 'courses', label: '课程探索', icon: '📖' },
    { id: 'assignments', label: '我的作业', icon: '📋', dot: true },
    { id: 'favorites', label: '复习收藏', icon: '🔖' },
    { id: 'records', label: '学习记录', icon: '🕘' }
  ];
  var NAV_TEACHER = [
    { id: 'dashboard', label: '教学概览', icon: '▦' },
    { id: 'agent', label: '教学助手', icon: '✦', ai: true },
    { id: 'assignments', label: '作业管理', icon: '📋' },
    { id: 'students', label: '我的班级', icon: '👥' },
    { id: 'records', label: '对话记录', icon: '🕘' }
  ];

  /* SECTION: courses */
  var LESSONS = [
    {
      chapter: '函数与极限', number: '01', title: '无限接近，意味着什么？',
      text: '从直觉出发，建立函数极限的初步认识。', formula: 'lim f(x)',
      prompt: '如何理解函数极限？', label: '概念探索'
    },
    {
      chapter: '函数与极限', number: '02', title: '一个重要的极限',
      text: '从 sin(x)/x 入手，学习夹逼思想。', formula: 'sin x / x',
      prompt: '如何理解 sin(x)/x 在 x→0 时的极限？', label: '预设例题'
    },
    {
      chapter: '导数与微分', number: '03', title: '让变化，有一个刻度',
      text: '从割线到切线，用定义理解导数。', formula: 'f′(x)',
      prompt: '用定义求 x² 的导数', label: '预设例题'
    },
    {
      chapter: '导数与微分', number: '04', title: '讲给另一个人听',
      text: '尝试解释导数，用讲解梳理你的理解。', formula: 'Δy / Δx',
      prompt: '我想用费曼学习法解释导数', label: '费曼练习'
    }
  ];

  /* SECTION: prompts */
  var PROMPTS_STUDENT = [
    { icon: 'Σ', text: '如何理解 sin(x)/x 在 x→0 时的极限？' },
    { icon: '💡', text: '用定义求 x² 的导数' },
    { icon: '📖', text: '我想用费曼学习法解释导数' }
  ];
  var PROMPTS_TEACHER = [
    { icon: 'Σ', text: '帮我设计一节导数概念微课' },
    { icon: '💡', text: '如何用例题解释瞬时变化率？' },
    { icon: '📖', text: '设计一道课后反思问题' }
  ];

  /* SECTION: demo-replies
     与 backend/app/ai/service.py 的 demo_reply 分支一一对应。 */
  var REPLY_TEACHER =
    '【教学设计示例 · 未连接真实模型】\n\n' +
    '可以先围绕“概念 → 例题 → 迁移”组织一节微课：\n' +
    '1. 用曲线在一点的切线，引入瞬时变化率。\n' +
    '2. 让学生解释割线斜率为什么要取极限。\n' +
    '3. 以 $f(x)=x^2$ 为例，用定义推导 $f\'(x)=2x$。\n' +
    '4. 用一道变式题收集反馈，再决定是否补讲。\n\n' +
    '这是固定教学示例，并未对你的具体要求进行模型分析。你可以前往“作业管理”发布自己的练习。';

  var REPLY_FEYNMAN =
    '【费曼练习示例 · 未评分】\n\n' +
    '试着把“导数”讲给第一次接触它的同学：\n' +
    '① 它描述什么？\n② 割线与切线有什么关系？\n③ 生活中有哪些瞬时变化的例子？\n\n' +
    '参考表达：导数描述函数在某一点的瞬时变化率，也对应曲线在该点的切线斜率。\n' +
    '目前只展示固定追问，还不能评价你的讲解质量。';

  var REPLY_SIN_LIMIT =
    '【固定例题演示】\n\n' +
    '你可以先看这个经典极限：\n' +
    '$$\\lim_{x\\to 0}\\frac{\\sin x}{x}=1$$\n' +
    '这里 $x$ 使用弧度制。\n\n' +
    '1. 直接代入会得到 $0/0$，它是不定式，不是答案。\n' +
    '2. 当 $0<x<\\pi/2$ 时，有 $\\cos x<\\sin x/x<1$。\n' +
    '3. 两侧都趋于 1；再结合偶函数性质，可得双侧极限为 1。\n\n' +
    '试一试：$\\lim_{x\\to 0}\\sin(3x)/x$ 是多少？\n' +
    '这段回复是预设例题说明，不是对任意输入的自动诊断。';

  var REPLY_DERIVATIVE =
    '【固定例题演示】\n\n' +
    '以 $f(x)=x^2$ 为例，从定义理解导数：\n' +
    "$$f'(x)=\\lim_{h\\to0}\\frac{(x+h)^2-x^2}{h}=\\lim_{h\\to0}(2x+h)=2x$$\n" +
    '1. 写出函数增量 $(x+h)^2-x^2$。\n' +
    '2. 展开并约去 $h$，注意取极限前 $h\\ne0$。\n' +
    '3. 令 $h$ 趋近于 0，得到 $2x$。\n\n' +
    '你能解释为什么不能在约分前直接令 $h=0$ 吗？\n' +
    '这是固定例题，尚未接入自动解题或数学工具校验。';

  var REPLY_FALLBACK =
    '【交互演示 · 未连接真实模型】\n\n' +
    '你的问题已保存。当前版本先验证提问、反馈和历史记录的完整流程，还不能生成针对这个问题的解答。\n\n' +
    '可以点击示例问题，体验“求 sin(x)/x 的极限”或“用定义求 x² 的导数”的预设讲解。\n' +
    '未来将在这里接入课程检索、分层提示与步骤诊断。';

  /* SECTION: seed-assignment
     预置一份作业，使师生作业闭环开箱即可体验。 */
  function seedAssignments() {
    var due = new Date();
    due.setDate(due.getDate() + 3);
    return [{
      id: 'a-seed-1',
      title: '导数定义与几何意义',
      content: '请用导数定义推导 f(x)=x² 的导数，并说明每一步为什么成立。\n\n要求：\n1. 写出函数增量与差商；\n2. 说明取极限前 h 为什么不能等于 0；\n3. 用一句话解释 f′(2)=4 的几何意义。\n\n鼓励写下你的思考过程，本版本不自动评分。',
      topic: '导数与微分',
      due_date: isoDate(due),
      created_at: new Date().toISOString(),
      submissions: []
    }];
  }

  function isoDate(d) {
    return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
  }

  window.SHUBAN = {
    USERS: USERS,
    NAV_STUDENT: NAV_STUDENT,
    NAV_TEACHER: NAV_TEACHER,
    LESSONS: LESSONS,
    PROMPTS_STUDENT: PROMPTS_STUDENT,
    PROMPTS_TEACHER: PROMPTS_TEACHER,
    REPLY_TEACHER: REPLY_TEACHER,
    REPLY_FEYNMAN: REPLY_FEYNMAN,
    REPLY_SIN_LIMIT: REPLY_SIN_LIMIT,
    REPLY_DERIVATIVE: REPLY_DERIVATIVE,
    REPLY_FALLBACK: REPLY_FALLBACK,
    seedAssignments: seedAssignments,
    isoDate: isoDate
  };
})();
