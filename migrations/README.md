# SQLite 迁移、备份与恢复

最后更新：2026-09-19。教师工作空间 v0.3，当前迁移版本号：3。仅支持 SQLite；0.2 B/C集成保持schema v2，本轮账号/班级实现新增v3。PostgreSQL / pgvector仍单独后置。

## 升级行为

- 应用在开放接口前调用 `upgrade.py`。全新库创建schema v3表，不默认创建用户或作业；首次通过setup建立教师。0.1/0.2旧库先使用SQLite backup API备份，再`BEGIN EXCLUSIVE`事务升级。
- 从0.1升级时仍补齐`assignments.status=published`、`submissions.version=1`以及questions/reviews；从v2升级保留既有值。用户新增`active,must_change_password,is_demo,created_by`，作业新增`class_id`，新增`classrooms,class_members,assignment_recipients`。
- 既有用户、会话、问答、题目、作业、作答和反馈保留；无反馈作答仍待批改。旧账号不强制重置，公开student/teacher账号标为演示，请勿据此对外开放服务。
- 每位旧教师建立“历史教学班”，旧学生加入各历史班级；旧非草稿作业保存旧学生收件快照，延续原先全局可见范围。只有一位旧教师时可推定学生账号创建归属；多教师旧库归属不明则保留空值，不擅自赋予任何教师重置/停用该学生账号的权限，但仍可维护本班成员。
- reviews 以 submission_id + version 唯一约束保存教师评语、状态、原作答快照及时间。同一版本重新批改会更新该版本评语；学生改答案后，旧版评语保留但不计为当前结果。
- 本轮旧库备份位于原库旁，命名如`demo.before-v3-<唯一标识>.db`；历史before-v2备份继续保留。数据库及备份被.gitignore排除，备份含账号摘要/会话及学生数据，应与原库同等保护；这不是定时备份方案。
- DDL 与版本标记同事务提交；异常回滚并中止启动，保留备份。重复启动验证已登记版本及字段；数据库版本更高或缺字段时拒绝启动。
- `create_all`只创建新表，不代替字段迁移。v3由版本记录识别，幂等重启不会重复建历史班级或收件快照；后续模型变化应新增版本，不重定义已部署的v3。

## 升级步骤

1. 停止旧后端及所有指向同一数据库的写入进程。关闭浏览器不会停止服务；先核对进程归属，再停止本项目后端。首次启动新版前不要同时运行新旧后端。
2. 先在数据库副本验证，可使用项目被忽略的`.tmp/`，避免覆盖原库。复制前停止写入，或使用SQLite backup API获取一致副本，不能盲目复制正在写入的.db文件。
3. 在项目根目录执行 `.venv/Scripts/python.exe -m migrations.upgrade`，或运行 `./start.ps1 -NoBrowser` 由应用启动完成同一迁移。
4. 确认生成备份、health中`teaching_version=0.3.0,schema_version=3`，查看原班级、作业、收件数量、作答与反馈。启动器检测到同目录旧版本会拒绝复用，不自动结束旧进程；它不能发现所有其他端口/路径的数据库写入者。

0.2阶段曾验证实际demo.db副本并升级原库；不能把该历史结果当成本轮v3验证。本轮测试位于`tests/test_migrations.py`及`tests/test_teacher_migration_v3.py`，执行结果见最新日志；实际用户库是否升级也须以日志为准。

2026-09-19验收事实：早期B状态测试未隔离lifespan，15:54:22触发实际demo.db升级v3，自动生成`backend/demo.before-v3-fa3c72f99b74.db`。当前库与该备份全部原表原列一致，完整性通过；另用该真实v2备份的独立副本复验迁移/备份/幂等通过。测试已增加禁止初始化哨兵，最终81项重跑前后实际库哈希不变。新版服务重启前后全11张表一致，原备份未删除、未回滚覆盖新库。

收尾补强已通过：旧作业`class_id`明确非NULL；多教师旧库升级后，两位教师看到`manageable=false`，修改姓名/停用/重置账号均被拒绝，但各自班级的移出/恢复仍可用。该HTTP回归使用独立临时数据库，未修改实际用户库；当前完整与针对性测试范围分别见开发日志。

## 恢复到新路径（保留当前数据库）

停止应用写入后，在项目根目录执行下列命令，把示例备份名替换为实际文件名：

```powershell
.venv/Scripts/python.exe -m migrations.restore backend/demo.before-v3-实际标识.db --output backend/recovered.db
```

工具先以只读方式检查备份完整性，再恢复到**不存在的新路径**并检查恢复结果；拒绝覆盖任何既有文件。此操作不自动替换 demo.db，不删除新数据。

核对recovered.db后，可在被忽略的根目录.env设置`DATABASE_URL=sqlite:///D:/AI/project/学校-agent项目/backend/recovered.db`，按实际路径调整。恢复旧版本备份后启动v0.3会再迁移；如需回退代码，必须配套对应旧库，不允许旧服务继续写入v3库。恢复时备份以后产生的新数据不会自动合并。

没有自动定时备份、跨机器恢复、PostgreSQL 迁移或公网灾备保证；这些属于后续部署阶段。

本轮先登记账号/班级契约，再新增v3；下一阶段共同授课、角色管理和正式认证仍须先约定历史兼容与迁移。PostgreSQL需要单独实现初始化、迁移、回滚和备份恢复，不能仅改连接串启用。

## 源码自动启动补充（2026-09-18）

start.ps1默认自动准备项目环境并同源启动；原.venv/8000/5173改为-Dev。自动准备后可用`.runtime/python-3.13.13/python.exe -m migrations.upgrade`或`-m migrations.restore`。为保持既有兼容，health的version/agent_version仍为0.2.0，不应据此判断数据版本；本轮新增teaching_version/schema_version明确标识v0.3/v3。
