# 接口约定入口

## 2026-09-21 模拟验收发现（尚未修复，不改变现行接口）

后续免费Qwen3-VL-2B本地真实调用中，普通问答Q01/Q02超时后返回HTTP200、mode=demo及notice；两张合成PNG的识别均返回502及明确调用失败提示，没有可用于符号准确率统计的text。直接模型短请求成功不等于上述应用契约通过，也不改变status只反映配置是否齐全的边界。未改变超时、响应字段、权限或数据库结构，见[续测报告](../simulation-test-report.md)。

18场景HTTP顺序联动验证了师生权限/发布快照/作答版本/反馈/私人对话隔离。双端页面测试另出现SQLite锁冲突与统计读取失败，健康检查仍可200，因此health不是业务可用性证明。

本地识别响应没有related_points、references或知识点详情，suggested_topic仅主题建议；本轮合入的拍照前端将其显示为标签，不是知识点弹窗。离线合成探针复现：伪base64及text/plain通过RecognizeInput；模型返回空JSON仍得live空text，warnings为数字时抛未捕获TypeError（HTTP500为推断，函数探针未发HTTP）；积分/级数被建议为导数主题。上述为已知缺口，不是认可的目标契约。demo503与模拟ModelCallFailed转502符合现状；不得把该合成探针称真实视觉验收。详见[测试报告](../simulation-test-report.md)。

## 2026-09-21 教师交互精简（接口不变）

成员设置沿用原单人账号/成员端点。批量移出/恢复只对当前列表中所勾选且需要变更的成员依次调用PATCH /api/classes/{id}/members/{student_id}，每次均由服务器校验归属和班级状态。执行前确认固定名单；首个失败后停止，报告已完成与未执行人数并刷新，不是原子批量事务，不自动重试超时，不改变发布收件快照或其他班级身份。manageable=false仍只允许本班成员维护，不授予账号管理权。

题库直接按章号分组显示，无需预选章节；作业编辑不再显示所属章节下拉。topic字段仍存在，同章选题自动推导、混合章节使用综合练习；手写新作业及旧空topic回落综合练习，未重新选题的旧非空topic保留。日期、题干限制、权限及schema v3不变。

## 2026-09-20 教师入口整合

教师侧边栏保留教学概览、班级管理、教学助手、账号设置。班级管理内进入本班作业或独立成员页；全部作业与未分班草稿仍可从班级管理访问。布置/编辑草稿时内嵌题库，按同济《高等数学》第八版上下册12章顺序分组，兼容原有自定义topic。

本轮沿用v0.3所有HTTP契约及schema v3，没有迁移。题库选题重新读取本人有效题目后，仅把标题、题干按选定顺序追加到编辑中的content；保留已填写内容，不复制reference_answer。最终仍用既有草稿POST/PATCH与发布端点，保持3000字限制、班级授权和发布收件快照。

对话记录现从Agent聊天顶部进入，复用GET /api/conversations和PATCH /api/conversations/{id}收藏接口；按问题/章节搜索、筛选已收藏和选记录回看均为前端行为，无新端点、无schema迁移，也不改变个人记录隔离。学生原学习记录导航保留。

## 2026-09-19 教师工作空间 v0.3 实施约定

最后更新：2026-09-19。本节为本地`codex/teacher-workspace`教师工作空间v0.3契约，优先于下方0.2沿用字段/历史行为；v0.3及9/20至21界面增量已上传原分支codex/c-local-teaching，本轮与main拍照入口整合，HTTP契约保持不变。SQLite新增schema v3；教师私有题库、作答版本和人工反馈保持。验收结果见开发日志，不把本节接口存在当作真实师生效果证明。

