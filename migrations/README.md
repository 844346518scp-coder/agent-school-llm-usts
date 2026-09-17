# SQLite 迁移、备份与恢复

当前版本：0.2，迁移版本号：2。当前仅支持 SQLite；PostgreSQL / pgvector 与多班级在后续阶段实施。

## 升级行为

- 应用在开放接口前调用 `upgrade.py`。全新数据库创建所有表；0.1 旧库先通过 SQLite backup API 备份，再在 `BEGIN EXCLUSIVE` 事务内升级。
- `assignments.status` 默认迁为 `published`；`submissions.version` 默认迁为 1。新增 `questions`、`reviews`、`schema_migrations`。
- 既有 users、sessions、conversations、assignments、submissions 原字段及记录保留；旧作答无反馈，显示待批改。
- reviews 以 submission_id + version 唯一约束保存教师评语、状态、原作答快照及时间。同一版本重新批改会更新该版本评语；学生改答案后，旧版评语保留但不计为当前结果。
- 已有库备份位于原数据库旁，命名如 `demo.before-v2-<唯一标识>.db`；数据库及备份均被 `.gitignore` 排除。备份不是定时备份方案。
- DDL 与版本标记同事务提交；异常回滚并中止启动，保留备份。重复启动验证已登记版本及字段；数据库版本更高或缺字段时拒绝启动。
- `create_all` 只创建新表，不代替旧字段迁移。下一次模型变更必须增加新版本迁移，不能修改版本2并假定已部署的库自动升级。

## 升级步骤

1. 停止旧后端及所有指向同一数据库的写入进程。关闭浏览器不会停止服务；先核对进程归属，再停止本项目后端。首次启动新版前不要同时运行新旧后端。
2. 必要时在数据库副本先验证，使用系统临时目录，避免覆盖原库。
3. 在项目根目录执行 `.venv/Scripts/python.exe -m migrations.upgrade`，或运行 `./start.ps1 -NoBrowser` 由应用启动完成同一迁移。
4. 确认生成备份、服务健康，登录查看原作业与记录。已有版本0.1服务占用8000时，新启动器会明确报错而不自动结束进程。

本轮实际验证了当前 demo.db 的副本迁移、旧字段逐项保留与重复运行，再启动本地服务升级原库。迁移、失败回滚和备份恢复自动化测试位于 `tests/test_migrations.py`。

## 恢复到新路径（保留当前数据库）

停止应用写入后，在项目根目录执行下列命令，把示例备份名替换为实际文件名：

```powershell
.venv/Scripts/python.exe -m migrations.restore backend/demo.before-v2-实际标识.db --output backend/recovered.db
```

工具先以只读方式检查备份完整性，再恢复到**不存在的新路径**并检查恢复结果；拒绝覆盖任何既有文件。此操作不自动替换 demo.db，不删除新数据。

核对 recovered.db 后，可在被忽略的根目录 `.env` 设置 `DATABASE_URL=sqlite:///D:/AI/project/学校-agent项目/backend/recovered.db`，再启动服务。路径需按实际电脑修改。若恢复的是0.1备份，0.2应用会再次执行迁移。恢复前后的代码版本应匹配；如需回退旧代码，必须同时使用对应旧库，不让旧服务写入升级后的库。

没有自动定时备份、跨机器恢复、PostgreSQL 迁移或公网灾备保证；这些属于后续部署阶段。
