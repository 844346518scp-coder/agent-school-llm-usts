# 接口约定入口

最后更新：2026-09-17，MVP 0.1。请求与响应使用 JSON；ID 为字符串，created_at 使用 UTC ISO 8601，due_date 为本地日历日期 YYYY-MM-DD。负责人边界：C 负责认证、作业与存储，B 负责演示问答；本轮用户授权 Codex 贯通这些模块，具体人员仍待认领。

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
| GET /api/assignments | 无 | 教师自己的作业 / 学生演示班级作业 |
| POST /api/assignments | title(1—100)、content(1—3000)、topic(1—40)、due_date | 201，作业；仅教师，日期不得早于今天 |
| PUT /api/assignments/{id}/submission | answer(1—5000，非空白) | 修改后作业；仅学生，截止日后拒绝 |

问答记录字段：id、question、answer、topic、favorite、created_at、mode（恒为 demo）。topic 可选“函数与极限”“导数与微分”“费曼练习”“教学设计”，默认“函数与极限”。每次提交是独立问题，不实现多轮上下文推理；除收藏外不可修改原问答。教师不能查看学生私人对话。

作业字段：id、title、content、topic、due_date、created_at、submitted、answer。学生只收到自己的提交状态和答案；教师额外收到 submissions 数组（student_name、answer、created_at）。教师仅可查看自己发布的作业。当前所有预设学生在同一演示班级，多班级权限尚未实现。相同学生对同一作业使用 PUT 更新，不新增重复提交，不自动评分。

错误格式为 FastAPI 的 `detail`：业务错误为字符串，422 字段验证为明细数组。401 表示未登录或凭据错误；403 表示角色或请求来源校验失败；404 表示记录不可见或不存在；409 表示作业过期。所有 /api 响应带 Cache-Control: no-store。

真实模型流式输出、OCR 上传与确认、诊断任务状态、语音、RAG 引用及异步任务接口仍待定义。改接口先更新此文档并协调调用方；新增子目录依照 [协作规范](../../AGENTS.md) 先确认。
