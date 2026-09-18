# 接口约定入口

## 0.2 本地教师工作流

仍使用同源 Cookie 与 X-Requested-With，题库和作业写操作仅所属教师可用；学生只能看到非草稿作业与自己的答案/反馈。截止日期按服务器本地日历计算，截止当天仍可提交。

- GET/POST `/api/questions`：教师自己的题库；GET 支持 search、topic、archived；POST 接收 title、topic、content、reference_answer。PATCH `/{id}` 编辑未归档题目，POST `/{id}/archive` 幂等归档。题目 ID、teacher_id、archived、created_at、updated_at 由服务端管理。
- POST `/api/assignments/drafts`：可传不完整的 title/content/topic/due_date（缺日期保存空字符串）；可传有序 question_ids，从本人未归档题目复制题干，不复制参考答案。PATCH `/api/assignments/{id}` 编辑草稿；已发布时只允许 due_date 且不得缩短；归档不可编辑。DELETE `/{id}` 仅删除草稿。
- POST `/api/assignments/{id}/publish`：验证完整内容与日期后发布，重复调用幂等；POST `/{id}/archive`：仅已发布转归档，重复调用幂等；POST `/{id}/copy`：从本人作业复制新草稿，不复制提交或反馈。
- POST `/api/assignments` 保持原直接发布兼容；GET 列表新增 status=draft/published/archived，学生永不获得 draft。PUT `/{id}/submission` 仅已发布且未截止可提交；每次保存递增 version。
- PUT `/api/assignments/{id}/submissions/{student_id}/review`：version（正整数）、comment（非空，最多3000字符）、status（needs_improvement/completed）。仅未归档作业可批改；作答版本变化返回409。相同版本可修改评语，按版本保留 answer_snapshot 和 feedback 历史。
- GET `/api/teaching/stats`：返回 published、submitted、pending、needs_improvement、completed，只计算当前教师未归档的已发布作业及最新作答。
- 作业新增 status；学生返回 submission（id、student_id、student_name、answer、created_at、version、review、review_history），旧 answer/submitted 保留；教师 submissions 使用同一提交结构。review 为当前版本反馈或 null；review_history 仅旧版本反馈（含 version、comment、status、answer_snapshot、reviewed_at）。参考答案永不混入作业响应。
- 草稿字段长度沿用原限制；题目 title<=100、topic<=40、content<=3000、reference_answer<=3000，非空标题/章节/题干；question_ids<=30 且不重复，合并作业题干仍<=3000。未提供 PATCH 字段保持原值；null 不可用于清空，草稿日期通过空字符串清空。未知字段返回422。
- 错误沿用 detail；401未登录、403角色不符、404无权访问或不存在、409生命周期/作答版本冲突、422内容不合规。

## 通用格式、认证与演示问答

下列认证/问答行为与 0.1 兼容，作业生命周期及反馈结构按上述 0.2 定义。

最后更新：2026-09-17，MVP 0.2。请求与响应使用 JSON；ID 为字符串，created_at 使用 UTC ISO 8601，due_date 为本地日历日期 YYYY-MM-DD。负责人边界：C 负责认证、题库、作业、人工反馈与存储，B 负责演示问答；本轮用户授权 Codex 贯通这些模块，C 已由当前用户认领，A/B 负责人仍待确认。

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
| GET /api/assignments | 无 | 教师自己的所有状态作业 / 学生演示班级非草稿作业 |
| POST /api/assignments | title(1—100)、content(1—3000)、topic(1—40)、due_date | 201，作业；仅教师，日期不得早于今天 |
| PUT /api/assignments/{id}/submission | answer(1—5000，非空白) | 修改后作业；仅学生，截止日后或归档后拒绝 |

问答记录字段：id、question、answer、topic、favorite、created_at、mode（demo或live）。topic 可选“函数与极限”“导数与微分”“费曼练习”“教学设计”，默认“函数与极限”。每次提交是独立问题，不实现多轮上下文推理；除收藏外不可修改原问答。教师不能查看学生私人对话。

作业保留原字段 id、title、content、topic、due_date、created_at、submitted、answer，并增加上述 status/submission/submissions 及版本化反馈结构。学生只收到自己的提交和反馈；教师仅可查看自己创建的作业。当前所有预设学生在同一演示班级，多班级权限尚未实现。相同学生对同一作业使用 PUT 更新，不新增重复提交，不自动评分。

错误格式为 FastAPI 的 `detail`：业务错误为字符串，422 字段验证为明细数组。401 表示未登录或凭据错误；403 表示角色或请求来源校验失败；404 表示记录不可见或不存在；409 表示作业截止、生命周期不允许或作答版本冲突。所有 /api 响应带 Cache-Control: no-store。

B智能体接口已定义并在本轮集成，见下文；语音、异步任务和完整上传流程仍待实现。

## 便携启动健康标识（2026-09-18）

`GET /api/health`原有字段保持；便携启动设置`SHUBAN_INSTANCE_ID`时额外返回`instance_id`（由本地路径哈希生成，非会话/认证凭据），供启动器识别本目录服务，避免误复用另一份测试包。此字段不授予访问权限。便携包网页与API同源于127.0.0.1:18080（可换端口），其余接口不变。

