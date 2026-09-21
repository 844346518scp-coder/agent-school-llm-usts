> 最后更新：2026-09-21。当前默认方案已改为“普通源码下载后自动初始化”，见[source-startup.md](source-startup.md)。本文记录可选便携工具及2026-09-18生成的历史C版ZIP；旧ZIP不含B/C集成，不是当前交付，也不得用来判断main的功能状态。

教师工作空间v0.3/schema v3已以8799cd0上传原C分支；其后的9/20至21教师入口、成员批量操作与章节分组选题已上传C分支，现与main拍照入口整合。本轮没有重建便携ZIP，旧包不含这些功能。下列“演示账号”步骤只适用于该历史ZIP；若用当前源码新打包，空库默认教师建档，演示种子须显式启用，并必须重新执行隔离验收，不能复用旧包结果。

# Windows 免安装测试包

适用：Windows 10/11、Intel/AMD 64 位电脑，普通用户权限，可写的本地目录。暂未验证 Windows ARM、Mac、Linux 或 Windows 7。已验证的`shuban-windows-x64-20260918-083356.zip`冻结于C教师工作流阶段，尚未整合B；当前源码已经完成B/C集成，两者不能混为同一版本。

## 测试者

1. 获取 `shuban-windows-x64-日期时间.zip` **便携测试包**。GitHub 的 Code → Download ZIP 是源码，不含运行环境，不能代替它。
2. 完整解压到较短的可写路径，例如 `D:\Shuban`。中文与空格路径可以使用。不要直接在压缩软件里双击文件，也不要只复制启动文件。
3. 双击 `一键启动.cmd`，浏览器打开 `http://127.0.0.1:18080/`。不需要安装 Python、Node.js、npm、数据库或联网下载依赖，也不需要管理员权限。
4. 学生演示账号 `student` / `Student123!`；教师演示账号 `teacher` / `Teacher123!`。首次启动创建新的演示数据库，发包者的数据不在包内。

数据保存在解压目录的 `backend/demo.db`，日志在 `backend/server.out.log` 和 `backend/server.err.log`。关闭网页不会关闭后端；重复启动复用本目录服务。重启电脑会停止服务。勿删除正在使用的目录或数据库。

默认优先使用18080，并记住成功启动的端口；如端口被其他程序占用或被Windows预留，会自动选择可用端口，以实际打开的网址为准。不会关闭别人的进程。手动指定的端口不可用时明确报错。可在包目录执行 `powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1 -Port 18081` 使用其他端口。`-NoBrowser` 只启动不打开网页。

更新版本请解压至新目录。需要保留数据时，先停止旧后端、备份旧数据库，再按项目迁移说明操作；不要用新的空数据库覆盖旧数据。测试包固定使用本目录 SQLite，不读取系统 DATABASE_URL 作为数据库地址。

此包只在本机开放服务，演示账号不用于公网；不同电脑的数据各自独立。学校的程序白名单或安全策略仍可能限制运行，请保留报错并联系管理员，不要求关闭安全软件。

## 开发者构建

在已安装锁定依赖的 Windows x64 开发电脑执行：

```powershell
.venv/Scripts/python.exe build-portable.py
```

构建器要求 Python 3.11 完整运行时、锁文件对应的 Python 包、已安装前端依赖的 Node.js/npm。先执行 TypeScript 检查和 Vite 构建，然后将 CPython 运行时、标准库、原生 DLL、锁定 Python 包和前端静态文件装入 `dist/` 中的独立目录并生成 ZIP、SHA256 校验文件。

运行时来自构建电脑的 `sys.base_prefix`（本次为 uv 管理的 CPython 3.11.15），并非复制不可移植的 `.venv`。包中通过 `_pth` 隔离系统 Python 与用户扩展；包含 CPython LICENSE、各 Python 包元数据/许可和前端 THIRD-PARTY.json。构建时校验依赖版本并进行打包运行时导入检查。运行时版本和逐文件 SHA256 记录于 `portable-manifest.json`。

按允许列表复制应用源文件，不复制 `.env`、真实数据库、会话、日志、源码附件、Git 历史、PCL.exe、node_modules 或虚拟环境。前端构建产物仍须避免使用 VITE_* 等变量写入真实秘密。测试包是被忽略的构建产物，不加入源码提交；发送或发布前检查包内容。Python/依赖安全升级需重新构建、验证并重新发包。

普通源码现在默认使用一键启动器和项目内`.runtime`自动初始化；需要Vite热更新时才按README使用`.venv`、系统Node和`-Dev`。便携包工具仅作可选测试分发，开发者仍以源码、锁文件和[source-startup.md](source-startup.md)为当前维护依据。

如果在当前集成源码上重新运行构建器，新ZIP会随当前源码包含B/C代码，但2026-09-18旧包的验收结论和SHA256不能沿用。必须重新检查包内版本、依赖许可、秘密凭据排除、隔离启动、重启持久化、端口切换及教师/智能体闭环；发布到GitHub前仍需履行AGENTS.md的上传检查和用户确认。
