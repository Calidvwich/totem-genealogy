# 核心查询与性能实验说明

本文记录当前族谱系统中已经实现的核心查询。项目运行时优先通过 FastAPI 接口调用；SQL 示例用于实验报告、tsql 手工验证和 EXPLAIN 分析。

默认数据库连接：

```bash
/usr/local/totem/bin/tsql -U totem -p 55432 -d genealogy
```

---

## 1. 成员模糊搜索

接口：

```text
GET /api/members/search-performance?clan_id=0&q=张_1_1&performance_mode=false
```

说明：

- `clan_id=0` 表示全库搜索。
- `performance_mode=false` 为普通模式。
- `performance_mode=true` 为性能模式，会尝试启用索引。
- 返回是否成功、耗时、内存、结果数量和前 200 条结果。

SQL 逻辑：

```sql
SELECT member_id, clan_id, name, gender, birth_year, death_year,
       father_id, mother_id, generation_num, bio, id_pic
FROM members
WHERE name LIKE '%张_1_1%'
   OR CAST(member_id AS TEXT) LIKE '%张_1_1%'
ORDER BY clan_id, generation_num, member_id
LIMIT 200;
```

单族谱搜索：

```sql
SELECT member_id, clan_id, name, gender, birth_year, death_year,
       father_id, mother_id, generation_num, bio, id_pic
FROM members
WHERE clan_id = 1
  AND (name LIKE '%张_1_1%' OR CAST(member_id AS TEXT) LIKE '%张_1_1%')
ORDER BY clan_id, generation_num, member_id
LIMIT 200;
```

---

## 2. 成员详情：父母、配偶、子女

接口：

```text
GET /api/members/{member_id}/detail
GET /api/query/spouse_children?member_id={member_id}
```

父母查询：

```sql
SELECT member_id, clan_id, name, gender, birth_year, death_year,
       father_id, mother_id, generation_num, bio, id_pic
FROM members
WHERE member_id IN (
    SELECT father_id FROM members WHERE member_id = 100
    UNION
    SELECT mother_id FROM members WHERE member_id = 100
);
```

子女查询：

```sql
SELECT member_id, clan_id, name, gender, birth_year, death_year,
       father_id, mother_id, generation_num, bio, id_pic
FROM members
WHERE father_id = 100 OR mother_id = 100
ORDER BY birth_year, member_id;
```

配偶查询：

```sql
SELECT DISTINCT s.member_id, s.name, s.gender, s.birth_year, s.death_year
FROM members c
JOIN members s ON s.member_id = CASE
    WHEN c.father_id = 100 THEN c.mother_id
    ELSE c.father_id
END
WHERE c.father_id = 100 OR c.mother_id = 100
ORDER BY s.member_id;
```

系统同时维护 `marriages` 表，手动婚姻管理接口为：

```text
GET    /api/members/{member_id}/marriages
POST   /api/marriages
PUT    /api/marriages/{marriage_id}/divorce
DELETE /api/marriages/{marriage_id}
```

---

## 3. 祖先查询

接口：

```text
GET /api/members/{member_id}/ancestors
```

当前实现说明：

- Totem 对递归 CTE 支持不稳定。
- 系统后端使用 Python 迭代向上查询父母，避免依赖 `WITH RECURSIVE`。
- 返回所有祖先及其距离目标成员的代数。

如果数据库支持递归 CTE，可用以下 SQL 做报告参考：

```sql
WITH RECURSIVE ancestors AS (
    SELECT member_id, name, gender, birth_year, death_year,
           father_id, mother_id, generation_num, 0 AS depth
    FROM members
    WHERE member_id = 100

    UNION ALL

    SELECT m.member_id, m.name, m.gender, m.birth_year, m.death_year,
           m.father_id, m.mother_id, m.generation_num, a.depth + 1
    FROM members m
    JOIN ancestors a ON m.member_id = a.father_id
                     OR m.member_id = a.mother_id
)
SELECT DISTINCT member_id, name, gender, birth_year, death_year,
       generation_num, depth AS generations_above
FROM ancestors
WHERE depth > 0
ORDER BY depth, member_id;
```

---

## 4. 亲缘关系路径查询

接口：

```text
GET /api/members/{source_id}/relationship?target_id={target_id}
```

当前实现说明：

- 后端基于父母边构建无向图。
- 使用 BFS 查找两名成员之间的亲缘路径。
- 前端展示路径节点。

