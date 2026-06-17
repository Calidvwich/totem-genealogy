# 功能 SQL 与对象代理设计

本文记录当前族谱系统的主要功能 SQL。项目采用“业务表 + 对象类 + Select 代理类”的结构：

- `members`、`marriages` 等普通表保存完整业务数据。
- `objects`、`object_proxies` 保存稳定对象身份，便于把用户、族谱、成员、婚姻统一抽象为对象。
- `member_objects`、`marriage_objects` 是 Totem `CREATE CLASS` 对象类。
- `father_down_edges`、`spouse_a_edges` 等是 `CREATE SELECTDEPUTYCLASS` 代理类，用于表达父子、母子、配偶、成员角色等常用关系。

TotemDB 的 `CREATE SELECTDEPUTYCLASS` 不能直接基于普通 `CREATE TABLE` 表，也不允许在定义中使用 `UNION`、聚合函数等复杂操作。因此本项目把“可复用关系语义”做成代理类，把聚合统计和路径搜索放在查询层或服务层完成。

默认连接：

```bash
/usr/local/totem/bin/tsql -U totem -p 55432 -d genealogy
```

## 1. 对象类与 Select 代理类

成员对象类：

```sql
CREATE CLASS member_objects (
    member_id BIGINT,
    clan_id INTEGER,
    name VARCHAR(50),
    gender CHAR(1),
    birth_year INTEGER,
    death_year INTEGER,
    father_id BIGINT,
    mother_id BIGINT,
    generation_num INTEGER
);
```

婚姻对象类：

```sql
CREATE CLASS marriage_objects (
    marriage_id INTEGER,
    clan_id INTEGER,
    spouse_a_id BIGINT,
    spouse_b_id BIGINT,
    marry_year INTEGER,
    divorce_year INTEGER
);
```

父子、母子向下代理：

```sql
CREATE SELECTDEPUTYCLASS father_down_edges AS (
    SELECT c.clan_id,
           c.father_id AS from_member_id,
           c.member_id AS to_member_id,
           c.birth_year AS child_birth_year,
           c.generation_num AS child_generation
    FROM member_objects AS c
    WHERE c.father_id IS NOT NULL
);

CREATE SELECTDEPUTYCLASS mother_down_edges AS (
    SELECT c.clan_id,
           c.mother_id AS from_member_id,
           c.member_id AS to_member_id,
           c.birth_year AS child_birth_year,
           c.generation_num AS child_generation
    FROM member_objects AS c
    WHERE c.mother_id IS NOT NULL
);
```

子女向父母代理：

```sql
CREATE SELECTDEPUTYCLASS father_up_edges AS (
    SELECT c.clan_id,
           c.member_id AS from_member_id,
           c.father_id AS to_member_id,
           c.generation_num AS child_generation
    FROM member_objects AS c
    WHERE c.father_id IS NOT NULL
);

CREATE SELECTDEPUTYCLASS mother_up_edges AS (
    SELECT c.clan_id,
           c.member_id AS from_member_id,
           c.mother_id AS to_member_id,
           c.generation_num AS child_generation
    FROM member_objects AS c
    WHERE c.mother_id IS NOT NULL
);
```

配偶双向代理：

```sql
CREATE SELECTDEPUTYCLASS spouse_a_edges AS (
    SELECT marriage_id,
           clan_id,
           spouse_a_id AS from_member_id,
           spouse_b_id AS to_member_id,
           marry_year,
           divorce_year
    FROM marriage_objects
    WHERE spouse_a_id IS NOT NULL
      AND spouse_b_id IS NOT NULL
);

CREATE SELECTDEPUTYCLASS spouse_b_edges AS (
    SELECT marriage_id,
           clan_id,
           spouse_b_id AS from_member_id,
           spouse_a_id AS to_member_id,
           marry_year,
           divorce_year
    FROM marriage_objects
    WHERE spouse_a_id IS NOT NULL
      AND spouse_b_id IS NOT NULL
);
```

