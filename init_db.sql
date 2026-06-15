-- Totem genealogy database schema.
-- Run with:
--   /usr/local/totem/bin/tsql -d genealogy -f init_db.sql

CREATE TABLE users (
    id            INTEGER      PRIMARY KEY,
    user_id       VARCHAR(20)  UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    username      VARCHAR(50),
    created_at    TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_users_user_id_len CHECK (length(trim(user_id)) >= 4)
);

CREATE TABLE genealogies (
    clan_id    INTEGER      PRIMARY KEY,
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
    photo_sha256  VARCHAR(64) PRIMARY KEY,
    content_type  VARCHAR(100) NOT NULL,
    content_base64 TEXT NOT NULL,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Member search indexes are managed by the app performance mode:
--   idx_members_clan, idx_members_clan_name, idx_members_father, idx_members_mother.
-- Normal mode drops them; performance mode creates them before measured search.
CREATE INDEX idx_collaborations_user ON collaborations(user_id);

INSERT INTO users (id, user_id, password_hash, username)
SELECT 1, 'admin', 'pbkdf2_sha256$150000$oIG0zKga4xpBMJ9KI7bAOg$3TjiTzurVc75Ql8+C5hQnSf7w5O9WK3UHcntJqJY6us', '管理员'
WHERE NOT EXISTS (SELECT 1 FROM users WHERE user_id = 'admin');

INSERT INTO users (id, user_id, password_hash, username)
SELECT 2, 'test01', 'pbkdf2_sha256$150000$oIG0zKga4xpBMJ9KI7bAOg$3TjiTzurVc75Ql8+C5hQnSf7w5O9WK3UHcntJqJY6us', '测试用户'
WHERE NOT EXISTS (SELECT 1 FROM users WHERE user_id = 'test01');

INSERT INTO genealogies (clan_id, title, surname, creator_id)
SELECT 1, '张氏示例族谱', '张', id FROM users WHERE user_id = 'admin'
AND NOT EXISTS (SELECT 1 FROM genealogies WHERE clan_id = 1);

INSERT INTO collaborations (clan_id, user_id)
SELECT 1, id FROM users WHERE user_id = 'admin'
AND NOT EXISTS (
    SELECT 1 FROM collaborations
    WHERE clan_id = 1 AND user_id = (SELECT id FROM users WHERE user_id = 'admin')
);
