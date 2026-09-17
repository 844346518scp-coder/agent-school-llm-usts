# 高数学习教育智能体

数伴（SHUBAN）0.1：可运行的本地 MVP，包含学生与教师登录、各自工作台、智能体演示窗口、对话收藏与历史、教师发布作业、学生提交及教师查看作答。真实 AI 尚未接入。

原始素材目录已恢复，本轮读取其中建设计划书确认技术路线：Vue 3、TypeScript、Element Plus、KaTeX、ECharts、FastAPI。正式方案采用 PostgreSQL / pgvector；为免部署即可体验，本版使用 SQLAlchemy + SQLite，保留 PostgreSQL 连接支持。

## 所有人和 AI 的开工入口

开始前完整阅读 [AGENTS.md](AGENTS.md)，其中统一维护协作规范、项目记忆、目录结构、三人边界和 GitHub 上传前密钥确认要求。再阅读 [开发日志](docs/development-log.md)、[架构说明](docs/architecture.md) 和 [接口约定入口](docs/contracts/README.md)。

不同 AI 工具不一定自动加载仓库规则。每次新会话请主动发送以下指令，并确保工具能够读取文件：

> 请先完整、详细阅读项目根目录 AGENTS.md，再阅读 README.md、开发日志最近记录及本任务相关文档。说明当前项目状态和本次修改范围后开始工作。严格执行目录变更事先确认、开发日志与全部文档同步、GitHub 上传前提醒并确认 API 密钥状态的规则。如果无法读取文件，请告诉我，不要假设已经读取。

## 本地安装与启动

**当前电脑已安装依赖，直接双击根目录的 [一键启动.cmd](一键启动.cmd)。** 启动器会启动前后端、等待就绪，然后自动打开默认浏览器。重复点击会复用健康的数伴服务；同时双击只会启动一组服务。启动成功后窗口关闭，服务继续在后台运行；失败则保留窗口显示原因。

首次换到其他电脑，先完成下面的依赖安装，再双击启动器。启动器不会自动下载安装环境或修改系统执行策略；CMD 只为本次 PowerShell 进程设置脚本执行方式。

环境：Node.js 22.12+、Python 3.11+。本次使用 Node 22.12 与 Python 3.11.15 验证。Windows PowerShell 在项目根目录执行：

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements.lock.txt
cd frontend
npm ci
cd ..
./start.ps1
```

入口为 [数伴本地页面](http://127.0.0.1:5173)。start.ps1 使用隐藏后台进程，输出 PID，并逐个等待服务就绪（各最长约 45 秒）；还会检查前端到后端的 API 代理。端口被其他服务占用时报告冲突，不关闭其他程序。若启动失败，查看 backend/server.err.log、frontend/server.err.log 及对应 server.out.log。关闭浏览器不会停止服务；重启电脑会停止后台服务。仅检查 / 启动而不打开浏览器，可在 PowerShell 执行 `./start.ps1 -NoBrowser`。

也可分别在两个终端运行，按 Ctrl+C 停止：

```powershell
# 终端一：项目根目录
.venv/Scripts/python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

```powershell
# 终端二：frontend 目录
npm run dev
```