角色代理：

```sql
CREATE SELECTDEPUTYCLASS male_50_plus AS (
    SELECT m.member_id,
           m.clan_id,
           m.name,
           m.gender,
           m.birth_year,
           m.death_year,
           m.generation_num,
           (EXTRACT(YEAR FROM current_date) - m.birth_year) AS age
    FROM member_objects AS m
    WHERE m.gender = 'M'
      AND m.birth_year IS NOT NULL
      AND m.death_year IS NULL
      AND (EXTRACT(YEAR FROM current_date) - m.birth_year) > 50
);

CREATE SELECTDEPUTYCLASS known_lifespan_members AS (
    SELECT m.member_id,
           m.clan_id,
           m.name,
           m.gender,
           m.birth_year,
           m.death_year,
           m.generation_num,
           (m.death_year - m.birth_year) AS lifespan
    FROM member_objects AS m
    WHERE m.birth_year IS NOT NULL
      AND m.death_year IS NOT NULL
);
```

## 2. 数据导入后的对象同步

导入 JSON、CSV 或生成数据后，需要把普通业务表同步到对象类：

```sql
DELETE FROM marriage_objects;
DELETE FROM member_objects;

INSERT INTO member_objects(member_id, clan_id, name, gender, birth_year,
                           death_year, father_id, mother_id, generation_num)
SELECT member_id, clan_id, name, gender, birth_year,
       death_year, father_id, mother_id, generation_num
FROM members;

INSERT INTO marriage_objects(marriage_id, clan_id, spouse_a_id, spouse_b_id,
                             marry_year, divorce_year)
SELECT marriage_id, clan_id, spouse_a_id, spouse_b_id, marry_year, divorce_year
FROM marriages;
```

`import.py` 已在 `restore`、`generated`、`csv` 三个入口自动执行同步。

## 3. 成员搜索

接口：

```text
GET /api/members/search-performance?clan_id=0&q=张_1_1&performance_mode=true
```

普通模式使用兼容性最高的模糊匹配：

```sql
SELECT member_id, clan_id, name, gender, birth_year, death_year,
       father_id, mother_id, generation_num, bio, id_pic
FROM members
WHERE name LIKE '%张_1_1%'
   OR CAST(member_id AS TEXT) LIKE '%张_1_1%'
ORDER BY clan_id, generation_num, member_id
LIMIT 200;
```

性能模式先启用索引，再用范围匹配优化“前缀式姓名”查询：

```sql
CREATE INDEX idx_members_name ON members(name);
CREATE INDEX idx_members_clan_name ON members(clan_id, name);
CREATE INDEX idx_members_member_id ON members(member_id);

SELECT member_id, clan_id, name, gender, birth_year, death_year,
       father_id, mother_id, generation_num, bio, id_pic
FROM members
WHERE clan_id = 1
  AND name >= '张_1_1'
  AND name <  '张_1_2'
ORDER BY clan_id, generation_num, member_id
LIMIT 200;
```

搜索返回“是否成功、耗时、内存、结果数”。结果数为 0 时前端显示搜索失败。

## 4. 成员详情

成员主体信息：

```sql
SELECT member_id, clan_id, name, gender, birth_year, death_year,
       father_id, mother_id, generation_num, bio, id_pic
FROM members
WHERE member_id = 100;
```

父母信息使用向上代理：

```sql
SELECT p.member_id, p.name, p.gender, p.birth_year, p.death_year
FROM father_up_edges AS e
JOIN members AS p ON p.member_id = e.to_member_id
WHERE e.from_member_id = 100
UNION
SELECT p.member_id, p.name, p.gender, p.birth_year, p.death_year
FROM mother_up_edges AS e
JOIN members AS p ON p.member_id = e.to_member_id
WHERE e.from_member_id = 100;
```

照片信息：

