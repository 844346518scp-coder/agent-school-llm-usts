# 源码下载与自动启动

## 用户要求与实现

本次目标是下载完整源码文件夹后即可双击启动；之前的独立便携包不能替代这一要求。新版一键启动.cmd仍调用start.ps1，默认执行bootstrap.ps1，自动建立项目私有环境并构建网页，再调用platform/portable.py的--source模式启动后端与同源静态页面。

首次需联网；缓存完整且源码/依赖未变时不再下载安装。无需全局Python、Node或管理员权限；不改变系统PATH。进程内补全系统PowerShell模块路径，兼容被其他Shell影响的PSModulePath。

## 下载与缓存

固定使用Python3.13.13 Windows x64嵌入式ZIP、Node22.23.2 Windows x64 ZIP、pip26.2.1 wheel；下载URL与SHA256均固定在bootstrap.ps1，来源为Python/Node官网及PyPI文件服务。先下载.partial文件，哈希匹配后才解压/使用。版本调整须更新哈希并重新验收；不动态执行网上安装脚本。

.runtime下保存下载、解释器、npm/pip缓存及临时文件。Python依赖按requirements.lock.txt全部版本核验安装到独立哈希目录；嵌入式_pth忽略系统PYTHONPATH/用户包。前端npm ci遵循锁文件及integrity，当前锁文件有npmmirror/CDN下载地址，慢网下需等待。前端源码/配置指纹变化才重新构建，变化失败则不启动旧构建。失败可再次双击重试。

已忽略的环境/缓存/构建目录是生成物，不属于新增维护源码目录；不要提交它们。真实.env、数据库、日志继续被忽略。

## 启动与数据

默认单个FastAPI进程同时提供静态页面与API，优先18080端口；自动模式遇占用或Windows保留端口则换可用端口并记住。显式-Port不可用时报错。目录锁防并发，instance_id核对所属目录，health支持demo/live并包含agent_version标识以区别旧C后端。

源码模式保留.env及DATABASE_URL语义，空值使用backend/demo.db；旧便携模式仍固定包内数据。B集成不新增数据表或迁移版本。升级前停止当前目录旧服务，备份数据，按migrations/README.md执行。自动安装不覆盖.env和数据库。

-SetupOnly仅准备环境；-NoBrowser启动但不打开网页；-Dev使用原先的.venv + 系统Node开发方式，保留8000/5173热更新。出现依赖文件被开发服务占用时需先停止本项目开发服务，不自动终止其他程序。

## 联调范围

tests/check_source.py建立没有.runtime/.venv/node_modules/dist/.env的新源码副本，移除子进程PATH中的Python/Node，设置无效PYTHONHOME/PYTHONPATH，再真实下载、校验、安装、构建。检查C题库/作业/反馈闭环、B演示问答和引用、重启持久化，以及缓存启动无需重新安装；live使用本地假模型服务，不使用真实密钥或外部模型。

验收结果以开发日志为准。本机隔离测试不能替代所有Windows实机；首次网络/代理、机构程序策略、Windows ARM及Mac/Linux仍有边界。普通旧main源码ZIP不会自行获得修复，需发布本次源码修改后下载更新。
