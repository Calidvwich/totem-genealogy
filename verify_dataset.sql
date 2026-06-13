SELECT id,user_id,password_hash FROM users WHERE user_id = 'admin';
SELECT clan_id, COUNT(member_id) AS members FROM members GROUP BY clan_id ORDER BY clan_id;
SELECT COUNT(clan_id) AS admin_created_genealogies FROM genealogies WHERE creator_id = (SELECT id FROM users WHERE user_id = 'admin');
SELECT COUNT(clan_id) AS admin_collaborations FROM collaborations WHERE user_id = (SELECT id FROM users WHERE user_id = 'admin');
SELECT COUNT(m.marriage_id) AS marriages_with_common_child
FROM marriages m
WHERE EXISTS (
    SELECT 1 FROM members c
    WHERE c.father_id = m.spouse_a_id AND c.mother_id = m.spouse_b_id
);