后端 [健康检查](http://127.0.0.1:8000/api/health)、[接口文档](http://127.0.0.1:8000/docs)。开发页面经 Vite 代理访问 /api，前后端同源。先构建前端，再启动后端时，也可由 FastAPI 在 8000 端口直接提供构建后的页面。

## 文件夹怎么理解

| 位置 | 用途 |
|---|---|
| frontend/src/student | 学生首页与课程探索页面，主要由 A 负责 |
| frontend/src/teacher | 教师首页，主要由 C 负责 |
| frontend/src/shared | 两端共用的登录、智能体窗口、作业、记录、图表、公式、样式和 API 调用 |
| frontend/src/App.vue | 登录状态与页面导航，决定当前显示学生端还是教师端 |
| backend/app/platform | 账号验证、权限、会话、数据库模型与连接 |
| backend/app/teaching | 教师发布作业、学生提交与教师查看的后端逻辑 |
| backend/app/ai | 智能体演示回复、对话记录与收藏；今后 B 接入真实 AI 的主要位置 |
| backend/app/main.py | 后端入口，组装接口、初始化数据库 |
| docs | 架构、开发日志和接口约定，供团队交接与 AI 开工阅读 |
| migrations | 数据库结构变更说明与后续迁移文件，当前只有初始化说明 |
| tests | 自动化测试，检查认证、权限和核心流程 |
| 原始素材 | 原有案例、计划书、图示等参考材料，不参与软件运行 |

根目录的 AGENTS.md 是协作规则和项目记忆，README.md 是使用说明，一键启动.cmd 是双击入口，start.ps1 是实际启动逻辑，.env.example 是配置模板，.gitignore 指定哪些本地文件不上传。

自动生成的目录无需日常编辑：.venv 是 Python 环境，frontend/node_modules 是前端依赖，frontend/dist 是构建结果，.pytest_cache 与 __pycache__ 是缓存。backend/demo.db 是本地账号、会话、对话与作业数据库，**删除会丢失本地记录**；server.out.log / server.err.log 用于排查启动问题。这些运行产物已被忽略，不作为源码提交。

## 演示账号与体验顺序

| 身份 | 账号 | 密码 |
|---|---|---|
| 学生 | student | Student123! |
| 教师 | teacher | Teacher123! |

这些是公开的本地演示凭据，不是外部服务密钥。首次打开显示登录页，选择匹配身份，可点击“填入演示账号”。勾选“记住密码”会使用 HttpOnly Cookie 保留登录七天，不把密码保存到 localStorage；未勾选时为浏览器会话 Cookie，服务端最长八小时。有效会话刷新可继续，退出登录会撤销它。

1. 学生登录 → 数伴智能体 → 点击极限或导数示例 → 发送 → 收藏；刷新后在学习记录、复习收藏中查看。
2. 退出 → 教师登录 → 发布新作业。
3. 退出 → 学生登录 → 我的作业 → 提交答案。
4. 退出 → 教师登录 → 作业管理 → 查看实际作答。

SQLite 默认保存到 backend/demo.db，重启不会清空。公开演示账号仅适合本机测试；暂无注册、重置密码、登录限流和正式账号管理，禁止直接作为公网认证系统使用。

## 当前能力边界

- 智能体使用固定例题和教学示例；未知问题仅保存并说明暂不能回答，不冒充真实模型。课程概念入口不等于完整课程内容。
- 收藏是用户主动标记，不自动判定为错题。图表统计实际提问次数，不虚构掌握度、学习时长或成绩。
- 作业面向一个演示班级；学生提交可在截止当天及之前修改，同一学生同一作业保存一份最新作答。教师只能查看自己发布的作业，学生不能发布作业；个人对话互相隔离。
- OCR、图片上传、语音、RAG、百炼、Tavily、SymPy 校验、pgvector、worker、多班级与教师复核尚未实现；师生招募和组织试用仍为暂定。

## 配置、检查与交接

可将 .env.example 复制为根目录 .env。程序读取 DATABASE_URL 与 COOKIE_SECURE；模型配置仅预留。DATABASE_URL 留空用 SQLite；填写 `postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME` 可选择 PostgreSQL，但本轮未连接真实 PostgreSQL 验证。真实配置不得提交。

```powershell
# 根目录：接口测试（使用系统临时目录中的独立数据库）
.venv/Scripts/python.exe -m pytest tests/test_api.py -q
# frontend 目录：TypeScript 检查及生产构建
npm run build
```

目录与职责以 AGENTS.md 为准。本次依赖解析版本记录在 frontend/package-lock.json、backend/requirements.lock.txt。数据库初始表方案见 migrations/README.md；`create_all` 不承担后续表结构升级。

每次开发后追加日志、同步全部受影响文档和项目记忆。上传 GitHub 前执行 AGENTS.md 中的密钥检查和用户确认。目标仓库为 https://github.com/844346518scp-coder/agent-school-llm-usts 。用户已授权 AI 主动核验秘密凭据后上传；检查范围、限制与执行记录见开发日志。仓库原有 PCL.exe 和 AVIF 图片原样保留，不参与本项目运行。

## 仓库原有说明（原文保留）

# agent-school-llm-usts
dddd
