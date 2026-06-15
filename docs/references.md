# 用途：记录本次审计参考的内部文件、外部资料链接和参考思路；不复制外部项目代码。

# 参考资料

## 仓库内参考

- `README.md`：项目背景、Totem 工具、资源文件保护要求。
- `env.md`：WSL、Totem、启动、导入和端口配置说明。
- `init_db.sql`：当前真实初始化 schema。
- `queries.md`：PostgreSQL 风格查询与设计参考，不作为 Totem 初始化脚本直接执行。
- `main.py`：FastAPI 路由、权限检查、Totem 访问层和 demo 回退逻辑。
- `generate_data.py`：批量测试数据生成和生成后校验思路。
- `load_db.py`、`import.py`、`export.py`、`export_db.py`：数据导入导出流程。
- `verify_dataset.sql`：已有的基础数据验证 SQL。

## 外部参考链接

- FastAPI 官方文档：https://fastapi.tiangolo.com/
- Pydantic 官方文档：https://docs.pydantic.dev/
- OWASP SQL Injection Prevention Cheat Sheet：https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html
- CWE-89 SQL Injection：https://cwe.mitre.org/data/definitions/89.html
- PostgreSQL 约束文档：https://www.postgresql.org/docs/current/ddl-constraints.html
- PostgreSQL COPY 文档：https://www.postgresql.org/docs/current/sql-copy.html

## Totem 参考思路

- 以课程环境中的 Totem 用户手册和本仓库 `env.md` 为准。
- 命令行工具按项目文档使用 `tsql`、`totemctl`、`totem_dump`。
- 不假设 PostgreSQL 的高级语法在 Totem 中全部可用。
- 对 Totem 未确认支持的能力，优先写成说明或只读校验，不在第一轮直接引入 schema 迁移。

## 本次审计采用的原则

- 不复制外部项目代码。
- 不引入未经许可的第三方代码。
- 不把 PostgreSQL 参考 SQL 直接等同于 Totem 可执行 SQL。
- 对会改数据库的脚本单独标风险，不纳入默认 smoke test。
- 对缺失外键等兼容性取舍，先用只读检查和文档说明补强。
