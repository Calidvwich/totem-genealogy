 #族谱系统 PostgreSQL 脚本集合，初步思路，供参考
 一、数据库初始化（建表 + 约束 + 索引）
1. 用户表
CREATE TABLE IF NOT EXISTS users (
    id            SERIAL       PRIMARY KEY,
    user_id       VARCHAR(20)  UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    username      VARCHAR(50),
    created_at    TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);
2. 族谱表
CREATE TABLE IF NOT EXISTS genealogies (
    clan_id    SERIAL       PRIMARY KEY,
    title      VARCHAR(100) NOT NULL,
    surname    VARCHAR(20),
    revised_at TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    creator_id INTEGER      REFERENCES users(id) ON DELETE SET NULL
);
3. 协作表（联合主键 = 多对多关联表）
CREATE TABLE IF NOT EXISTS collaborations (
    clan_id INTEGER REFERENCES genealogies(clan_id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id)            ON DELETE CASCADE,
    PRIMARY KEY (clan_id, user_id)
);
4. 成员表
CREATE TABLE IF NOT EXISTS members (
    member_id      BIGINT       PRIMARY KEY,
    clan_id        INTEGER      REFERENCES genealogies(clan_id) ON DELETE CASCADE,
    name           VARCHAR(50)  NOT NULL,
    gender         CHAR(1)      CHECK (gender IN ('M', 'F')),
    birth_year     INT,
    death_year     INT,
    father_id      BIGINT       REFERENCES members(member_id) ON DELETE SET NULL,
    mother_id      BIGINT       REFERENCES members(member_id) ON DELETE SET NULL,
    generation_num INT,
    bio            TEXT,
    id_pic         TEXT,        -- base64 data URI
    -- CHECK 约束：出生年必须早于死亡年
    CONSTRAINT chk_birth_before_death CHECK (
        birth_year IS NULL OR death_year IS NULL OR birth_year < death_year
    )
);
5. 性能索引
CREATE INDEX IF NOT EXISTS idx_members_father   ON members(father_id);
CREATE INDEX IF NOT EXISTS idx_members_mother   ON members(mother_id);
CREATE INDEX IF NOT EXISTS idx_members_clan     ON members(clan_id);
CREATE INDEX IF NOT EXISTS idx_members_clan_name ON members(clan_id, name);
CREATE INDEX IF NOT EXISTS idx_members_birth    ON members(birth_year);
CREATE INDEX IF NOT EXISTS idx_members_gender   ON members(gender);
二、生成模拟数据（使用 generate_series + 递归）
2.1 插入一个示例用户
INSERT INTO users (user_id, password_hash, username)
VALUES ('admin', 'hashed_password_here', '管理员')
ON CONFLICT (user_id) DO NOTHING;
2.2 插入示例族谱
INSERT INTO genealogies (clan_id, title, surname, creator_id)
VALUES (1, '示例族谱', '张', (SELECT id FROM users WHERE user_id = 'admin'))
ON CONFLICT DO NOTHING;
2.3 批量生成成员数据（示例：用 generate_series 生成 100 条测试数据）
生产环境使用 generate_data.py 生成 CSV 后通过 COPY 导入（见下方）
INSERT INTO members (member_id, clan_id, name, gender, birth_year, death_year, generation_num, bio)
SELECT
    gs AS member_id,
    1  AS clan_id,
    '成员_' || gs AS name,
    CASE WHEN gs % 2 = 0 THEN 'M' ELSE 'F' END AS gender,
    1800 + (gs % 10) * 15 AS birth_year,
    1800 + (gs % 10) * 15 + 60 + (gs % 30) AS death_year,
    CEIL(gs::NUMERIC / 10)::INT AS generation_num,
    '第' || CEIL(gs::NUMERIC / 10)::INT || '代成员' AS bio
FROM generate_series(1, 100) AS gs
ON CONFLICT DO NOTHING;

三、CSV 批量导入（generate_data.py 输出后执行）
步骤1：运行 Python 脚本生成 CSV
python generate_data.py
步骤2：使用 COPY 命令导入（在 psql 中执行）
注意：NULL 值以空字符串表示，需指定 NULL ''
\COPY members(member_id, clan_id, name, gender, father_id, mother_id, generation_num, bio)
FROM 'members_load.csv'
WITH (FORMAT CSV, NULL '');
或使用 pg_restore / psql 管道方式：psql -U postgres -d genealogy_db -c "\COPY members(...) FROM 'members_load.csv' WITH (FORMAT CSV, NULL '');"

四、业务查询脚本
4.1 查询某个成员的配偶和所有子女
说明：配偶定义为"与该成员共同出现在某子女的 father_id 或 mother_id 中的另一方"
即：找到所有子女，再从子女记录中提取另一个父母即为配偶。
查询 member_id = :mid 的配偶（去重，可能有多个）
WITH target AS (
    SELECT :mid::BIGINT AS mid   -- ← 替换 :mid 为具体成员 ID，例如 1
),
children_of_target AS (
    SELECT member_id, father_id, mother_id
    FROM members
    WHERE father_id = (SELECT mid FROM target)
       OR mother_id = (SELECT mid FROM target)
)
SELECT DISTINCT
    s.member_id,
    s.name      AS spouse_name,
    s.gender,
    s.birth_year
FROM children_of_target c
JOIN members s ON s.member_id = CASE
    WHEN c.father_id = (SELECT mid FROM target) THEN c.mother_id
    ELSE c.father_id
END
ORDER BY s.member_id;

