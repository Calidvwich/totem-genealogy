-- 用途：对 Totem 族谱数据库做只读一致性检查；本文件仅包含查询语句。

SELECT 'users_count' AS check_name, COUNT(*) AS value FROM users;
SELECT 'genealogies_count' AS check_name, COUNT(*) AS value FROM genealogies;
SELECT 'collaborations_count' AS check_name, COUNT(*) AS value FROM collaborations;
SELECT 'members_count' AS check_name, COUNT(*) AS value FROM members;
SELECT 'marriages_count' AS check_name, COUNT(*) AS value FROM marriages;
SELECT 'member_photos_count' AS check_name, COUNT(*) AS value FROM member_photos;

SELECT 'duplicate_user_id' AS check_name, user_id, COUNT(*) AS issue_count
FROM users
GROUP BY user_id
HAVING COUNT(*) > 1;

SELECT 'genealogy_creator_missing' AS check_name, g.clan_id, g.creator_id
FROM genealogies g
LEFT JOIN users u ON u.id = g.creator_id
WHERE g.creator_id IS NOT NULL AND u.id IS NULL;

SELECT 'collaboration_clan_missing' AS check_name, c.clan_id, c.user_id
FROM collaborations c
LEFT JOIN genealogies g ON g.clan_id = c.clan_id
WHERE g.clan_id IS NULL;

SELECT 'collaboration_user_missing' AS check_name, c.clan_id, c.user_id
FROM collaborations c
LEFT JOIN users u ON u.id = c.user_id
WHERE u.id IS NULL;

SELECT 'member_clan_missing' AS check_name, m.member_id, m.clan_id
FROM members m
LEFT JOIN genealogies g ON g.clan_id = m.clan_id
WHERE m.clan_id IS NOT NULL AND g.clan_id IS NULL;

SELECT 'member_invalid_gender' AS check_name, member_id, gender
FROM members
WHERE gender IS NOT NULL AND gender NOT IN ('M', 'F', 'U');

SELECT 'member_death_before_birth' AS check_name, member_id, birth_year, death_year
FROM members
WHERE birth_year IS NOT NULL AND death_year IS NOT NULL AND death_year < birth_year;

SELECT 'member_self_parent' AS check_name, member_id, father_id, mother_id
FROM members
WHERE member_id = father_id OR member_id = mother_id;

SELECT 'member_father_missing' AS check_name, m.member_id, m.father_id
FROM members m
LEFT JOIN members f ON f.member_id = m.father_id
WHERE m.father_id IS NOT NULL AND f.member_id IS NULL;

SELECT 'member_mother_missing' AS check_name, m.member_id, m.mother_id
FROM members m
LEFT JOIN members mo ON mo.member_id = m.mother_id
WHERE m.mother_id IS NOT NULL AND mo.member_id IS NULL;

SELECT 'member_parent_same_person' AS check_name, member_id, father_id, mother_id
FROM members
WHERE father_id IS NOT NULL AND mother_id IS NOT NULL AND father_id = mother_id;

SELECT 'member_father_not_male' AS check_name, m.member_id, m.father_id, f.gender
FROM members m
JOIN members f ON f.member_id = m.father_id
WHERE f.gender <> 'M';

SELECT 'member_mother_not_female' AS check_name, m.member_id, m.mother_id, mo.gender
FROM members m
JOIN members mo ON mo.member_id = m.mother_id
WHERE mo.gender <> 'F';

SELECT 'member_father_birth_order' AS check_name, m.member_id, m.birth_year, f.member_id AS father_id, f.birth_year AS father_birth_year
FROM members m
JOIN members f ON f.member_id = m.father_id
WHERE m.birth_year IS NOT NULL AND f.birth_year IS NOT NULL AND m.birth_year <= f.birth_year;

SELECT 'member_mother_birth_order' AS check_name, m.member_id, m.birth_year, mo.member_id AS mother_id, mo.birth_year AS mother_birth_year
FROM members m
JOIN members mo ON mo.member_id = m.mother_id
WHERE m.birth_year IS NOT NULL AND mo.birth_year IS NOT NULL AND m.birth_year <= mo.birth_year;

