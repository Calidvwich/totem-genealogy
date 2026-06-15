# 用途：记录第一轮代码质量、安全性和数据操作风险审计结论，作为后续小步修复的依据。

# 代码审计报告

## 审计范围

本轮审计只阅读现有代码并新增文档、只读检查脚本，不重构核心业务逻辑，不修改 `main.py`，不修改 `resources/` 和 `resources/defaultpic.jpg`。

已重点阅读：

- `README.md`、`env.md`、`queries.md`
- `init_db.sql`、`verify_dataset.sql`、`import_members.sql`
- `main.py`、`interface.py`
- `generate_data.py`、`load_db.py`、`import.py`、`export.py`、`export_db.py`
- `config/startup/startup.json`、`scripts/start-genealogy.ps1`

## 总体结论

项目已经具备完整的课程项目主链路：FastAPI 页面、Totem 命令行访问、族谱成员管理、婚姻关系、协作者、导入导出和性能测试入口。当前最适合第一轮贡献的方向不是大规模重写，而是补足数据库设计说明、路由映射、只读数据一致性检查和手工测试计划。

主要风险集中在三个方面：

- 数据库 schema 为了兼容 Totem，弱化了外键与级联约束，跨表一致性主要依赖应用代码维护。
- 真实 Totem 访问层通过 `tsql -c` 执行拼接 SQL，虽然有 `sql_literal()` 做基础转义，但仍不是参数化查询模型。
- 部分导入脚本具有清空数据行为，文档中对其影响范围的描述不够一致，容易被误当成普通 smoke test。

## SQL 注入风险

`main.py` 中 `TotemClient.query()` 和 `TotemClient.execute()` 通过 `subprocess.run()` 调用 `tsql -c`，业务 SQL 大量使用 f-string 或 `.format()` 拼接。

已有缓解：

- `main.py`、`import.py`、`export.py` 中均有 `sql_literal()`，会对字符串单引号做转义。
- 多数路径参数由 FastAPI/Pydantic 转成 `int` 后再使用。
- `update_user()`、`update_member()` 的动态字段来自 Pydantic 模型字段，不是直接使用请求 JSON 的任意 key。

剩余风险：

- 当前不是数据库驱动级参数绑定，无法获得参数化查询的完整保护。
- 所有新增 SQL 都需要人工确认是否经过 `sql_literal()` 或已转换为整数。
- `export.py` 中 `export_clans()` 会先把 `clan_ids` 转成 `int`，风险较低；这种模式值得在文档中明确为推荐写法。

后续建议：

- 保持第一轮不改核心逻辑，仅记录风险。
- 若后续 Totem 提供 Python 驱动或安全参数接口，再统一收敛 SQL 执行层。
- 在新增业务 SQL 前增加代码审查清单：所有用户输入必须经过类型转换或 `sql_literal()`。

## 硬编码路径、账号和默认密码

已确认的硬编码配置：

- `main.py`、`load_db.py`、`import.py`、`export.py` 默认使用 `TOTEM_DATABASE=genealogy`、`TOTEM_USER=totem`、`TOTEM_TSQL=/usr/local/totem/bin/tsql`。
- `export_db.py` 默认使用 `/usr/local/totem/bin/totem_dump`。
- `config/startup/startup.json` 包含 WSL 发行版、`/usr/local/totem`、`/mnt/e/totemdb/project`、`app_user=xjz`、端口 `55432` 等本机化配置。
- `interface.py` 登录框默认填入 `admin` 和 `123456`。
- `init_db.sql` 内置 `admin`、`test01` 两个用户及初始密码哈希。

风险判断：

- 这些值更像课程项目本地运行默认值，不是生产密钥；但账号和默认密码说明容易不一致。
- `env.md` 中写了默认账号 `admin / admin`，而界面默认值和导入脚本更像 `admin / 123456`，建议后续统一说明。
- `startup.local.json` 已在 `.gitignore` 中，适合放个人本机路径，这是合理方向。

后续建议：

- 文档明确默认账号只用于本地测试库。
- 保留默认值，但鼓励使用环境变量覆盖。
- 不把真实个人密码或外部服务密钥提交到仓库。

## 数据导入与导出脚本

`generate_data.py`：

- 使用固定随机种子和 Python CSV 生成数据，包含一定的生成后校验。
- 会写入 `genealogies_load.csv`、`members_load.csv`、`marriages_load.csv`，这些生成文件已被 `.gitignore` 覆盖。

`load_db.py`：

- 如果缺少 CSV，会调用 `generate_data.py`。
- 会执行多条删除语句清空 `marriages`、`members`、`collaborations`、`genealogies`。
- 会重置 `admin`、`test01` 密码哈希。

`import.py`：

- `import_generated_data(reset=True)` 会清空族谱相关表再导入生成数据。
- `import_clan_csv()` 会新增一个族谱并导入成员，不清空已有数据。
- 多数异常会抛出到 API 层，由接口转为 HTTP 400。

`export.py` 和 `export_db.py`：

- `export.py` 主要执行 SELECT 并写出 CSV/JSON 到 `output/export`。
- `export_db.py` 调用 `totem_dump` 导出整库。
- `export.py` 对可选 `member_photos` 表读取失败做了容错。

发现的问题：

- `env.md` 说明 `load_db.py` 默认只清空并重新导入 `members` 表中 `clan_id = 1`，但当前实现会清空多张族谱业务表。应在后续文档修正。
- 导入脚本不适合作为 smoke test，必须只在测试库执行。
- `load_db.py` 对 `subprocess.run()` 的 stderr 捕获较少，排错信息不如 `import.py` 完整。

## 异常处理与 demo 回退

`TotemGenealogyService` 继承自 `DemoGenealogyService`，许多真实库操作在捕获普通 `Exception` 后会回退到 demo 数据。

优点：

- 本地没有 Totem 时，页面仍可用于演示。
- 课程展示时降低启动失败概率。

风险：

- 真实库连接或 SQL 错误可能被掩盖，用户以为操作成功但实际使用了内存 demo 数据。
- 对审计和测试而言，需要明确区分 demo 模式与真实 Totem 模式。

后续建议：

- smoke test 中只检查 GET 端点可达，不把 demo 回退等同于真实库成功。
- 手工测试计划中单列真实库检查步骤：确认 `TOTEM_USE_DEMO=0`、数据库名、端口和 `SELECT COUNT(*)`。

## 文件与资源边界

`resources/defaultpic.jpg` 被 README 明确标为不要修改，`.gitignore` 也保留该文件跟踪。本轮未修改该目录。

`main.py` 中成员头像接口在没有数据库头像时读取 `APP_DIR / "resources" / "defaultpic.jpg"`，这是主功能依赖，后续不要随意删除或替换。

## 第一轮建议清单

- 新增数据库设计审计文档，解释为什么实际 schema 没有外键，以及如何用只读 SQL 检查孤儿数据。
- 新增 API 路由映射文档，降低后续维护者理解成本。
- 新增只读 SQL 检查脚本，不改变数据库状态。
- 新增 smoke check Python 脚本，默认只做静态和可选只读 API 检查。
- 后续再考虑修正文档中的默认密码、`load_db.py` 数据影响范围描述，以及真实库异常回退提示。
