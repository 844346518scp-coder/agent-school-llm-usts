# 接口约定入口

最后更新：2026-09-17，MVP 0.1。请求与响应使用 JSON；ID 为字符串，created_at 使用 UTC ISO 8601，due_date 为本地日历日期 YYYY-MM-DD。负责人边界：C 负责认证、作业与存储，B 负责演示问答；本轮用户授权 Codex 贯通这些模块，具体人员仍待认领。

所有写请求必须带 `X-Requested-With: shuban-web`，使用同源 HttpOnly Cookie 认证。不开放跨域 CORS。前端统一客户端在 frontend/src/shared/api.ts，错误保留输入并提示，客户端超时 15 秒，不自动重试写请求。

| 方法与路径 | 请求 | 响应 / 权限 |
|---|---|---|
| GET /api/health | 无 | status、agent_mode（当前生效模式 demo/live）、version；公开 |
| POST /api/auth/login | username、password、role(student/teacher)、remember(bool，默认 false) | id、username、name、role；设置 Cookie；身份不匹配也拒绝 |
| GET /api/auth/me | 无 | 当前用户公共字段；未登录 401 |
| POST /api/auth/logout | 无 | ok=true；撤销当前会话并清除 Cookie |
| GET /api/conversations | 无 | 当前用户的全部问答，按创建时间倒序 |
| POST /api/conversations | question(1—2000 字符，非空白)、topic | 201，问答记录；自动保存演示回复 |
| PATCH /api/conversations/{id} | favorite(bool) | 修改后问答；非本人记录返回 404 |
| GET /api/assignments | 无 | 教师自己的作业 / 学生演示班级作业 |
| POST /api/assignments | title(1—100)、content(1—3000)、topic(1—40)、due_date | 201，作业；仅教师，日期不得早于今天 |
| PUT /api/assignments/{id}/submission | answer(1—5000，非空白) | 修改后作业；仅学生，截止日后拒绝 |

问答记录字段：id、question、answer、topic、favorite、created_at、mode（恒为 demo）。topic 可选“函数与极限”“导数与微分”“费曼练习”“教学设计”，默认“函数与极限”。每次提交是独立问题，不实现多轮上下文推理；除收藏外不可修改原问答。教师不能查看学生私人对话。

作业字段：id、title、content、topic、due_date、created_at、submitted、answer。学生只收到自己的提交状态和答案；教师额外收到 submissions 数组（student_name、answer、created_at）。教师仅可查看自己发布的作业。当前所有预设学生在同一演示班级，多班级权限尚未实现。相同学生对同一作业使用 PUT 更新，不新增重复提交，不自动评分。

错误格式为 FastAPI 的 `detail`：业务错误为字符串，422 字段验证为明细数组。401 表示未登录或凭据错误；403 表示角色或请求来源校验失败；404 表示记录不可见或不存在；409 表示作业过期。所有 /api 响应带 Cache-Control: no-store。

真实模型与流式输出、RAG 引用、诊断已于 2026-09-17 由 B 模块给出接口（见下节“智能体接口 v0.2”）。仍待定义：拍照识别的上传与确认流程细节、诊断任务状态（异步）、语音、长期记忆与异步任务队列。改接口先更新此文档并协调调用方；新增子目录依照 [协作规范](../../AGENTS.md) 先确认。

## 2026-09-17 · 智能体接口 v0.2（B 模块）

状态：草案，已实现、可本地运行（`python -m pytest -q` 40 passed）。前端（A）可按此联调，正式启用需在 PR 中同步确认。

模式约定：所有回答都带 `mode` 字段。`demo` 表示预设演示内容，`live` 表示真实模型输出；缺少模型凭据或调用失败时一律回退为 `demo`，并在 `notice` 中说明原因。**不允许把演示文案冒充模型输出**。

### 新增公共能力探针

| 方法 / 路径 | 是否鉴权 | 响应要点 |
| --- | --- | --- |
| GET /api/agent/status | 公开 | version、mode、requested_mode、model{ready,name,vision_name,endpoint,timeout_seconds}、knowledge{engine,points,topics,verified_points,pending_review}、capabilities{qa,qa_stream,references,diagnosis,recognize,memory,recommendation}、notes；不返回任何密钥 |