```sql
SELECT photo_sha256, content_type, content_base64, updated_at
FROM member_photos
WHERE photo_sha256 = (
    SELECT id_pic FROM members WHERE member_id = 100
);
```

若 `id_pic` 为空或照片不存在，前端显示 `resources/defaultpic.jpg`。

## 5. 配偶与子女

接口：

```text
GET /api/query/spouse_children?member_id=100
GET /api/query/spouse_children?name=张_1_1
```

姓名入口先解析成员。若重名，返回候选项并要求补充 `member_id`：

```sql
SELECT member_id, clan_id, name, gender, birth_year, death_year, generation_num
FROM members
WHERE name = '张_1_1'
ORDER BY clan_id, generation_num, member_id
LIMIT 20;
```

配偶查询使用双向配偶代理：

```sql
SELECT m.member_id, m.name, m.gender, m.birth_year, m.death_year,
       e.marriage_id, e.marry_year, e.divorce_year
FROM spouse_a_edges AS e
JOIN members AS m ON m.member_id = e.to_member_id
WHERE e.from_member_id = 100
UNION
SELECT m.member_id, m.name, m.gender, m.birth_year, m.death_year,
       e.marriage_id, e.marry_year, e.divorce_year
FROM spouse_b_edges AS e
JOIN members AS m ON m.member_id = e.to_member_id
WHERE e.from_member_id = 100
ORDER BY member_id;
```

子女查询使用父子、母子代理：

```sql
SELECT c.member_id, c.name, c.gender, c.birth_year, c.death_year,
       c.generation_num, e.child_birth_year
FROM father_down_edges AS e
JOIN members AS c ON c.member_id = e.to_member_id
WHERE e.from_member_id = 100
UNION
SELECT c.member_id, c.name, c.gender, c.birth_year, c.death_year,
       c.generation_num, e.child_birth_year
FROM mother_down_edges AS e
JOIN members AS c ON c.member_id = e.to_member_id
WHERE e.from_member_id = 100
ORDER BY birth_year, member_id;
```

## 6. 父母校验与婚姻维护

新增或编辑成员父母时，系统先按姓名解析父母。若同名，则要求输入具体 ID。父亲必须为男，母亲必须为女：

```sql
SELECT member_id, clan_id, name, gender, birth_year, death_year
FROM members
WHERE name = '张_2_10'
ORDER BY clan_id, generation_num, member_id;
```

保存孩子关系后，若父母同时存在且没有对应婚姻，则自动补婚姻：

```sql
INSERT INTO marriages(marriage_id, clan_id, spouse_a_id, spouse_b_id,
                      marry_year, divorce_year)
SELECT next_id, child.clan_id, child.father_id, child.mother_id,
       inferred_marry_year, NULL
FROM members AS child
WHERE child.member_id = 100
  AND child.father_id IS NOT NULL
  AND child.mother_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM marriages AS m
      WHERE m.clan_id = child.clan_id
        AND (
            (m.spouse_a_id = child.father_id AND m.spouse_b_id = child.mother_id)
            OR
            (m.spouse_a_id = child.mother_id AND m.spouse_b_id = child.father_id)
        )
  );
```

移除孩子关系后，若这对父母没有任何共同孩子，则删除对应婚姻：

```sql
DELETE FROM marriages
WHERE clan_id = 1
  AND (
      (spouse_a_id = 10 AND spouse_b_id = 11)
      OR
      (spouse_a_id = 11 AND spouse_b_id = 10)
  )
  AND NOT EXISTS (
      SELECT 1 FROM members AS c
      WHERE c.clan_id = 1
        AND c.father_id = 10
        AND c.mother_id = 11
  );
```

修改完成后，同步对象类：

```sql
DELETE FROM marriage_objects;
DELETE FROM member_objects;
INSERT INTO member_objects(...) SELECT ... FROM members;
INSERT INTO marriage_objects(...) SELECT ... FROM marriages;
```