真实模型与流式输出、RAG 引用、诊断已于 2026-09-17 由 B 模块给出接口（见下节“智能体接口 v0.2”）。拍照识别的上传与确认流程已于 2026-09-18 在前端落地（见下节“拍照识别前端调用约定”）。仍待定义：诊断任务状态（异步）、语音、长期记忆与异步任务队列。改接口先更新此文档并协调调用方；新增子目录依照 [协作规范](../../AGENTS.md) 先确认。

## 2026-09-18 · 拍照识别前端调用约定

前端入口位于 `frontend/src/shared/PhotoSearchDialog.vue`，由 `AgentView.vue` 对话头的「拍照搜题」按钮打开。调用与确认流程如下，接口字段未变更：

1. **上传**：`POST /api/agent/recognize`，请求体 `{ image_base64, media_type, hint }`。`image_base64` 为裁剪压缩后的纯 base64（不含 `data:` 前缀，与 `service.py` 中 `RecognizeInput` 一致）；`media_type` 取 `image/jpeg` 或 `image/png`；`hint` 为可选题目提示，前端限长 200 字符。
2. **传输方式**：复用 `frontend/src/shared/api.ts` 的 `api()`，自动携带 `Content-Type: application/json`、`X-Requested-With: shuban-web` 与 `credentials: same-origin`；该路径命中 `isAiWrite`，超时 90 秒，不做自动重试。
3. **确认**：后端返回 `requires_confirmation=true`，前端把 `text` 放入可编辑文本框，由学生核对或修正；确认后仅回填到提问框，再由学生决定是否发送。发送走既有 `POST /api/conversations`，组件本身不入库、不代替学生确认。
4. **来源标注**：仅当返回 `mode === 'live'` 才标为真实接口结果；`confidence`、`warnings`、`suggested_topic` 原样展示。
5. **失败处理**：`503`（未配置视觉模型）、`502`（调用失败）与网络异常均如实展示 `detail` 原文，不回退为编造的识别文本。
6. **仍待定义**：多题切分、公式人工修正、语音输入。

## 2026-09-17 · 智能体接口 v0.2（B 模块）

状态：2026-09-18已与C本地集成，普通问答页面已接入模式、降级提示和引用；其他AI页面入口后续接入。

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
4. **步骤反馈**：`POST /api/agent/feedback` 只判断学生本次提交的这一步，`steps[]` 传已写步骤作为上下文；不返回整题答案。demo模式命中关键词也只返回`unclear`，提供待复核提示，不确定对错。
5. **保存与再次学习**：`GET /api/conversations` 取历史，`PATCH /api/conversations/{id}` 收藏错题（既有接口，未变）。

### 既有接口的增量字段（向后兼容）

| 方法 / 路径 | 变化 |
| --- | --- |
| POST /api/conversations | 响应新增 `mode`、`notice`、`references`；live 模式答案末尾附“资料来源”编号列表，因此历史记录自带引用，无需改表 |
| GET /api/conversations | 新记录由后端写入固定来源前缀并据此前缀返回mode；旧记录兼容原演示标记识别，存储结构未变 |

### 字段与降级约定

- 前端如需显示“AI 模式”角标，请以 `mode` 字段为准，不要根据答案长度或关键词猜测。
- 课程知识点内容位于 `backend/app/ai/knowledge.py`（当前 7 个知识点，全部 `verified=false`，待课程资料复核后置为 True）。
- 检索当前为本地 BM25（中文按字 bigram），`retrieve()` 签名保持不变，后续可替换为向量检索。

### 仍待 B 模块后续定义（不属于 9/20 最小版）

- 诊断任务状态与异步任务队列、长任务进度。
- 长期记忆读写策略、跨会话画像。
- 语音输入输出、资源检索与总结评价（9/21–24 功能扩展版）。
- 拍照识别的多题切分与公式人工修正细节（当前只有单次转录 + 确认）。


## 2026-09-18 集成修正

- health增加agent_version=0.2.0识别集成B后的服务；agent_mode动态为demo/live；可选instance_id用于目录识别，不是认证凭据。默认源码模式与可选便携模式均同源提供页面/API。
- 新问答正文持久保存“回复来源：模型/演示”前缀与失败提示，确保刷新/重登、收藏后来源稳定；老记录按已有演示标记兼容识别。references结构在POST返回，历史的引用保存在正文，无结构化引用字段迁移。
- demo模式即使填写凭据也不调用问答/识别模型；recognize返回503，status.capabilities.recognize/qa_stream按生效live模式报告。
- MODEL_TIMEOUT_SECONDS限制1–60秒（默认30），AI前端等待90秒，普通请求15秒。无自动重试；接收失败先查历史。httpx超时为网络阶段超时，不能承诺远端整个任务硬性在该秒数结束。
- SSE fallback包含replace=true；使用流式接口的客户端必须丢弃此前未完成的模型文本，再展示演示回复，不能拼接为同一答案。当前网页未使用流式接口。
- 模型网络异常及非2xx响应不会原样向学生输出远端错误正文/URL，避免泄露凭据；status只显示endpoint的scheme/hostname。
- 诊断confidence为规则匹配启发值，未经学习效果校准，不是可靠掌握度；规则步骤verdict统一unclear。模型批改同样需复核，不自动写入教师反馈或错题确定标签。