### 新增问答 / 反馈 / 诊断接口（需登录会话 + `X-Requested-With: shuban-web`）

| 方法 / 路径 | 请求 | 响应要点 |
| --- | --- | --- |
| POST /api/agent/ask | question（1–2000 字）、topic（默认“函数与极限”）、role（student/teacher） | answer、mode、notice、references、persisted=false；不写入学习记录，便于联调与评测 |
| POST /api/agent/ask/stream | 同 /ask | `text/event-stream`，事件 meta → delta → done；模型失败时先发 fallback 再发演示文本 |
| POST /api/agent/feedback | question、step（本次提交的一步）、steps[]（已写步骤）、topic | mode、notice、verdict（`correct` / `incorrect` / `unclear`）、hint、next_question、flagged[]、references、method |
| POST /api/agent/diagnosis | question、answer、wrong_points[]、topic（均可选） | mode、notice、weak_points[]{id,title,topic,reason,confidence,source}、related_points[]{index,id,title,source,score,matched}、suggested_practice[]{point_id,title,prompt,source}、summary、next_step、method |
| POST /api/agent/recognize | image_base64、media_type（默认 image/png）、hint | mode=live 时返回 text、confidence、warnings、**requires_confirmation=true**、suggested_topic、confirm_endpoint；未配置模型时返回 503 并说明原因（不返回编造结果） |

### 最小版核心流程（9/20 交付：提问 → 确认 → 反馈 → 保存 → 再次学习）

1. **提问**：`POST /api/agent/ask` 先看结果与引用（不落库，便于试错）；确认要保存时调用 `POST /api/conversations`。
2. **引用**：响应 `references[i].index` 与正文中的 `[1]`、`[2]` 一一对应；`source` 是资料出处，`verified=false` 表示待课程资料复核。demo 模式的答案正文会附一行“本轮检索到的课程资料（未经模型解读）”，避免误认为已由资料生成。
3. **拍照识别与确认**：`POST /api/agent/recognize` 只返回草稿（`requires_confirmation=true` + `suggested_topic`）；学生在界面校对/修正后，用确认后的题目调用 `POST /api/conversations` 保存并生成回答。识别接口不会自动入库，也不会代替学生确认。
4. **步骤反馈**：`POST /api/agent/feedback` 只判断学生本次提交的这一步，`steps[]` 传已写步骤作为上下文；不返回整题答案。demo 模式只标记明显错误（命中规则表 → `incorrect`）或返回 `unclear`，**不会**给出 `correct`。
5. **保存与再次学习**：`GET /api/conversations` 取历史，`PATCH /api/conversations/{id}` 收藏错题（既有接口，未变）。

### 既有接口的增量字段（向后兼容）

| 方法 / 路径 | 变化 |
| --- | --- |
| POST /api/conversations | 响应新增 `mode`、`notice`、`references`；live 模式答案末尾附“资料来源”编号列表，因此历史记录自带引用，无需改表 |
| GET /api/conversations | 每条记录的 `mode` 由答案文本中的演示标记反推（历史数据仍为 demo），存储结构未变 |

### 字段与降级约定

- 前端如需显示“AI 模式”角标，请以 `mode` 字段为准，不要根据答案长度或关键词猜测。
- 课程知识点内容位于 `backend/app/ai/knowledge.py`（当前 7 个知识点，全部 `verified=false`，待课程资料复核后置为 True）。
- 检索当前为本地 BM25（中文按字 bigram），`retrieve()` 签名保持不变，后续可替换为向量检索。

### 仍待 B 模块后续定义（不属于 9/20 最小版）

- 诊断任务状态与异步任务队列、长任务进度。
- 长期记忆读写策略、跨会话画像。
- 语音输入输出、资源检索与总结评价（9/21–24 功能扩展版）。
- 拍照识别的多题切分与公式人工修正细节（当前只有单次转录 + 确认）。
