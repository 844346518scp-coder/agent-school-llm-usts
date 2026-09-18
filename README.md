# 高数学习教育智能体 · 数伴

当前本地集成版本保留 C 的教师题库、草稿/发布/归档、作答版本、人工反馈和教学统计，并合入 B 的模型兼容接口、本地课程检索、引用、步骤反馈和基础诊断。没有配置模型时可以演示使用；模型能力的代码接入不代表已完成真实模型效果验收。

## 下载源码后直接运行（Windows）

1. 下载**包含本次修复的分支**源码 ZIP，完整解压到可写目录，例如 `D:\Shuban`。支持中文和空格路径；不要在压缩软件内直接打开启动文件。
2. 双击根目录 [一键启动.cmd](一键启动.cmd)。**首次需要联网**：脚本自动下载项目专用 Python、Node.js，校验 SHA256，安装锁定依赖并构建网页。可能需要数分钟，请保留窗口等待完成。
3. 浏览器就绪后自动打开。优先使用 `http://127.0.0.1:18080/`；被占用或被 Windows 预留时会自动选择可用端口并记住，以实际打开的网址为准。
4. 此后仍双击同一文件。环境、依赖和源码未变时复用本地结果；演示功能无需联网。真实模型调用需要网络和本地配置。

**无需预先安装 Python、Node.js、npm 或数据库，不需要管理员权限，不修改系统 PATH。** 下载的环境位于被忽略的 `.runtime/`，前端依赖和构建结果分别在 `frontend/node_modules`、`frontend/dist`。这就是普通源码文件夹的自动初始化，无需另取便携包。

自动初始化面向 **Windows 10/11 Intel/AMD 64 位**。Windows ARM、Mac/Linux 未提供此自动安装脚本；学校的应用白名单、PowerShell禁用或网络限制仍需管理员处理。首次完全离线且没有缓存时不能安装环境。

常用参数，在源码根目录执行：

```powershell
# 只准备环境，不启动后端、不打开页面
./start.ps1 -SetupOnly
# 自动准备并运行，不打开浏览器
./start.ps1 -NoBrowser
# 指定端口（被占用时明确报错，不关闭其他进程）
./start.ps1 -Port 18081
```

每个文件夹的安装和启动分别有锁，避免重复双击造成同时安装或重复进程。关闭网页不会结束后端；重启电脑会结束。需要停止时，可在任务管理器按启动输出的后端 PID 核对并结束该项目进程，勿批量结束所有 Python。

## 首次失败怎么排查

- **下载失败/校验失败**：按窗口中的文件和网址检查网络，再次双击重试。已通过校验的下载会复用，未校验的内容不会执行。运行时源为 python.org、nodejs.org；pip源为 files.pythonhosted.org，包安装还需访问 PyPI 和锁文件列出的 npm 下载地址。
- **前端依赖被占用**：先停止这个文件夹正在运行的 Vite/构建进程，再次启动；安装器会尽可能提前检查，不主动关闭其他程序。
- **后端失败**：查看 `backend/server.err.log`；启动失败不等于数据已删除。端口冲突可去掉 `-Port` 自动选择。
- **空间不足**：保持项目盘有足够空间（建议至少2GB）。安装临时文件与npm/pip缓存放在项目 `.runtime/`，避免只依赖C盘空间。
- **旧启动器仍提示手动npm ci**：说明仍在使用旧源码。请重新下载最新main源码并完整解压；旧ZIP不会自动更新。

详细机制、已验证范围和限制见 [源码启动说明](docs/source-startup.md)。

## 演示账号

| 身份 | 账号 | 密码 |
|---|---|---|
| 学生 | student | Student123! |
| 教师 | teacher | Teacher123! |

这些是公开的本地演示凭据，不是正式认证。不要直接开放到公网，也不要使用真实师生隐私。个人对话按账号隔离；教师只能管理自己的题库和作业，不能查看学生私人对话。

## C 教师闭环验收

教师登录→我的题库新建题目（可选私有参考答案、支持公式）→按顺序选题生成草稿→完善章节/题干/日期并发布→学生登录提交→教师人工评语并标记待改进/已完成→学生查看并修改→教师复核新版→归档。