该查询不依赖递归 SQL，适合 Totem 当前环境。

---

## 5. 每代平均寿命

接口：

```text
GET /api/query/longevity?clan_id=1
```

SQL 参考：

```sql
SELECT generation_num,
       AVG(death_year - birth_year) AS avg_lifespan,
       COUNT(*) AS member_count
FROM members
WHERE clan_id = 1
  AND generation_num IS NOT NULL
  AND birth_year IS NOT NULL
  AND death_year IS NOT NULL
GROUP BY generation_num
ORDER BY avg_lifespan DESC;
```

后端实现会忽略缺少年份的数据。

---

## 6. 50 岁以上男性单身成员

接口：

```text
GET /api/query/singles?clan_id=1
```

说明：

- 男性。
- 已知出生年份。
- 未填写死亡年份。
- 当前年份减出生年份大于 50。
- 没有任何子女记录能推导出配偶。

SQL 参考：

```sql
SELECT m.member_id, m.name, m.gender, m.birth_year, m.death_year,
       2026 - m.birth_year AS age
FROM members m
WHERE m.clan_id = 1
  AND m.gender = 'M'
  AND m.birth_year IS NOT NULL
  AND m.death_year IS NULL
  AND 2026 - m.birth_year > 50
  AND NOT EXISTS (
      SELECT 1
      FROM members c
      WHERE (c.father_id = m.member_id AND c.mother_id IS NOT NULL)
         OR (c.mother_id = m.member_id AND c.father_id IS NOT NULL)
  )
ORDER BY m.birth_year, m.member_id
LIMIT 200;
```

---

## 7. 早于本代平均出生年份的成员

接口：

```text
GET /api/query/early_birth?clan_id=1
```

SQL 参考：

```sql
SELECT m.member_id, m.name, m.clan_id, m.generation_num, m.birth_year,
       a.avg_birth_year,
       a.avg_birth_year - m.birth_year AS years_before_avg
FROM members m
JOIN (
    SELECT clan_id, generation_num, AVG(birth_year) AS avg_birth_year
    FROM members
    WHERE clan_id = 1
      AND generation_num IS NOT NULL
      AND birth_year IS NOT NULL
    GROUP BY clan_id, generation_num
) a ON a.clan_id = m.clan_id AND a.generation_num = m.generation_num
WHERE m.birth_year < a.avg_birth_year
ORDER BY m.clan_id, m.generation_num, m.birth_year
LIMIT 300;
```

---

## 8. 第四代后代查询

接口：

```text
GET /api/query/great_grandchildren?member_id=100
GET /api/query/great_grandchildren?name=张_1_1
```

当前实现说明：

- 后端使用 Python 迭代三层子女关系，得到第四代后代。
- 不依赖递归 CTE。

---

## 9. 性别比例统计

接口：

```text
GET /api/dashboard
GET /api/dashboard?clan_id=1
```

SQL 参考：

```sql
SELECT gender, COUNT(*) AS total
FROM members
GROUP BY gender
ORDER BY gender;
```

单族谱：

```sql
SELECT gender, COUNT(*) AS total
FROM members
WHERE clan_id = 1
GROUP BY gender
ORDER BY gender;
```

前端使用 ECharts 扇形图展示全库或当前族谱的男女比例。

---

## 10. 索引与 EXPLAIN

性能模式涉及的索引：

```sql
CREATE INDEX idx_members_clan ON members(clan_id);
CREATE INDEX idx_members_clan_name ON members(clan_id, name);
CREATE INDEX idx_members_father ON members(father_id);
CREATE INDEX idx_members_mother ON members(mother_id);
```

EXPLAIN 接口：

```text
POST /api/performance/explain
```

请求体：

```json
{
  "q": "张_1_1",
  "clan_id": 0,
  "performance_mode": true
}
```

输出位置：

```text
output/performance-test/YYYYMMDD-HHMMSS.txt
```

文件中包含：

- 生成时间。
- 查询模式。
- 索引状态。
- 查询关键字。
- SQL。
- `EXPLAIN ANALYZE` 输出。

---

## 11. 导入导出相关接口

导入：

```text
POST /api/import/clan-csv
POST /api/import/generated
```

导出：

```text
POST /api/export/database
POST /api/export/clans
POST /api/export/members/{member_id}
```

默认输出目录：

```text
output/export/
```

导入上传中转目录：

```text
output/import/
```
