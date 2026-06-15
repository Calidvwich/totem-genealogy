# 索引设计与性能模式说明

本文说明当前族谱系统的索引设计机制、性能模式如何工作，以及这些索引为什么能提升成员搜索和统计查询性能。

---

## 1. 当前数据访问特点

系统当前数据规模约 10 万级成员，默认生成 10 个族谱，其中一个大族谱约 6 万人。主要高频访问有：

- 按姓名或 ID 模糊搜索成员。
- 在某个族谱内搜索成员。
- 根据父亲 ID 或母亲 ID 查找子女。
- 根据成员向上追溯父母和祖先。
- 统计某个族谱内的性别比例、寿命、早于本代均值成员等。
- 查询配偶/子女、四代后代。

其中最容易变慢的是成员表 `members`。因为它既保存基础成员信息，也保存父母关系：

```text
members(member_id, clan_id, name, gender, birth_year, death_year, father_id, mother_id, generation_num, ...)
```

如果没有索引，很多查询会退化为全表扫描。10 万级数据仍可运行，但搜索、树形图展开、亲属查询和性能实验会明显变慢。

---

## 2. 性能模式的索引

当前性能模式在 `main.py` 中由 `configure_member_indexes(performance_mode)` 控制。

性能模式开启时，系统尝试创建以下索引：

```sql
CREATE INDEX idx_members_clan ON members(clan_id);
CREATE INDEX idx_members_clan_name ON members(clan_id, name);
CREATE INDEX idx_members_father ON members(father_id);
CREATE INDEX idx_members_mother ON members(mother_id);
```

普通模式下，系统会尝试删除这些索引：

```sql
DROP INDEX idx_members_clan;
DROP INDEX idx_members_clan_name;
DROP INDEX idx_members_father;
DROP INDEX idx_members_mother;
```

说明：

- TotemDB 当前环境对 `CREATE INDEX IF NOT EXISTS` 支持不稳定，所以代码使用“尝试创建/删除，忽略已存在或不存在错误”的方式。
- 性能模式主要用于实验对比，不代表生产环境每次搜索都必须反复创建/删除索引。
- 实际系统长期运行时，建议保持性能模式索引存在。

---

## 3. 为什么这些索引有效

### 3.1 `idx_members_clan`

```sql
CREATE INDEX idx_members_clan ON members(clan_id);
```

适用场景：

- 进入某个具体族谱。
- 查询该族谱成员。
- 统计该族谱男女比例。
- 统计该族谱每代寿命。
- 查询该族谱中早于本代平均出生年份的成员。

没有索引时：

- 数据库需要扫描全库成员，再筛选 `clan_id = ?`。

有索引时：

- 数据库可先定位到某个族谱的成员范围，再做后续过滤或聚合。

对 10 个族谱、其中一个 6 万人族谱的场景，`clan_id` 索引可以显著减少小族谱查询的扫描量。

### 3.2 `idx_members_clan_name`

```sql
CREATE INDEX idx_members_clan_name ON members(clan_id, name);
```

适用场景：

- 在某个族谱内按姓名搜索。
- 父母/子女按姓名匹配。
- 统计查询中先输入姓名，再解析成员 ID。

没有索引时：

- `WHERE clan_id = ? AND name = ?` 或类似条件需要扫描较多成员。

有索引时：

- 数据库可以按 `clan_id` 先缩小族谱范围，再按 `name` 定位候选。

注意：

- 当前模糊搜索使用 `LIKE '%关键字%'`，前置通配符不一定能完全利用 B-Tree 的 `name` 部分。
- 但当查询包含 `clan_id` 时，联合索引至少能利用 `clan_id` 前缀缩小扫描范围。
- 对精确姓名匹配，例如重名确认前的候选查询，`idx_members_clan_name` 更有效。

### 3.3 `idx_members_father`

```sql
CREATE INDEX idx_members_father ON members(father_id);
```

适用场景：

- 查询某个成员作为父亲的所有子女。
- 配偶/子女查询。
- 树形图从父节点展开子节点。
- 移除父子关系后检查是否还存在共同子女。
- 四代后代查询的逐层扩展。

没有索引时：

- 每次找子女都需要扫描 `members` 表。

有索引时：

- `WHERE father_id = ?` 可以直接定位子女集合。

### 3.4 `idx_members_mother`

```sql
CREATE INDEX idx_members_mother ON members(mother_id);
```

适用场景与 `idx_members_father` 对称：

- 查询某个成员作为母亲的所有子女。
- 配偶/子女查询。
- 树形图展开。
- 婚姻关系自动维护。
- 四代后代查询。

---

## 4. 成员搜索的性能模式

前端搜索调用：

```text
GET /api/members/search-performance?clan_id=0&q=张_1_1&performance_mode=true
```

后端执行流程：

1. 根据 `performance_mode` 创建或删除成员索引。
2. 使用 `tracemalloc` 开始记录内存峰值。
3. 记录开始时间。
4. 执行成员查询。
5. 返回：
   - 是否成功。
   - 模式。
   - 索引状态。
   - 耗时毫秒。
   - 内存峰值 KB。
   - 结果数量。
   - 前 200 条结果。