空草稿可保存但不可发布；已发布题干锁定，可以延期或复制新草稿。参考答案不进入学生响应。修改作答生成新版本，旧反馈保留但不沿用结论；归档只读。统计按真实提交和人工反馈计算，默认排除草稿/归档，不推断学习效果。

## B 智能体模式与边界

可将 `.env.example` 复制为根目录 `.env`，填写自己的配置。真实密钥只保存在本地，禁止提交。

- `AGENT_MODE=auto`：配置 `MODEL_BASE_URL`、`MODEL_API_KEY`、`MODEL_NAME` 后使用模型，否则演示；`demo` 明确禁止模型调用，含识别接口。`live` 缺配置时仍如实回到演示。
- 兼容 Chat Completions；`MODEL_BASE_URL` 可为服务的 `/v1` 地址或完整 `/chat/completions`。可选 `MODEL_VISION_NAME` 指定视觉模型。
- 问答页面和历史按每条回复显示模型/演示来源，展示检索引用与待复核状态。调用失败时明确降级，提示随回复保存。原有历史继续兼容读取。
- 模型网络超时默认30秒，配置限制为1–60秒；前端AI请求等待90秒。异常不会自动重试，接收失败应先查历史，避免重复保存。
- 本地检索是内置课程片段的BM25，资料仍待课程复核；不是已完成的课程上传、向量库或pgvector。
- 步骤/诊断中的关键词只用于生成候选与自检提示，不能凭关键词确定学生答错或推断知识掌握。规则步骤反馈统一为`unclear`。
- B的流式问答、识别、诊断和步骤反馈保留后端接口，当前页面主要接入普通问答与引用；识别等页面入口后续完成。识别结果必须确认，不能直接作为已核实题干。
- 长期记忆、异步任务、语音、自动评分、正式账号、多班级、PostgreSQL与公网部署尚未完成。师生试用及效果验证仍为暂定。

## 数据与更新

数据保存在 `backend/demo.db`，复制源码不会复制发包者的数据。源码模式遵循 `.env` / `DATABASE_URL`，留空默认SQLite；当前迁移仅支持SQLite。数据版本保持2，B集成未改变数据库结构。旧0.1库升级先备份、事务迁移失败则不启动，见 [迁移与恢复](migrations/README.md)。

更新源码前停止本文件夹服务并备份数据库；保留本地 `.env` 和 `backend/demo.db`。不要把一个空数据库覆盖旧数据。启动器根据后端锁文件、前端锁文件和源码指纹决定重装/重建。已安装缓存可复用，依赖变更需要联网。其他电脑各自存储本地数据，尚无云端同步。

## 开发者运行与检查

若需要Vite热更新，可自行准备Node.js22.12+和Python3.11+：

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r backend/requirements.lock.txt
cd frontend
npm ci
cd ..
./start.ps1 -Dev
```

开发模式使用8000/5173，并检查已集成B的健康标识，避免误复用旧版后端。手动运行后端：`.venv/Scripts/python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`；前端在frontend运行`npm run dev`。自动模式使用构建页面与同源API，无需常驻Vite。

```powershell
# 使用隔离测试数据库，不操作实际demo.db
.venv/Scripts/python.exe -m pytest tests -q
# 完整源码冷启动验收（需要网络，耗时较长）
.venv/Scripts/python.exe tests/check_source.py
# TypeScript及生产构建
cd frontend
npm run build
```

原先的 [便携包工具](docs/portable-windows.md)保留为可选历史方案，不再作为下载源码后的必需步骤；旧C版便携ZIP不包含此次B/C集成。

## 协作入口

所有人及AI开始工作前完整阅读 [AGENTS.md](AGENTS.md)，再读 [开发日志](docs/development-log.md)、[架构](docs/architecture.md)、[接口](docs/contracts/README.md)。目录职责、迁移、文档同步及上传前密钥确认要求以AGENTS.md为准。本次集成已更新`codex/c-local-teaching`，并通过[PR #2](https://github.com/844346518scp-coder/agent-school-llm-usts/pull/2)合入`main`；下载最新main即可获得修复。

项目仓库：https://github.com/844346518scp-coder/agent-school-llm-usts 。历史原始材料保留原文；PCL.exe的远端删除在本次集成中保留。

## 仓库原有说明（原文保留）

# agent-school-llm-usts
dddd
