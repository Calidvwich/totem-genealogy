-- Totem genealogy Object Classes and Select Deputy Classes.
--
-- TotemDB Select Deputy Class must be based on CLASS objects rather than
-- ordinary relational tables. Therefore this script first projects the current
-- business tables into object classes, then creates deputy classes from those
-- classes.
--
-- Select Deputy Class is stricter than a normal SQL view: set operations such
-- as UNION and aggregate queries are not allowed. Therefore each relationship
-- or role is modeled as one simple select proxy.
--
-- Run after init_db.sql and after data import:
--   /usr/local/totem/bin/tsql -U totem -p 55432 -d genealogy -f deputy_classes.sql

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

INSERT INTO member_objects(member_id,clan_id,name,gender,birth_year,death_year,father_id,mother_id,generation_num)
SELECT member_id,clan_id,name,gender,birth_year,death_year,father_id,mother_id,generation_num
FROM members;

CREATE CLASS marriage_objects (
    marriage_id INTEGER,
    clan_id INTEGER,
    spouse_a_id BIGINT,
    spouse_b_id BIGINT,
    marry_year INTEGER,
    divorce_year INTEGER
);

INSERT INTO marriage_objects(marriage_id,clan_id,spouse_a_id,spouse_b_id,marry_year,divorce_year)
SELECT marriage_id,clan_id,spouse_a_id,spouse_b_id,marry_year,divorce_year
FROM marriages;

-- Father -> child edge proxy.
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

-- Mother -> child edge proxy.
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

-- Child -> father edge proxy.
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

-- Child -> mother edge proxy.
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

-- Marriage spouse_a -> spouse_b proxy.
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

-- Marriage spouse_b -> spouse_a proxy.
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

-- Living male members over 50. This is a role proxy. Whether he is single is
-- then checked by the service layer through spouse edge proxies or marriages.
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

-- Living members proxy, reused by dashboard/statistics when needed.
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

-- Members with enough year information to compute lifespan.
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

-- Gender role proxies.
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

-- Active and historical marriage role proxies.
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
