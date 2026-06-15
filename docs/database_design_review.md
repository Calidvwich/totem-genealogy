# 用途：审计 Totem 族谱数据库表结构、约束设计和与 PostgreSQL 参考 SQL 的差异。

# 数据库设计审计

## 数据库模型概览

当前实际初始化脚本为 `init_db.sql`，包含 6 张表：

- `users`：系统用户与密码哈希。
- `genealogies`：族谱主表。
- `collaborations`：用户与族谱的协作关系。
- `members`：族谱成员。
- `marriages`：婚姻关系。
- `member_photos`：成员头像二进制内容的 base64 存储。

`queries.md` 更像 PostgreSQL 参考草案，包含 `SERIAL`、`CREATE TABLE IF NOT EXISTS`、`REFERENCES`、递归 CTE、`generate_series` 等写法。实际 Totem 初始化以 `init_db.sql` 为准。

## 表结构与约束

### users

已定义：

- `id INTEGER PRIMARY KEY`
- `user_id VARCHAR(20) UNIQUE NOT NULL`
- `password_hash VARCHAR(255) NOT NULL`
- `username VARCHAR(50)`
- `created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
- `chk_users_user_id_len` 要求账号 trim 后长度至少 4

评价：

- 主键、唯一性和密码哈希非空约束合理。
- `username` 可为空，适合作为展示名。
- 默认种子用户方便本地演示，但默认账号密码应只用于测试库。

### genealogies

已定义：

- `clan_id INTEGER PRIMARY KEY`
- `title VARCHAR(100) NOT NULL`
- `surname VARCHAR(20)`
- `revised_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
- `creator_id INTEGER`

评价：

- 主键与标题非空合理。
- `creator_id` 没有外键，允许出现创建者不存在的孤儿引用。
- 如果 Totem 后续能稳定支持外键，可考虑 `creator_id REFERENCES users(id)`；当前先通过只读检查发现异常。

### collaborations

已定义：

- `clan_id INTEGER`
- `user_id INTEGER`
- `PRIMARY KEY (clan_id, user_id)`
- `idx_collaborations_user ON collaborations(user_id)`

评价：

- 联合主键适合表达一个用户对一个族谱最多一条协作关系。
- 没有外键，可能出现不存在的 `clan_id` 或 `user_id`。
- 在某些数据库中主键隐含非空；考虑到 Totem 兼容性，建议用只读 SQL 检查空值和孤儿引用。

### members

已定义：

- `member_id BIGINT PRIMARY KEY`
- `clan_id INTEGER`
- `name VARCHAR(50) NOT NULL`
- `gender CHAR(1) DEFAULT 'U'`
- `birth_year INTEGER`
- `death_year INTEGER`
- `father_id BIGINT`
- `mother_id BIGINT`
- `generation_num INTEGER`
- `bio TEXT`
- `id_pic TEXT`
- `chk_members_gender` 限定 `M/F/U`
- `chk_members_birth_death` 要求死亡年份不早于出生年份
- `chk_members_not_own_parent` 禁止父母字段指向自己

评价：

- 成员主键和姓名非空合理。
- `gender` 增加 `U` 能兼容未知性别，比 `queries.md` 的 `M/F` 更宽松。
- `clan_id`、`father_id`、`mother_id` 没有外键，存在孤儿族谱、孤儿父母、跨族谱父母的潜在风险。
- `generation_num` 可为空，便于导入不完整数据，但树形展示和排序会更依赖应用层处理。
- 成员姓名没有唯一约束是合理的，同名成员在族谱中可能真实存在。

### marriages

已定义：

- `marriage_id INTEGER PRIMARY KEY`
- `clan_id INTEGER`
- `spouse_a_id BIGINT`
- `spouse_b_id BIGINT`
- `marry_year INTEGER`
- `divorce_year INTEGER`
- `chk_marriages_distinct_spouses`
- `chk_marriages_year_order`

评价：

- 主键合理，年份顺序检查必要。
- `spouse_a_id`、`spouse_b_id` 没有非空和外键，可能出现缺少配偶或配偶不存在。
- 数据库层没有唯一约束来防止同一对成员重复登记；应用层已有部分检查，但外部导入仍可能绕过。
- 当前应用中部分父母关系会自动推断婚姻关系，建议用只读检查发现重复配偶、孤儿配偶和跨族谱配偶。

### member_photos

已定义：

- `photo_sha256 VARCHAR(64) PRIMARY KEY`
- `content_type VARCHAR(100) NOT NULL`
- `content_base64 TEXT NOT NULL`
- `created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
- `updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`

评价：

- 以内容哈希作为主键可以去重。
- `members.id_pic` 没有外键指向 `member_photos.photo_sha256`，可能出现成员引用不存在图片。
- base64 存库适合课程项目简化部署；如果图片量很大，后续可评估文件对象存储或资源目录策略。

## Totem 与 PostgreSQL 差异

项目文档已经提到以下差异：

- 使用 `tsql`，不是 `psql`。
- 使用 `totemctl` 管理服务。
- 使用 `totem_dump` 备份。
- 当前 Totem 版本对 `CREATE TABLE IF NOT EXISTS`、部分内联外键语法、`SERIAL`、`generate_series`、递归 CTE 的支持需要谨慎验证。
- 当前 `\COPY` 元命令语法使用 `WITH CSV NULL ''`，不是 README 早期示例中的 PostgreSQL 风格 `WITH (FORMAT CSV, NULL '')`。

审计建议：

- `init_db.sql` 作为真实可执行 schema。
- `queries.md` 标为 PostgreSQL 参考思路，不应直接作为 Totem 初始化脚本执行。
- 后续文档中把 Totem 已验证写法和 PostgreSQL 参考写法分栏说明。

## 缺失或弱化的数据库约束

考虑 Totem 兼容性，当前弱化了以下约束：

- `genealogies.creator_id -> users.id`
- `collaborations.clan_id -> genealogies.clan_id`
- `collaborations.user_id -> users.id`
- `members.clan_id -> genealogies.clan_id`
- `members.father_id -> members.member_id`
- `members.mother_id -> members.member_id`
- `members.id_pic -> member_photos.photo_sha256`
- `marriages.clan_id -> genealogies.clan_id`
- `marriages.spouse_a_id -> members.member_id`
- `marriages.spouse_b_id -> members.member_id`

这些约束不一定要在第一轮强行加回数据库层，因为可能破坏 Totem 运行兼容性。更稳妥的第一步是新增 `scripts/schema_readonly_check.sql`，定期读取检查孤儿引用和不一致数据。

## 建议的数据一致性检查

本轮新增的只读 SQL 应覆盖：

- 表行数概览。
- 重复用户账号。
- 族谱创建者不存在。
- 协作关系引用不存在的用户或族谱。
- 成员引用不存在的族谱、父亲、母亲。
- 父亲性别不是 `M`、母亲性别不是 `F`。
- 成员出生死亡年份顺序异常。
- 父母与子女年份明显矛盾。
- 婚姻配偶不存在、配偶相同、年份顺序异常。
- 成员头像 hash 引用不存在的图片记录。

## 后续设计建议

- 保持 `init_db.sql` 可在当前 Totem 环境执行，不在第一轮加入未经验证的外键语法。
- 对真实库导入前后运行只读一致性检查。
- 在课程报告中说明：出于 Totem 兼容性考虑，部分关系完整性由应用层和审计脚本共同保证。
- 若后续确认 Totem 外键稳定，再单独提交 schema 迁移方案和回滚方案。