SELECT 'member_father_death_order' AS check_name, m.member_id, m.birth_year, f.member_id AS father_id, f.death_year AS father_death_year
FROM members m
JOIN members f ON f.member_id = m.father_id
WHERE m.birth_year IS NOT NULL AND f.death_year IS NOT NULL AND m.birth_year >= f.death_year;

SELECT 'member_mother_death_order' AS check_name, m.member_id, m.birth_year, mo.member_id AS mother_id, mo.death_year AS mother_death_year
FROM members m
JOIN members mo ON mo.member_id = m.mother_id
WHERE m.birth_year IS NOT NULL AND mo.death_year IS NOT NULL AND m.birth_year >= mo.death_year;

SELECT 'marriage_clan_missing' AS check_name, mg.marriage_id, mg.clan_id
FROM marriages mg
LEFT JOIN genealogies g ON g.clan_id = mg.clan_id
WHERE mg.clan_id IS NOT NULL AND g.clan_id IS NULL;

SELECT 'marriage_spouse_a_missing' AS check_name, mg.marriage_id, mg.spouse_a_id
FROM marriages mg
LEFT JOIN members a ON a.member_id = mg.spouse_a_id
WHERE mg.spouse_a_id IS NOT NULL AND a.member_id IS NULL;

SELECT 'marriage_spouse_b_missing' AS check_name, mg.marriage_id, mg.spouse_b_id
FROM marriages mg
LEFT JOIN members b ON b.member_id = mg.spouse_b_id
WHERE mg.spouse_b_id IS NOT NULL AND b.member_id IS NULL;

SELECT 'marriage_same_spouse' AS check_name, marriage_id, spouse_a_id, spouse_b_id
FROM marriages
WHERE spouse_a_id IS NOT NULL AND spouse_b_id IS NOT NULL AND spouse_a_id = spouse_b_id;

SELECT 'marriage_divorce_before_marry' AS check_name, marriage_id, marry_year, divorce_year
FROM marriages
WHERE marry_year IS NOT NULL AND divorce_year IS NOT NULL AND divorce_year < marry_year;

SELECT 'marriage_cross_clan_spouse' AS check_name, mg.marriage_id, mg.clan_id, a.clan_id AS spouse_a_clan, b.clan_id AS spouse_b_clan
FROM marriages mg
JOIN members a ON a.member_id = mg.spouse_a_id
JOIN members b ON b.member_id = mg.spouse_b_id
WHERE mg.clan_id IS NOT NULL AND (a.clan_id <> mg.clan_id OR b.clan_id <> mg.clan_id);

SELECT 'duplicate_marriage_pair' AS check_name, clan_id,
       CASE WHEN spouse_a_id < spouse_b_id THEN spouse_a_id ELSE spouse_b_id END AS spouse_low,
       CASE WHEN spouse_a_id < spouse_b_id THEN spouse_b_id ELSE spouse_a_id END AS spouse_high,
       COUNT(*) AS issue_count
FROM marriages
WHERE spouse_a_id IS NOT NULL AND spouse_b_id IS NOT NULL
GROUP BY clan_id,
         CASE WHEN spouse_a_id < spouse_b_id THEN spouse_a_id ELSE spouse_b_id END,
         CASE WHEN spouse_a_id < spouse_b_id THEN spouse_b_id ELSE spouse_a_id END
HAVING COUNT(*) > 1;

SELECT 'member_photo_blob_missing' AS check_name, m.member_id, m.id_pic
FROM members m
LEFT JOIN member_photos p ON p.photo_sha256 = m.id_pic
WHERE m.id_pic IS NOT NULL AND m.id_pic <> '' AND p.photo_sha256 IS NULL;

SELECT 'unreferenced_member_photo' AS check_name, p.photo_sha256
FROM member_photos p
LEFT JOIN members m ON m.id_pic = p.photo_sha256
WHERE m.member_id IS NULL;