- 默认不植入演示用户或作业。`GET /api/auth/setup`按是否已有教师返回`{required}`；`POST /api/auth/setup`接收`username,name,password`，事务内只允许首次创建教师，201返回User并登录，之后409。已有教师可`POST /api/auth/teachers`创建同级教师，201返回新User且其`must_change_password=true`，不改变当前教师会话。演示种子须显式SHUBAN_SEED_DEMO=true且用户表为空；重启不补回已有库的数据。
- User公共字段为`id,username,name,role,active,must_change_password,is_demo`；不返回password_hash或created_by。`POST /api/auth/password`接收`current_password,new_password`，旧密码错误403、新旧相同422，成功撤销所有旧会话并签发新会话，返回User且清除演示/强制改密标记；`PATCH /api/auth/profile`接收name。临时密码登录后必须改密，业务访问403，仅允许me/password/logout等账号必要操作；停用账号认证401。账号3–80位英文/数字/._-，姓名1–80位非空；新密码10–128字符含英文字母数字，不回传明文。重复账号409，未知字段422。
- `GET/POST /api/classes`：教师自己的全部班级列表/创建，name/course/term均1–80位非空，POST201；响应`id,name,course,term,archived,student_count,created_at`，人数是有效账号且在班的成员。`PATCH /api/classes/{id}`可编辑或设置archived，班级归档可恢复。`GET /api/classes/{id}/students`返回成员User字段及`member_active,manageable,submitted,completed,pending,needs_improvement,expected`，按该班已发布作业快照统计；包含已移出/停用成员。manageable=false时不可编辑/重置/停用账号，但仍能维护本班成员。归档班级名册仍可读历史进度。
- `POST /api/classes/{id}/students`创建学生并加入班级（`username,name,password`），密码只用于创建，学生须首次改密；账号管理归属创建教师。`POST /api/classes/{id}/members`以`{username}`加入本教师管理的已有学生，跨教师禁止。`PATCH /api/classes/{id}/members/{student_id}`以`{active}`移出/恢复成员。`PATCH /api/students/{id}`以`{name?,active?}`编辑/停用本人管理学生；`POST /api/students/{id}/password`以`{password}`重置临时密码，撤销会话并要求改密。
- 作业新增`class_id,class_name,recipient_count,class_archived,can_submit`；can_submit由后端根据学生收件范围、成员/账号状态、归档及截止日期计算，前端不代替权限检查。草稿可未选班，发布须选本人有效班级且至少一位有效学生（不满足422），固定收件人快照；class_id可在草稿创建/PATCH传入，未选用null。发布后班级锁定。复制保留有效班级，不复制作答；源班归档则新草稿class_id=null。历史库按各教师建历史班级保留旧可见范围；仅单教师旧库推定学生账号管理人，多教师不擅自授予管理权。
- 学生GET作业只返回本人是收件人的非草稿作业，跨班提交404；已移出、停用或归档的班级不可提交（原历史仍可只读）。后加入成员不自动获得旧作业，需教师复制发布。教师仍可查看历史提交；反馈只能在作业及班级均未归档时写入。
- `GET /api/teaching/stats?class_id=`新增`classes,students,expected,unsubmitted`，保留旧5项；按当前教师未归档班级/已发布作业统计，应交为收件快照总数，未交为应交减当前提交；有效学生去重，不因退班而改写历史应交。不读取私人对话。GET作业支持class_id过滤，未授权班级404。API错误仍用detail/401/403/404/409/422及既有写请求头。
- `GET /api/health`新增`teaching_version="0.3.0",schema_version=3`；原version/agent_version保持0.2.0兼容B客户端，agent_mode仍如实demo/live，可选instance_id仍只是目录标识。启动器同时核验模块/数据版本，拒绝复用同目录旧后台。
- 页面落实班级建档/编辑/归档、学生创建/已有成员加入/移出/停用/改密、班级筛选、按人提交进度及CSV导出；教学概览人数来自API，头像和名称来自当前用户。教学助手继续按每条回复实际mode标记，未配置模型不能消除演示标记。
- CSV由前端依据已授权的班级名册生成，没有新增导出API；只导出当前搜索/成员状态筛选结果。列为班级、账号、姓名、成员状态、账号状态、应交、已交、未交、待批改、待改进、已完成。使用UTF-8 BOM、CRLF、双引号转义及公式前缀防护；下载和Excel兼容的验收边界见日志，不把文件内容测试等同于实际落盘。


以下登记沿用的题库/反馈/AI字段及历史集成背景。涉及默认账号、班级授权、统计范围、发布必填字段时以上方v0.3为准。拍照Vue流程已随本轮合并纳入；“仍待定义”不代表已实现。

