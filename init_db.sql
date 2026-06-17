-- Totem genealogy database schema.
-- Run with:
--   /usr/local/totem/bin/tsql -U totem -p 55432 -d genealogy -f init_db.sql
--
-- Design:
--   1. Relational business tables keep durable application data.
--   2. objects/object_proxies keep a stable object identity layer.
--   3. member_objects/marriage_objects are Totem CLASS objects.
--   4. SELECTDEPUTYCLASS definitions expose relationship and role proxies.
--
-- Import scripts must copy members/marriages into member_objects/marriage_objects
-- after bulk import so deputy classes can be queried by the application.

CREATE TABLE objects (
    object_id    BIGINT       PRIMARY KEY,
    object_type  VARCHAR(30)  NOT NULL,
    display_name VARCHAR(100),
    created_at   TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE object_proxies (
    proxy_id    BIGINT       PRIMARY KEY,
    object_id   BIGINT       NOT NULL,
    proxy_table VARCHAR(40)  NOT NULL,
    proxy_pk    BIGINT       NOT NULL,
    proxy_label VARCHAR(100),
    created_at  TIMESTAMP    DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE users (
    id            INTEGER      PRIMARY KEY,
    object_id     BIGINT,
    user_id       VARCHAR(20)  UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    username      VARCHAR(50),
    created_at    TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_users_user_id_len CHECK (length(trim(user_id)) >= 4)
);

CREATE TABLE genealogies (
    clan_id    INTEGER      PRIMARY KEY,
    object_id  BIGINT,
    title      VARCHAR(100) NOT NULL,
    surname    VARCHAR(20),
    revised_at TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    creator_id INTEGER
);

CREATE TABLE collaborations (
    clan_id INTEGER,
    user_id INTEGER,
    PRIMARY KEY (clan_id, user_id)
);

CREATE TABLE members (
    member_id      BIGINT       PRIMARY KEY,
    object_id      BIGINT,
    clan_id        INTEGER,
    name           VARCHAR(50)  NOT NULL,
    gender         CHAR(1)      DEFAULT 'U',
    birth_year     INTEGER,
    death_year     INTEGER,
    father_id      BIGINT,
    mother_id      BIGINT,
    generation_num INTEGER,
    bio            TEXT,
    id_pic         TEXT,
    CONSTRAINT chk_members_gender CHECK (gender IN ('M', 'F', 'U')),
    CONSTRAINT chk_members_birth_death CHECK (
        birth_year IS NULL OR death_year IS NULL OR death_year >= birth_year
    ),
    CONSTRAINT chk_members_not_own_parent CHECK (
        (father_id IS NULL OR member_id <> father_id)
        AND (mother_id IS NULL OR member_id <> mother_id)
    )
);

CREATE TABLE marriages (
    marriage_id  INTEGER PRIMARY KEY,
    object_id    BIGINT,
    clan_id      INTEGER,
    spouse_a_id  BIGINT,
    spouse_b_id  BIGINT,
    marry_year   INTEGER,
    divorce_year INTEGER,
    CONSTRAINT chk_marriages_distinct_spouses CHECK (spouse_a_id <> spouse_b_id),
    CONSTRAINT chk_marriages_year_order CHECK (
        marry_year IS NULL OR divorce_year IS NULL OR divorce_year >= marry_year
    )
);

CREATE TABLE member_photos (
    photo_sha256   VARCHAR(64) PRIMARY KEY,
    object_id      BIGINT,
    content_type   VARCHAR(100) NOT NULL,
    content_base64 TEXT NOT NULL,
    created_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Basic indexes for identity and permission checks. Search-performance indexes
-- are still controlled by the application performance mode.
CREATE INDEX idx_objects_type ON objects(object_type);
CREATE INDEX idx_object_proxies_object ON object_proxies(object_id);
CREATE INDEX idx_object_proxies_target ON object_proxies(proxy_table, proxy_pk);
CREATE INDEX idx_collaborations_user ON collaborations(user_id);

-- Totem object classes. SELECTDEPUTYCLASS must be based on CLASS objects, not
-- ordinary CREATE TABLE tables.
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

CREATE CLASS marriage_objects (
    marriage_id INTEGER,
    clan_id INTEGER,
    spouse_a_id BIGINT,
    spouse_b_id BIGINT,
    marry_year INTEGER,
    divorce_year INTEGER
);

-- Parent-child relationship proxies.
CREATE SELECTDEPUTYCLASS father_down_edges
AS (
    SELECT
        c.clan_id,
        c.father_id AS from_member_id,
        c.member_id AS to_member_id,
        c.birth_year AS child_birth_year,
        c.generation_num AS child_generation
    FROM member_objects AS c
    WHERE c.father_id IS NOT NULL
);

CREATE SELECTDEPUTYCLASS mother_down_edges
AS (
    SELECT
        c.clan_id,
        c.mother_id AS from_member_id,
        c.member_id AS to_member_id,
        c.birth_year AS child_birth_year,
        c.generation_num AS child_generation
    FROM member_objects AS c
    WHERE c.mother_id IS NOT NULL
);

CREATE SELECTDEPUTYCLASS father_up_edges
AS (
    SELECT
        c.clan_id,
        c.member_id AS from_member_id,
        c.father_id AS to_member_id,
        c.generation_num AS child_generation
    FROM member_objects AS c
    WHERE c.father_id IS NOT NULL
);

CREATE SELECTDEPUTYCLASS mother_up_edges
AS (
    SELECT
        c.clan_id,
        c.member_id AS from_member_id,
        c.mother_id AS to_member_id,
        c.generation_num AS child_generation
    FROM member_objects AS c
    WHERE c.mother_id IS NOT NULL
);

-- Marriage relationship proxies.
CREATE SELECTDEPUTYCLASS spouse_a_edges
AS (
    SELECT
        marriage_id,
        clan_id,
        spouse_a_id AS from_member_id,
        spouse_b_id AS to_member_id,
        marry_year,
        divorce_year
    FROM marriage_objects
    WHERE spouse_a_id IS NOT NULL
      AND spouse_b_id IS NOT NULL
);

CREATE SELECTDEPUTYCLASS spouse_b_edges
AS (
    SELECT
        marriage_id,
        clan_id,
        spouse_b_id AS from_member_id,
        spouse_a_id AS to_member_id,
        marry_year,
        divorce_year
    FROM marriage_objects
    WHERE spouse_a_id IS NOT NULL
      AND spouse_b_id IS NOT NULL
);

-- Role/statistic proxies. Aggregation is intentionally left to normal SQL or
-- the service layer because Totem SELECTDEPUTYCLASS does not allow aggregates.
CREATE SELECTDEPUTYCLASS male_50_plus
AS (
    SELECT
        m.member_id,
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

CREATE SELECTDEPUTYCLASS living_members
AS (
    SELECT
        m.member_id,
        m.clan_id,
        m.name,
        m.gender,
        m.birth_year,
        m.generation_num
    FROM member_objects AS m
    WHERE m.death_year IS NULL
);

CREATE SELECTDEPUTYCLASS known_lifespan_members
AS (
    SELECT
        m.member_id,
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

CREATE SELECTDEPUTYCLASS male_members
AS (
    SELECT member_id, clan_id, name, birth_year, death_year, generation_num
    FROM member_objects
    WHERE gender = 'M'
);

CREATE SELECTDEPUTYCLASS female_members
AS (
    SELECT member_id, clan_id, name, birth_year, death_year, generation_num
    FROM member_objects
    WHERE gender = 'F'
);

CREATE SELECTDEPUTYCLASS active_marriages
AS (
    SELECT marriage_id, clan_id, spouse_a_id, spouse_b_id, marry_year
    FROM marriage_objects
    WHERE divorce_year IS NULL
);

CREATE SELECTDEPUTYCLASS divorced_marriages
AS (
    SELECT marriage_id, clan_id, spouse_a_id, spouse_b_id, marry_year, divorce_year
    FROM marriage_objects
    WHERE divorce_year IS NOT NULL
);

-- Seed users. Both passwords are 123456, stored as pbkdf2_sha256 hashes.
INSERT INTO objects (object_id, object_type, display_name)
SELECT 1, 'user', 'admin'
WHERE NOT EXISTS (SELECT 1 FROM objects WHERE object_id = 1);

INSERT INTO objects (object_id, object_type, display_name)
SELECT 2, 'user', 'test01'
WHERE NOT EXISTS (SELECT 1 FROM objects WHERE object_id = 2);

INSERT INTO objects (object_id, object_type, display_name)
SELECT 1001, 'genealogy', '张氏示例族谱'
WHERE NOT EXISTS (SELECT 1 FROM objects WHERE object_id = 1001);

INSERT INTO users (id, object_id, user_id, password_hash, username)
SELECT 1, 1, 'admin', 'pbkdf2_sha256$150000$oIG0zKga4xpBMJ9KI7bAOg$3TjiTzurVc75Ql8+C5hQnSf7w5O9WK3UHcntJqJY6us', '管理员'
WHERE NOT EXISTS (SELECT 1 FROM users WHERE user_id = 'admin');

INSERT INTO users (id, object_id, user_id, password_hash, username)
SELECT 2, 2, 'test01', 'pbkdf2_sha256$150000$oIG0zKga4xpBMJ9KI7bAOg$3TjiTzurVc75Ql8+C5hQnSf7w5O9WK3UHcntJqJY6us', '测试用户'
WHERE NOT EXISTS (SELECT 1 FROM users WHERE user_id = 'test01');

INSERT INTO genealogies (clan_id, object_id, title, surname, creator_id)
SELECT 1, 1001, '张氏示例族谱', '张', id FROM users WHERE user_id = 'admin'
AND NOT EXISTS (SELECT 1 FROM genealogies WHERE clan_id = 1);

INSERT INTO object_proxies (proxy_id, object_id, proxy_table, proxy_pk, proxy_label)
SELECT 1, 1, 'users', id, user_id FROM users WHERE user_id = 'admin'
AND NOT EXISTS (SELECT 1 FROM object_proxies WHERE proxy_id = 1);

INSERT INTO object_proxies (proxy_id, object_id, proxy_table, proxy_pk, proxy_label)
SELECT 2, 2, 'users', id, user_id FROM users WHERE user_id = 'test01'
AND NOT EXISTS (SELECT 1 FROM object_proxies WHERE proxy_id = 2);

INSERT INTO object_proxies (proxy_id, object_id, proxy_table, proxy_pk, proxy_label)
SELECT 1001, 1001, 'genealogies', clan_id, title FROM genealogies WHERE clan_id = 1
AND NOT EXISTS (SELECT 1 FROM object_proxies WHERE proxy_id = 1001);

INSERT INTO collaborations (clan_id, user_id)
SELECT 1, id FROM users WHERE user_id = 'admin'
AND NOT EXISTS (
    SELECT 1 FROM collaborations
    WHERE clan_id = 1 AND user_id = (SELECT id FROM users WHERE user_id = 'admin')
);
