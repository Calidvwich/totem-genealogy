# 任务清单（Totem 版）
# 本文件记录项目所有需求，基于 Totem 对象代理数据库 + WSL 环境

## 0. 环境配置（新增）
- 在 WSL 中安装并启动 Totem 数据库（`totemctl start`）
- 验证 `tsql` 连接成功
- 创建 `genealogy_db` 数据库（`createdb genealogy_db`）
- 确认 Totem 是否支持标准 `CREATE TABLE`（优先）或需改用 `CREATE CLASS`
- 确认 Totem 是否支持递归 CTE（`WITH RECURSIVE`），如不支持则准备替代方案
- 确认 `\COPY` / `LOAD` 导入语法在 Totem 中是否可用

## 1. 应用界面
- 用户登录
- 用户管理
- Dashboard 的男女比例和家族总人数
- 族谱和成员管理：
    - 增删改查成员
    - 可以邀请他人编辑
    - 支持模糊查找
- 树形预览
- 人物祖先查询
- 人物亲缘关系查询：展示亲缘关系通路

## 2. 建模相关
- E-R 图（实体、属性、对应关系）
- 关系模式转换：关系表，范式级别说明
    - users: BCNF
    - genealogies: BCNF
    - members: 3NF
    - collaborations: BCNF
- 约束设计：
    - 主键外键（见 property.md）
    - `CHECK (gender IN ('M', 'F', 'U'))`
    - `CHECK (death_year >= birth_year)`
    - `CHECK (member_id <> father_id AND member_id <> mother_id)`
    - `CHECK (length(trim(user_id)) >= 4)`
- **[Totem 适配]** 确认以上约束语法在 Totem 中是否完全支持

## 3. 数据导入和导出
- 数据生成脚本（`generate_data.py`）
- **[Totem 适配]** 修改 `load_db.py`：将 psycopg2 连接替换为 Totem 对应的 Python 驱动或 `tsql` 命令行调用
- **[Totem 适配]** 验证 `\COPY` 批量导入 CSV 在 Totem 中的语法
- **[Totem 适配]** 修改 `export_db.py`：将 `pg_dump` 替换为 `totem_dump`
- 使用 COPY 将 CSV 数据批量导入数据库 / 导出某分支

## 4. SQL 核心查询
- 基本查询：查询某个人所有的子女和配偶（queries.md 4.1）
- 递归查询：查询某个成员的所有历代祖先（queries.md 4.2）
- 统计分析：统计某个家族中年纪最长（或最长寿）的人（queries.md 4.3）
- 查询所有年龄 > 50（以系统时间为准）的男性单身个体（queries.md 4.4）
- 找出家族中出生年份早于该代平均出生年份的成员（queries.md 4.5）
- **[Totem 适配]** 在 `tsql` 中逐条执行并截图验证查询结果
- **[Totem 适配]** 若 Totem 不支持 `WITH RECURSIVE`，将递归祖先查询改写为迭代存储过程（Totem 支持 PL/pgSQL 风格的存储过程）

## 5. 索引与优化
- 对姓名模糊查询设计索引（`idx_members_clan_name`）
- 对基于父节点 ID 查询子节点设计索引（`idx_members_father`, `idx_members_mother`）
- **[Totem 适配]** 确认 Totem 中 `CREATE INDEX` 语法是否与 PostgreSQL 一致
- 记录有无索引情况下执行四代查询的时间差异
- 提交 `EXPLAIN` 执行计划分析（在 `tsql` 中执行 `EXPLAIN` 语句并截图）

## 6. 实验报告（提交材料）
- E-R 图
- 关系模型及 3NF/BCNF 分析说明
- 索引和约束的设计说明
- 数据生成方法说明（generate_data.py 或手工插入）
- 所用 RDBMS 名称和版本（Totem 1.0，WSL Ubuntu 18.04）
- 每条 SQL 查询语句及在 `tsql` 中执行后的结果截图
- 数据库导出文件（`totem_dump` 导出的 `.sql` 文件）
- 工具源码（如使用自编工具生成数据）