## 0.2 本地教师工作流

沿用同源Cookie与X-Requested-With，题库/作业仅所属教师可写；v0.3学生还必须是发布收件人，且仅拿到自己的答案/反馈。截止按服务器本地日历，截止当天仍可提交。

- GET/POST `/api/questions`：教师自己的题库；GET 支持 search、topic、archived；POST 接收 title、topic、content、reference_answer。PATCH `/{id}` 编辑未归档题目，POST `/{id}/archive` 幂等归档。题目 ID、teacher_id、archived、created_at、updated_at 由服务端管理。
- POST `/api/assignments/drafts`：可传不完整的 title/content/topic/due_date（缺日期保存空字符串）；可传有序 question_ids，从本人未归档题目复制题干，不复制参考答案。PATCH `/api/assignments/{id}` 编辑草稿；已发布时只允许 due_date 且不得缩短；归档不可编辑。DELETE `/{id}` 仅删除草稿。
- POST `/api/assignments/{id}/publish`：验证完整内容与日期后发布，重复调用幂等；POST `/{id}/archive`：仅已发布转归档，重复调用幂等；POST `/{id}/copy`：从本人作业复制新草稿，不复制提交或反馈。
- POST `/api/assignments`保留直接发布端点，v0.3需class_id；GET列表状态draft/published/archived，学生永不获得draft。PUT submission每次保存递增version，且需符合v0.3成员/收件/归档权限。
- PUT `/api/assignments/{id}/submissions/{student_id}/review`：version（正整数）、comment（非空，最多3000字符）、status（needs_improvement/completed）。仅未归档作业可批改；作答版本变化返回409。相同版本可修改评语，按版本保留 answer_snapshot 和 feedback 历史。
- GET `/api/teaching/stats`：返回 published、submitted、pending、needs_improvement、completed，只计算当前教师未归档的已发布作业及最新作答。
- 作业新增 status；学生返回 submission（id、student_id、student_name、answer、created_at、version、review、review_history），旧 answer/submitted 保留；教师 submissions 使用同一提交结构。review 为当前版本反馈或 null；review_history 仅旧版本反馈（含 version、comment、status、answer_snapshot、reviewed_at）。参考答案永不混入作业响应。
- 草稿字段长度沿用原限制；题目 title<=100、topic<=40、content<=3000、reference_answer<=3000，非空标题/章节/题干；question_ids<=30 且不重复，合并作业题干仍<=3000。未提供 PATCH 字段保持原值；null 不可用于清空，草稿日期通过空字符串清空。未知字段返回422。
- 错误沿用 detail；401未登录、403角色不符、404无权访问或不存在、409生命周期/作答版本冲突、422内容不合规。

## 通用格式、认证与演示问答

下列认证/问答行为与 0.1 兼容，作业生命周期及反馈结构按上述 0.2 定义。

请求响应JSON；ID字符串，created_at UTC ISO8601，due_date本地日历YYYY-MM-DD。C负责账号/班级/题库/作业/人工反馈/权限存储，B负责模型/检索/识别/诊断；C当前用户认领，A/B负责人待确认。

所有写请求必须带 `X-Requested-With: shuban-web`，使用同源 HttpOnly Cookie 认证。不开放跨域 CORS。前端统一客户端在 frontend/src/shared/api.ts，错误保留输入并提示，客户端超时 15 秒，不自动重试写请求。

| 方法与路径 | 请求 | 响应 / 权限 |
|---|---|---|
| GET /api/health | 无 | status、agent_mode（当前生效模式 demo/live）、version；公开 |
| POST /api/auth/login | username、password、role(student/teacher)、remember(bool，默认 false) | id、username、name、role；设置 Cookie；身份不匹配也拒绝 |
| GET /api/auth/me | 无 | 当前用户公共字段；未登录 401 |
| POST /api/auth/logout | 无 | ok=true；撤销当前会话并清除 Cookie |
| GET /api/conversations | 无 | 当前用户的全部问答，按创建时间倒序 |
| POST /api/conversations | question(1—2000 字符，非空白)、topic | 201，保存回复及实际来源标记（demo/live） |
| PATCH /api/conversations/{id} | favorite(bool) | 修改后问答；非本人记录返回 404 |
| GET /api/assignments | 可选class_id | 教师自己的作业 / 学生收件快照中的非草稿作业 |
| POST /api/assignments | title(1—100)、content(1—3000)、topic(1—40)、due_date、class_id | 201，作业；仅教师，班级须有效且有有效学生，日期不得早于今天 |
| PUT /api/assignments/{id}/submission | answer(1—5000，非空白) | 修改后作业；仅学生，截止日后或归档后拒绝 |

