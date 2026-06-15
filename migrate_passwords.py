from main import TotemClient, hash_password, is_password_hash, sql_literal


def main() -> None:
    client = TotemClient()
    rows = client.query("SELECT id,user_id,password_hash FROM users ORDER BY id;")
    migrated = 0
    skipped = 0
    for row in rows:
        stored = row.get("password_hash") or ""
        if is_password_hash(stored):
            skipped += 1
            continue
        new_hash = hash_password(stored)
        client.execute(
            "UPDATE users SET password_hash = {} WHERE id = {};".format(
                sql_literal(new_hash),
                sql_literal(int(row["id"])),
            )
        )
        migrated += 1
        print("migrated user_id={}".format(row.get("user_id")))
    print("password migration complete: migrated={}, skipped={}".format(migrated, skipped))


if __name__ == "__main__":
    main()