普通模式用于对照全表扫描或弱索引场景；性能模式用于观察索引带来的收益。

---

## 5. EXPLAIN 输出机制

前端点击 `EXPLAIN` 后调用：

```text
POST /api/performance/explain
```

请求体示例：

```json
{
  "q": "张_1_1",
  "clan_id": 0,
  "performance_mode": true
}
```

后端会：

1. 按性能模式配置索引。
2. 构造与搜索一致的 SQL。
3. 执行 `EXPLAIN ANALYZE`。
4. 将结果写入：

```text
output/performance-test/YYYYMMDD-HHMMSS.txt
```

文件包括：

- 生成时间。
- 当前模式。
- 索引状态。
- 查询关键字。
- SQL 原文。
- `EXPLAIN ANALYZE` 输出。

---

## 6. 统计查询中的索引收益

### 6.1 配偶/子女查询

接口：

```text
GET /api/query/spouse_children?member_id=100
```

关键访问：

```sql
SELECT *
FROM members
WHERE father_id = 100 OR mother_id = 100;
```

相关索引：

- `idx_members_father`
- `idx_members_mother`

收益：

- 快速找到目标成员的子女。
- 子女记录中另一个父母字段可推导配偶。
- 避免为了找子女扫描全表。

### 6.2 祖先查询

接口：

```text
GET /api/members/{member_id}/ancestors
```

当前实现：

- 后端使用 Python 迭代追溯父母。
- 每一层根据 `member_id` 查找父母，再继续向上。

主要依赖：

- `members.member_id` 主键。

收益：

- 通过主键定位每个父母节点。
- 避免依赖 TotemDB 对递归 CTE 的支持。

说明：

- 父母字段本身是存储在当前成员记录里的，因此“向上查祖先”最关键的是按 `member_id` 快速读取父母记录。
- `father_id/mother_id` 索引主要服务“向下找子女”，不是祖先查询的核心。

### 6.3 四代曾孙查询

接口：

```text
GET /api/query/great_grandchildren?member_id=100
```

当前实现：

- 后端读取成员关系后，以父母关系逐层扩展三次。

相关索引：

- `idx_members_father`
- `idx_members_mother`

收益：

- 每一层都需要找当前一批成员的子女。
- 父母索引能显著减少逐层查找子女的扫描成本。

### 6.4 每代平均寿命

接口：

```text
GET /api/query/longevity?clan_id=1
```

关键过滤：

```sql
WHERE clan_id = 1
```

相关索引：

- `idx_members_clan`

收益：

- 先定位族谱成员，再按 `generation_num` 分组统计。

### 6.5 50 岁以上男性单身成员

接口：

```text
GET /api/query/singles?clan_id=1
```

相关索引：

- `idx_members_clan`
- `idx_members_father`
- `idx_members_mother`

收益：

- `clan_id` 缩小候选范围。
- 判断是否存在子女和配偶关系时，可用父母索引加速。

### 6.6 早于本代平均出生年份

接口：

```text
GET /api/query/early_birth?clan_id=1
```

相关索引：

- `idx_members_clan`

收益：

- 先缩小到目标族谱，再按世代分组计算平均出生年。

---

## 7. 为什么没有建立更多索引

当前没有默认创建 `gender`、`birth_year`、`generation_num` 的单列索引，原因是：

- 这些字段选择性相对较低，单独过滤时收益有限。
- 统计查询通常先按 `clan_id` 缩小范围，再在内存或 SQL 中聚合。
- 过多索引会增加导入和更新成本，尤其是 10 万级批量导入时。
- 当前课程实验重点是对比搜索和亲属关系查询，因此优先索引姓名、族谱、父母关系。

后续如果要进一步优化，可以考虑：

```sql
CREATE INDEX idx_members_clan_generation ON members(clan_id, generation_num);
CREATE INDEX idx_members_clan_gender ON members(clan_id, gender);
CREATE INDEX idx_members_clan_birth ON members(clan_id, birth_year);
```

这些索引更适合持续进行大量统计分析的场景。

---

## 8. 实验建议

建议实验时记录两组结果：

1. 普通模式：
   - 搜索关键字。
   - 耗时。
   - 内存。
   - 结果数量。
   - EXPLAIN 输出文件。

2. 性能模式：
   - 搜索相同关键字。
   - 耗时。
   - 内存。
   - 结果数量。
   - EXPLAIN 输出文件。

推荐测试关键字：

- 大族谱常见姓氏前缀，例如 `张_`。
- 精确姓名，例如 `张_1_1`。
- 不存在的姓名，例如 `不存在成员`。
- 小族谱中的姓名。

观察重点：

- 是否从全表扫描变为索引扫描。
- 查询耗时是否下降。
- 小族谱搜索是否比全库搜索更明显受益。
- 父母/子女、四代后代查询在大族谱中是否稳定。
