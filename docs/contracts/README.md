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
| GET /api/health | 无 | status、agent_mode=demo、version；公开 |
| POST /api/auth/login | username、password、role(student/teacher)、remember(bool，默认 false) | id、username、name、role；设置 Cookie；身份不匹配也拒绝 |
| GET /api/auth/me | 无 | 当前用户公共字段；未登录 401 |
| POST /api/auth/logout | 无 | ok=true；撤销当前会话并清除 Cookie |
| GET /api/conversations | 无 | 当前用户的全部问答，按创建时间倒序 |
| POST /api/conversations | question(1—2000 字符，非空白)、topic | 201，问答记录；自动保存演示回复 |
| PATCH /api/conversations/{id} | favorite(bool) | 修改后问答；非本人记录返回 404 |
| GET /api/assignments | 无 | 教师自己的所有状态作业 / 学生演示班级非草稿作业 |
| POST /api/assignments | title(1—100)、content(1—3000)、topic(1—40)、due_date | 201，作业；仅教师，日期不得早于今天 |
| PUT /api/assignments/{id}/submission | answer(1—5000，非空白) | 修改后作业；仅学生，截止日后或归档后拒绝 |

问答记录字段：id、question、answer、topic、favorite、created_at、mode（恒为 demo）。topic 可选“函数与极限”“导数与微分”“费曼练习”“教学设计”，默认“函数与极限”。每次提交是独立问题，不实现多轮上下文推理；除收藏外不可修改原问答。教师不能查看学生私人对话。

作业保留原字段 id、title、content、topic、due_date、created_at、submitted、answer，并增加上述 status/submission/submissions 及版本化反馈结构。学生只收到自己的提交和反馈；教师仅可查看自己创建的作业。当前所有预设学生在同一演示班级，多班级权限尚未实现。相同学生对同一作业使用 PUT 更新，不新增重复提交，不自动评分。

错误格式为 FastAPI 的 `detail`：业务错误为字符串，422 字段验证为明细数组。401 表示未登录或凭据错误；403 表示角色或请求来源校验失败；404 表示记录不可见或不存在；409 表示作业截止、生命周期不允许或作答版本冲突。所有 /api 响应带 Cache-Control: no-store。

真实模型流式输出、OCR 上传与确认、诊断任务状态、语音、RAG 引用及异步任务接口仍待定义。改接口先更新此文档并协调调用方；新增子目录依照 [协作规范](../../AGENTS.md) 先确认。