问答记录字段：id、question、answer、topic、favorite、created_at、mode（demo或live）。topic 可选“函数与极限”“导数与微分”“费曼练习”“教学设计”，默认“函数与极限”。每次提交是独立问题，不实现多轮上下文推理；除收藏外不可修改原问答。教师不能查看学生私人对话。

作业保留原id/title/content/topic/due_date/created_at/submitted/answer及0.2版本反馈结构，增加v0.3班级/收件字段。学生只拿自己的提交，教师仅看本人作业；同学生同作业PUT更新，不新增重复提交，不自动评分。旧全局学生可见规则只通过迁移历史收件快照保留，不用于新发布。

错误格式为 FastAPI 的 `detail`：业务错误为字符串，422 字段验证为明细数组。401 表示未登录或凭据错误；403 表示角色或请求来源校验失败；404 表示记录不可见或不存在；409 表示作业截止、生命周期不允许或作答版本冲突。所有 /api 响应带 Cache-Control: no-store。

B智能体接口已于2026-09-18集成，见下文；语音、异步任务和完整上传流程仍待实现。

## 便携启动健康标识（2026-09-18）

`GET /api/health`原有字段保持；便携启动设置`SHUBAN_INSTANCE_ID`时额外返回`instance_id`（由本地路径哈希生成，非会话/认证凭据），供启动器识别本目录服务，避免误复用另一份测试包。此字段不授予访问权限。便携包网页与API同源于127.0.0.1:18080（可换端口），其余接口不变。

真实模型与流式输出、RAG 引用、诊断已于 2026-09-17 由 B 模块给出接口（见下节“智能体接口 v0.2”）。远端main的后续提交已实现拍照识别上传与人工确认的前端调用流程，本轮已随main合并纳入当前工作区，真机及真实视觉模型仍待验收。仍待定义：多题切分、公式人工修正、诊断任务状态（异步）、语音、长期记忆与异步任务队列。改接口先更新此文档并协调调用方；新增子目录依照 [协作规范](../../AGENTS.md) 先确认。

## 2026-09-18 · 拍照识别前端调用约定（9/21合入当前工作区）

入口位于`frontend/src/shared/PhotoSearchDialog.vue`，由`AgentView.vue`对话头的“拍照搜题”按钮打开。本轮保留教师v0.3和对话历史功能，整合main 168928d的拍照入口。识别回填与现有提问合计不得超过2000字，超限时保留原问题和识别草稿，由用户缩短后重试；不自动截断公式。

1. **上传**：`POST /api/agent/recognize`，请求体`{ image_base64, media_type, hint }`。`image_base64`为裁剪压缩后的纯base64，不含`data:`前缀；`media_type`为`image/jpeg`或`image/png`；`hint`最多200字符。
2. **传输**：复用`frontend/src/shared/api.ts`的`api()`，自动携带JSON内容类型、`X-Requested-With: shuban-web`和同源Cookie；AI写请求超时90秒，不自动重试。
3. **确认**：返回文本放入可编辑框。用户确认后只回填既有提问框，再自行决定是否发送；发送仍走`POST /api/conversations`。拍照组件不直接保存问答，不绕过`requires_confirmation`。
4. **来源**：只有`mode === 'live'`可标为真实接口结果；`confidence`、`warnings`和`suggested_topic`仅作提示并原样展示，不能视为已核实结论。
5. **失败**：401/403、502、503和网络异常应如实展示，不生成替代识别文本。关闭弹窗应停止相机轨道并释放临时对象URL。
6. **验证边界**：贡献记录只有`vue-tsc --noEmit`和Vite生产构建通过；未验证浏览器真机、移动端触控、后端401/502/503分支或真实视觉模型质量。