## 7. 祖先查询

接口：

```text
GET /api/query/ancestors?member_id=100
GET /api/query/ancestors?name=张_1_1
```

系统通过 `father_up_edges`、`mother_up_edges` 逐层向上查找。单层 SQL：

```sql
SELECT p.member_id, p.clan_id, p.name, p.gender, p.birth_year, p.death_year,
       p.father_id, p.mother_id, p.generation_num
FROM father_up_edges AS e
JOIN members AS p ON p.member_id = e.to_member_id
WHERE e.from_member_id = 100
UNION
SELECT p.member_id, p.clan_id, p.name, p.gender, p.birth_year, p.death_year,
       p.father_id, p.mother_id, p.generation_num
FROM mother_up_edges AS e
JOIN members AS p ON p.member_id = e.to_member_id
WHERE e.from_member_id = 100;
```

采用服务层迭代而不是递归 SQL，是为了避开当前 Totem 环境中递归 CTE 兼容性不稳定的问题。

## 8. 亲缘路径查询

接口：

```text
GET /api/members/{source_id}/relationship?target_id={target_id}
```

后端用代理边构建图：

```sql
SELECT from_member_id, to_member_id, 'father' AS edge_type
FROM father_down_edges
UNION ALL
SELECT from_member_id, to_member_id, 'mother' AS edge_type
FROM mother_down_edges
UNION ALL
SELECT from_member_id, to_member_id, 'spouse' AS edge_type
FROM spouse_a_edges
UNION ALL
SELECT from_member_id, to_member_id, 'spouse' AS edge_type
FROM spouse_b_edges;
```

随后服务层使用 BFS 计算两名成员之间的最短亲缘路径。

## 9. 每代平均寿命

接口：

```text
GET /api/query/longevity?clan_id=1
```

`known_lifespan_members` 先代理出“可计算寿命”的成员，聚合在查询层完成：

```sql
SELECT generation_num,
       AVG(lifespan) AS avg_lifespan,
       COUNT(*) AS member_count
FROM known_lifespan_members
WHERE clan_id = 1
  AND generation_num IS NOT NULL
GROUP BY generation_num
ORDER BY avg_lifespan DESC;
```

## 10. 50 岁以上单身男性

接口：

```text
GET /api/query/singles?clan_id=1
```

`male_50_plus` 代理出候选角色，再排除所有存在配偶边的人：

```sql
SELECT m.member_id, m.clan_id, m.name, m.birth_year, m.age
FROM male_50_plus AS m
WHERE m.clan_id = 1
  AND NOT EXISTS (
      SELECT 1 FROM spouse_a_edges AS e
      WHERE e.from_member_id = m.member_id
  )
  AND NOT EXISTS (
      SELECT 1 FROM spouse_b_edges AS e
      WHERE e.from_member_id = m.member_id
  )
ORDER BY m.birth_year, m.member_id
LIMIT 200;
```

## 11. 早于本代平均出生年份

接口：

```text
GET /api/query/early_birth?clan_id=1
```

聚合不能放进 Select 代理定义，所以在查询层使用 `member_objects`：

```sql
SELECT m.member_id, m.name, m.clan_id, m.generation_num, m.birth_year,
       a.avg_birth_year,
       a.avg_birth_year - m.birth_year AS years_before_avg
FROM member_objects AS m
JOIN (
    SELECT clan_id, generation_num, AVG(birth_year) AS avg_birth_year
    FROM member_objects
    WHERE clan_id = 1
      AND generation_num IS NOT NULL
      AND birth_year IS NOT NULL
    GROUP BY clan_id, generation_num
) AS a ON a.clan_id = m.clan_id
      AND a.generation_num = m.generation_num
WHERE m.birth_year < a.avg_birth_year
ORDER BY m.clan_id, m.generation_num, m.birth_year
LIMIT 300;
```