-- 查询 member_id = :mid 的所有直接子女
SELECT
    member_id,
    name,
    gender,
    birth_year,
    death_year,
    generation_num
FROM members
WHERE father_id = :mid   -- ← 替换 :mid
   OR mother_id = :mid
ORDER BY birth_year NULLS LAST;


4.2 查询某个成员的所有祖先（递归 CTE）
向上追溯所有父母、祖父母……直到无父母为止

WITH RECURSIVE ancestors AS (
    -- 基础：目标成员本身
    SELECT
        member_id, name, gender, birth_year, death_year,
        father_id, mother_id, generation_num,
        0 AS depth
    FROM members
    WHERE member_id = :mid   -- ← 替换 :mid

    UNION ALL

    递归：向上找父母
    SELECT
        m.member_id, m.name, m.gender, m.birth_year, m.death_year,
        m.father_id, m.mother_id, m.generation_num,
        a.depth + 1
    FROM members m
    JOIN ancestors a ON m.member_id = a.father_id
                     OR m.member_id = a.mother_id
)
SELECT DISTINCT
    member_id,
    name,
    gender,
    birth_year,
    death_year,
    generation_num,
    depth AS generations_above
FROM ancestors
WHERE depth > 0   -- 排除目标本身
ORDER BY depth, member_id;


4.3 统计某个家族中年纪最长的人
年纪最长 = 出生年份最早（birth_year 最小）

SELECT
    member_id,
    name,
    gender,
    birth_year,
    death_year,
    generation_num
FROM members
WHERE clan_id = :clan_id   -- ← 替换 :clan_id
  AND birth_year IS NOT NULL
ORDER BY birth_year ASC
LIMIT 1;

若需要同时显示"最长寿"（活得最久），则改为：
SELECT
    member_id,
    name,
    gender,
    birth_year,
    death_year,
    COALESCE(death_year, EXTRACT(YEAR FROM CURRENT_DATE)::INT) - birth_year AS age_span
FROM members
WHERE clan_id = :clan_id
  AND birth_year IS NOT NULL
ORDER BY age_span DESC
LIMIT 1;


-- ── 4.4 基于系统当前日期查询超过 50 岁的男性单身成员 ──────
单身定义：该成员在所有子女记录中，其配偶位置为 NULL。即：没有任何子女的 father_id/mother_id 同时指向另一人
-- 简化判断：在 members 表中，没有任何记录以该成员为父且同时有母，或以该成员为母且同时有父
SELECT DISTINCT
    m.member_id,
    m.name,
    m.gender,
    m.birth_year,
    m.death_year,
    EXTRACT(YEAR FROM CURRENT_DATE)::INT - m.birth_year AS estimated_age
FROM members m
WHERE m.gender = 'M'
  AND m.death_year IS NULL                            
  AND m.birth_year IS NOT NULL
  AND EXTRACT(YEAR FROM CURRENT_DATE)::INT - m.birth_year > 50
  AND NOT EXISTS (
      -- 排除：作为父亲且子女同时有母亲的情况（即已婚）
      SELECT 1 FROM members c
      WHERE c.father_id = m.member_id
        AND c.mother_id IS NOT NULL
  )
  AND NOT EXISTS (
      -- 同理排除作为母亲一侧的情况（虽然这里筛的是男性，保留完整性）
      SELECT 1 FROM members c
      WHERE c.mother_id = m.member_id
        AND c.father_id IS NOT NULL
  )
ORDER BY m.birth_year ASC;


-- ── 4.5 四代查询：查询某个曾祖父的所有曾孙 ──────
-- 说明：给定某个成员 ID (即曾祖父/曾祖母，第1代)，查询其第4代后代（曾孙辈）
WITH RECURSIVE descendants AS (
    -- 1) 初始条件：将起始成员作为第 1 代
    SELECT
        member_id,
        1 AS depth
    FROM members
    WHERE member_id = :start_member_id  -- ← 替换要查询的曾祖父/曾祖母 ID
    
    UNION ALL
    
    -- 2) 递归条件：从第 i 代寻找子女 (第 i+1 代)
    SELECT
        m.member_id,
        d.depth + 1
    FROM members m
    JOIN descendants d ON m.father_id = d.member_id OR m.mother_id = d.member_id
    WHERE d.depth < 4
)
-- 3) 最终筛选第 4 代 (即曾孙辈)
SELECT m.member_id, m.name, m.gender, m.generation_num, m.birth_year
FROM descendants d
JOIN members m ON d.member_id = m.member_id
WHERE d.depth = 4;


4.5 找出出生年份早于本代平均出生年份的所有成员
按 (clan_id, generation_num) 分组，计算每代平均出生年，
然后找出个人出生年 < 该代平均出生年的成员
WITH gen_avg AS (
    SELECT
        clan_id,
        generation_num,
        AVG(birth_year) AS avg_birth_year
    FROM members
    WHERE birth_year IS NOT NULL
    GROUP BY clan_id, generation_num
)
SELECT
    m.member_id,
    m.clan_id,
    m.name,
    m.gender,
    m.birth_year,
    m.generation_num,
    ROUND(g.avg_birth_year, 2) AS generation_avg_birth_year,
    ROUND(g.avg_birth_year - m.birth_year, 2) AS years_earlier_than_avg
FROM members m
JOIN gen_avg g ON g.clan_id = m.clan_id
              AND g.generation_num = m.generation_num
WHERE m.birth_year IS NOT NULL
  AND m.birth_year < g.avg_birth_year
ORDER BY m.clan_id, m.generation_num, m.birth_year;