远端独立原型默认调用的`POST /api/agent/video-search`目前不存在于后端路由，也未在本接口文档定义；调用方不得把该原型请求当作可用接口。

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

## 后续接口范围（未实现）

v0.3只提供教师私有资源与本地账号/班级。以下仍需另立契约，不可提前依赖：批量导入、学校实名认证/SSO、管理员、教师停用/角色转换、共同授课/助教、跨教师共享或转移学生、课程共享题库、自动找回密码、操作审计与PostgreSQL迁移。

AI反馈复核还需明确原始结果、教师修改、审核状态、发布人及时间，未经批准不能成为学生正式反馈。上述能力不因v0.3多班级实现而自动具备。

## 2026-09-21 · 智能体接口 v0.3（B 模块第二阶段）

状态：已实现、可本地运行（`python -m pytest -q` → 101 passed；`python tests/check_ai_contracts.py` → issues_reproduced=0、behaviors_as_expected=8）。
范围：长期记忆、推荐练习、评价（费曼复述/自评）、总结复习、资源检索。

### 第一阶段遗留缺口的修复（模拟验收列出的 6 项）

| 缺口 | 现状 |
| --- | --- |
| 拍照入参未校验 base64 / MIME | `RecognizeInput` 严格校验：非法 base64、非图片 MIME、缺少文件头的载荷都在入参阶段 422，不会送到模型；若声明的 MIME 与实际文件头不符，以实际文件头为准 |
| 积分/级数被猜成“导数与微分” | 知识库扩展到「一元函数积分学」「无穷级数」；覆盖不足时返回 `suggested_topic: null`，不猜 |
| 模型返回空 JSON 时透传空文本 | 识别结果为空时返回 502，并说明需重拍或手动输入 |
| `warnings` 为数字时抛非受控异常 | 非字符串列表一律忽略并标注，响应里 `warnings` 恒为数组 |
| 演示模式仍可能触达模型 | 识别在 `mode != live` 时直接 503，不调用模型（已有测试覆盖） |

### 新增接口（均需登录会话 + `X-Requested-With: shuban-web`）

| 方法 / 路径 | 请求 | 响应要点 |
| --- | --- | --- |
| GET /api/agent/memory | 无 | user_id、event_count、kinds、updated_at、points[]{point_id,title,topic,attempts,positive,negative,mastery,confidence,status,last_seen}、topics[]、weak_points[]、mastered_points[]、evidence_tags、privacy |
| DELETE /api/agent/memory | 查询参数 point_id（可选） | removed、scope=own_account；学生可清空自己的长期记忆 |
| POST /api/agent/recommend | topic、limit(1-8)、exclude[] | items[]{point_id,title,topic,reason,prompt,source,verified,mastery,status}、method、note；把上一批 point_id 放进 `exclude` 即“换一批” |
| POST /api/agent/review | text(1-4000)、topic、kind=feynman\|self | point、coverage、band（基本到位/有遗漏/需要重讲/无法评价）、memory_weight、signals_hit、signals_missing、advice[]、follow_up、model_comment、references、method |
| POST /api/agent/summary | days(1-90，默认 7)、topic | period_days、question_count、topics[]、covered_points、weak_points[]、mastered_points[]、highlights[]、next_steps[]、model_summary、references、method |
| POST /api/agent/resources/search | query(1-200)、topic、limit(1-20) | items[]{id,kind,topic,title,summary,point_id,source,verified,score}、total、note |

`GET /api/agent/status` 新增 `phase=2`；capabilities 增加 step_feedback、review、summary、resource_search，`memory` 改为 true，并新增 `async_tasks=false`。
`version` 仍为 0.2.0：`/api/health` 的 `agent_version` 会被启动器校验，变更需与 C 侧一起改。

### 长期记忆的口径与存储（重要）

