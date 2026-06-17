# 对象代理与 Select Deputy Class 设计说明

本项目在基础业务表之外补充了 `deputy_classes.sql`，用于体现 TotemDB 中更典型的对象代理风格。

需要注意：TotemDB 的 `CREATE SELECTDEPUTYCLASS` 不能直接基于普通 `CREATE TABLE` 表创建，父对象必须是 `CREATE CLASS` 得到的对象类。因此脚本会先把当前业务表投影为对象类：

- `member_objects`
- `marriage_objects`

然后再基于这些对象类建立 Select 代理类。

## 1. 为什么不是只看 father_id / mother_id

传统关系表中，父子、母子、夫妻关系分散在不同字段中：

- `members.father_id`
- `members.mother_id`
- `marriages.spouse_a_id`
- `marriages.spouse_b_id`

如果每个业务查询都直接判断这些字段，查询语句会重复出现大量组合条件。对象代理风格的做法是先把这些关系整理成可复用的代理类，让业务层查询“关系对象”而不是重复拼字段。

## 2. 关系边代理

TotemDB 的 Select Deputy Class 不允许在定义中使用 `UNION` 或聚合查询。因此本项目没有把父亲边和母亲边强行合成一个代理类，而是拆为两个简单代理类，并且它们基于 `member_objects` 对象类：

- `father_down_edges`
- `mother_down_edges`

```sql
CREATE SELECTDEPUTYCLASS father_down_edges AS (
    SELECT father_id AS from_member_id, member_id AS to_member_id, 'father' AS parent_role
    FROM member_objects
    WHERE father_id IS NOT NULL
);

CREATE SELECTDEPUTYCLASS mother_down_edges AS (
    SELECT mother_id AS from_member_id, member_id AS to_member_id, 'mother' AS parent_role
    FROM member_objects
    WHERE mother_id IS NOT NULL
);
```

这样查询某人的子女时，不再需要写：

```sql
WHERE father_id = ? OR mother_id = ?
```

而是查询：

```sql
SELECT * FROM father_down_edges WHERE from_member_id = ?
UNION ALL
SELECT * FROM mother_down_edges WHERE from_member_id = ?;
```

后端接口会分别读取两个代理类，再在业务层合并结果。向上查找同理使用：

- `father_up_edges`
- `mother_up_edges`

## 3. 夫妻边代理

夫妻关系也拆为两个基于 `marriage_objects` 的简单代理类：

- `spouse_a_edges`：A -> B
- `spouse_b_edges`：B -> A

这样树形展示、成员详情、亲缘路径都可以使用统一的边语义。

## 4. 成员角色代理

`male_50_plus` 是一个 Select 代理类，用于表示“50 岁以上且仍在世的男性成员”。

由于 Select Deputy Class 不适合定义复杂反连接，是否“单身”由业务层在 `male_50_plus` 候选集上继续检查 `spouse_a_edges/spouse_b_edges`。这样仍然比每次从全体成员开始筛选更符合角色代理思路。

## 5. 统计代理

每代平均出生年份、早于本代平均出生年份等查询依赖 `AVG/GROUP BY`。由于 TotemDB 当前 `CREATE SELECTDEPUTYCLASS` 不允许聚合，这部分仍由普通统计 SQL 或后端逻辑完成，不放入 Select 代理类。

## 6. 与系统代码的关系

当前后端查询采用兼容策略：

1. 如果已经执行 `deputy_classes.sql`，优先查询代理类。
2. 如果代理类不存在，自动回退到原来的业务表查询。

目前优先使用代理类的功能包括：

- 配偶/子女查询：`spouse_a_edges`、`spouse_b_edges`、`father_down_edges`、`mother_down_edges`
- 祖先查询：`father_up_edges`、`mother_up_edges`
- 亲缘路径查询：父母边代理 + 配偶边代理
- 四代曾孙查询：`father_down_edges`、`mother_down_edges`
- 50 岁以上单身男性查询：`male_50_plus` + 配偶边代理
- 每代平均寿命：`known_lifespan_members` 作为候选集，业务层完成分组平均

额外角色代理类：

- `living_members`
- `male_members`
- `female_members`
- `active_marriages`
- `divorced_marriages`

因此数据库可以先用基础表运行，也可以在验收或报告中执行：

```bash
/usr/local/totem/bin/tsql -U totem -p 55432 -d genealogy -f deputy_classes.sql
```

执行后，配偶/子女、50+ 单身男性、早于本代平均出生年份等查询会优先体现 Select Deputy Class 风格。
