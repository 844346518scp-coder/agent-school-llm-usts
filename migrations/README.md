# MVP 数据库初始化

版本 0.1 由 backend/app/platform/database.py 定义表，应用启动时通过 SQLAlchemy `create_all` 创建缺失的表，并幂等初始化两套演示账号和一份示例作业。

表：users、sessions、conversations、assignments、submissions。密码保存 PBKDF2 摘要，session 只保存令牌摘要。已有演示账号、对话与作业不会在重启时被覆盖。

`create_all` 不是表结构升级工具。后续改字段前必须在此目录提交正式迁移方案，并由 C 审核；不能只修改模型后假定旧数据库已升级。

本地默认数据库为 backend/demo.db，已忽略提交；设置 DATABASE_URL 可选择 PostgreSQL，当前 PostgreSQL 驱动已安装，真实 PostgreSQL 服务尚未验证。SQLite 数据不会自动搬迁到 PostgreSQL。