- 掌握度 = 拉普拉斯平滑的加权成功率 `(正证据 + 1) / (正证据 + 负证据 + 2)`；没有证据时是 0.5 但状态为 `unseen`，**不判定掌握**。
- `status`：`weak`（掌握度 ≤0.4）、`learning`、`mastered`（≥0.75 且至少 2 条证据）、`unseen`。
- 证据只有三类可核对信号：学生自评/复述评价结果、步骤反馈结论、诊断命中；普通问答只记 `exposed`（权重 0）。
- 存储：B 自有追加式表 `ai_learning_events`，由 `backend/app/ai/memory.py` 用**独立 MetaData** 惰性建表，
  **不加入 `platform.database.Base`**——因为 `migrations/upgrade.py` 在 schema v3 时会校验 Base 里每张表都已存在，
  加表会让既有库启动报 “Incomplete schema”。该表与业务表同库，整库备份/恢复自然覆盖它。
  若日后要纳入版本化 schema，需平台侧出 v4 迁移并在 `upgrade.py` 加分支。
- 记忆写入是尽力而为：写失败不影响问答/反馈结果（`remember()` 捕获异常并回滚）。

### 前端（A）接入建议

1. 学生端“我的薄弱点”：`/api/agent/memory` 的 `weak_points` / `points`；`mastery` 与 `confidence` 要一起展示，避免把 0.5 当成“已掌握”。
2. 推荐练习：“换一批”把上一批 `point_id` 放进 `exclude`；每条 `reason` 已经写明依据，可直接展示，不要改写成“AI 智能推荐”。
3. 复述/自评：`/api/agent/review` 的 `band` + `signals_missing` + `follow_up` 做评价卡片；`model_comment` 只在 `mode=live` 时出现。
4. 复习页：`/api/agent/summary` 的 `highlights`、`next_steps` 可直接渲染；`mode=demo` 时不要显示“AI 生成”。
5. 资源检索：`kind` 可做筛选标签；`verified=false` 必须在界面标注“待复核”。
6. 拍照识别：`requires_confirmation=true` 时必须让学生确认或修正后再调用 `/api/conversations` 保存。

### 仍待 B 模块后续定义（不属于 9/24 冻结范围）

- 异步任务与长任务进度（当前 `async_tasks=false`）、诊断任务状态。
- 语音输入输出。
- 拍照识别的多题切分与公式人工修正细节。
- 教师端知识点掌握度聚合：当前长期记忆只对本人开放，教师端学情仍以作业提交统计为主；如需按班聚合，需要新增教师侧接口并定义权限边界。
- 资源库扩充：已在知识点派生的基础上追加 6 条跨模块资料/导览条目（章节导览 ×4、极限计算思路图、积分方法选择表），全部 `verified=false` 待复核；外部课件/视频接入后需同样的复核流程。

## 2026-09-25 · 智能体接口 v0.4（B 模块第三阶段）

状态：已实现、可本地运行（`python -m pytest -q` → 135 passed；`python tests/check_agent_accuracy.py` → 7 套件全部达标，62/62 用例）。
范围：分层提示、图形批注（步骤/坐标/讲解）、数学工具、语音服务适配、准确性评测、教师纠错、降级与错误统计。
字段冻结说明：`GET /api/agent/status` 的 `version` 仍为 `0.2.0`、`phase` 仍为 `2`（启动器与既有测试依赖），本轮新增 `stage=3` 标识阶段。

### 新增接口（POST 需登录会话 + `X-Requested-With: shuban-web`；两个探针为公开 GET）