## 12. 四代曾孙查询

接口：

```text
GET /api/query/great_grandchildren?member_id=100
GET /api/query/great_grandchildren?name=张_1_1
```

姓名入口同样先解析重名。四代查询使用父子/母子向下代理逐层展开。单层展开 SQL：

```sql
SELECT c.member_id, c.clan_id, c.name, c.gender, c.birth_year, c.death_year,
       c.father_id, c.mother_id, c.generation_num
FROM father_down_edges AS e
JOIN members AS c ON c.member_id = e.to_member_id
WHERE e.from_member_id = 100
UNION
SELECT c.member_id, c.clan_id, c.name, c.gender, c.birth_year, c.death_year,
       c.father_id, c.mother_id, c.generation_num
FROM mother_down_edges AS e
JOIN members AS c ON c.member_id = e.to_member_id
WHERE e.from_member_id = 100;
```

服务层执行三次展开，得到第四代后代。

## 13. 性别比例统计

接口：

```text
GET /api/dashboard
GET /api/dashboard?clan_id=1
```

全库统计：

```sql
SELECT
    (SELECT COUNT(*) FROM male_members) AS male_count,
    (SELECT COUNT(*) FROM female_members) AS female_count,
    (SELECT COUNT(*) FROM member_objects WHERE gender = 'U') AS unknown_count,
    (SELECT COUNT(*) FROM member_objects) AS total_count;
```

单族谱统计：

```sql
SELECT
    (SELECT COUNT(*) FROM male_members WHERE clan_id = 1) AS male_count,
    (SELECT COUNT(*) FROM female_members WHERE clan_id = 1) AS female_count,
    (SELECT COUNT(*) FROM member_objects WHERE clan_id = 1 AND gender = 'U') AS unknown_count,
    (SELECT COUNT(*) FROM member_objects WHERE clan_id = 1) AS total_count;
```

## 14. 权限与用户管理

用户、登录、协作权限属于系统管理数据，不属于族谱成员关系，因此仍使用普通表：

```sql
SELECT id, user_id, username, created_at
FROM users
WHERE user_id = 'admin';
```

管理员检索用户：

```sql
SELECT id, user_id, username, created_at
FROM users
WHERE user_id LIKE '%test%'
   OR username LIKE '%test%'
ORDER BY id
LIMIT 200;
```

授予族谱编辑权限：

```sql
INSERT INTO collaborations(clan_id, user_id)
SELECT 1, id
FROM users
WHERE user_id = 'test01'
  AND NOT EXISTS (
      SELECT 1 FROM collaborations
      WHERE clan_id = 1 AND user_id = users.id
  );
```

取消族谱编辑权限：

```sql
DELETE FROM collaborations
WHERE clan_id = 1
  AND user_id = (
      SELECT id FROM users WHERE user_id = 'test01'
  );
```

## 15. 导入导出

导出整个数据库或某个族谱时会生成 `import_bundle.json`，该文件可以被 `import.py restore` 直接导回：

```bash
python3 import.py restore output/export/xxx/import_bundle.json --reset
```

导入时若出现主键、账号、成员 ID、婚姻 ID 或照片 hash 重复，系统停止导入并返回具体冲突原因。

## 16. EXPLAIN 性能实验

性能实验在 `output/performance-test` 下保存 `EXPLAIN` 结果。典型搜索分析：

```sql
EXPLAIN
SELECT member_id, clan_id, name, gender, birth_year, death_year,
       father_id, mother_id, generation_num
FROM members
WHERE clan_id = 1
  AND name >= '张_1_1'
  AND name <  '张_1_2'
ORDER BY clan_id, generation_num, member_id
LIMIT 200;
```

索引启用后，姓名前缀查询可以减少全表扫描范围；普通 `%keyword%` 模糊查询仍可能触发较大扫描，因此性能模式会优先把标准姓名格式转换成范围条件。