| 方法 / 路径 | 请求 | 响应要点 |
| --- | --- | --- |
| POST /api/agent/hint | question(1–1000)、level(1–3，默认 1)、topic | level、level_title（概念提示/方法提示/关键步骤提示）、hint、self_check、next_level、answer_leaked=false、guard、point{id,title,topic,source,verified}、references、mode、method |
| POST /api/agent/plot/annotate | question、expr、at、topic、x_min、x_max、samples(2–241)、cx/cy/radius | shape、function{expr,latex,derivative,derivative_latex,derivative_checked}、viewport{x_min,x_max,y_min,y_max}、samples[[x,y]]、clipped、key_points[]{kind,label,x,y,slope,explain}、steps[]{index,title,detail,points}、explanation（live）、honesty |
| POST /api/agent/math/check | expr(1–200)、x、expected、compare_expr、x0 | expr、latex、variables、derivative{ok,derivative,derivative_latex,numeric_agreement}、value、value_check、limit、equivalence、method、limitations |
| GET /api/agent/voice/status | 无（公开） | ready、credential_source(voice_env/model_env/none)、model、endpoint(scheme+host)、timeout_seconds、limits{formats,max_bytes,max_duration_seconds}、text_to_speech=false、browser_fallback |
| POST /api/agent/voice/transcribe | audio_base64、media_type、language、duration_seconds、hint | text（纠错后）、raw_text、corrections[]{from,to,count}、warnings、changed、suggested_topic、requires_confirmation=true、confirm_endpoint；未配置语音服务 → 503；音频非法 → 422 |
| GET /api/agent/diagnostics | 无（需登录） | total、counters、recent[]{at,code,endpoint,detail,meaning}、codes、retry_policy{max_attempts:2,retryable_codes}、scope、math_tools、voice |
| POST /api/agent/evaluate | suites[]（可选） | **仅教师**；overall{cases,passed,failed,rate,ok}、suites[]{name,title,cases,passed,failed,rate,threshold,ok,failures,results}、scope、limitations、degradation |
| POST /api/agent/corrections | student_id、point_id、corrected(correct/incorrect/unclear)、reason、weight(-3..3)、origin | **仅教师**；correction{...}、point{id,title,topic}、before、after、state、note |
| GET /api/agent/corrections | limit（默认 50） | items[]{...,point_title,topic}、total、scope(teacher_self/own_account) |

`GET /api/agent/status` 新增 `stage=3`；capabilities 增加 `hints`、`plot_annotation`、`math_tools`、`accuracy_eval`、`teacher_correction`、`degradation_report`（恒为 true），`voice_input` 取决于语音凭据是否就绪（demo 模式下为 false）。

### 口径与硬约束（后续改动不要破坏）

- **分层提示**任何级别都不得包含最终答案，响应固定 `answer_leaked=false`；第 3 级只给“第一步动作”。
- **图形批注**的 `samples` 与 `key_points` 全部由本地数学工具算出；live 模式模型只写讲解（`explanation`/`step_notes`），不得改动数值。
- **数学工具**零第三方依赖；`-x^2` 解析为 `-(x^2)`；极限与等价性是数值证据，必须带 `method` 与说明，不得表述为证明。
- **语音**未配置凭据返回 503 并给出浏览器原生方案，不返回编造文本；转写结果只是草稿（`requires_confirmation=true`）。
- **教师纠错**为追加式补偿证据：不删除原始 `ai_learning_events`；`ai_corrections` 用独立 MetaData 惰性建表，**不进 `Base.metadata`**（原因同长期记忆：schema v3 校验会导致既有库启动失败）。
- **超时降级**只对网络阶段超时重试一次（`MAX_ATTEMPTS=2`），其它失败不重试；降级统计仅存进程内存，`sanitize()` 已去掉 URL 与长 token。

### 给前端（A）的接入建议

1. 分层提示做成“提示 / 再具体一点”按钮：`next_level` 为 null 时禁用；不要在前端自己拼接三级提示。
2. 图形批注直接用 `viewport` + `samples` 画折线，`key_points` 做标注；`clipped>0` 表示有超出视窗的点被裁掉，界面需要说明。
3. 语音优先使用 `browser_fallback` 的 Web Speech API；启用服务端转写后把 `corrections` 展示给学生确认，再走 `/api/conversations` 保存。
4. 教师纠错：教师端“复核”调用 `POST /api/agent/corrections`；学生端用 `GET /api/agent/corrections` 显示“已由教师复核”。

### 仍待 B 模块后续定义（不属于本轮范围）

- 异步任务与长任务进度（`async_tasks` 仍为 false）、诊断任务状态。
- 拍照识别多题切分；数学工具的多变量、积分与级数支持。
- 资源库 `verified` 复核（12 个知识点仍为 false，需课程资料复核后重跑评测）。
- 真实模型、真实视觉与真实语音服务的效果评测（未配置凭据前不得声称已评测）。
