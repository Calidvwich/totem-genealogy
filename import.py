import argparse
import csv
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
DATABASE = os.getenv("TOTEM_DATABASE", "genealogy")
TSQL = os.getenv("TOTEM_TSQL", "/usr/local/totem/bin/tsql")
TOTEM_PORT = os.getenv("TOTEM_PORT", "")
TOTEM_USER = os.getenv("TOTEM_USER", "totem")

GENERATED_FILES = {
    "genealogies": APP_DIR / "genealogies_load.csv",
    "members": APP_DIR / "members_load.csv",
    "marriages": APP_DIR / "marriages_load.csv",
}


def sql_literal(value):
    if value is None or value == "":
        return "NULL"
    if isinstance(value, int):
        return str(value)
    return "'{}'".format(str(value).replace("'", "''"))


def optional_int(value):
    if value in (None, "", "NULL"):
        return None
    return int(value)


def run_tsql(args, timeout=120):
    command = [TSQL]
    if TOTEM_PORT:
        command.extend(["-p", TOTEM_PORT])
    if TOTEM_USER:
        command.extend(["-U", TOTEM_USER])
    command.extend(["-d", DATABASE])
    command.extend(args)
    completed = subprocess.run(
        command,
        cwd=str(APP_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        check=False,
        timeout=timeout,
    )
    if completed.returncode != 0:
        output = (completed.stderr.strip() or completed.stdout.strip() or "no output")
        sql_hint = ""
        if "-c" in args:
            try:
                sql_hint = " sql={}".format(args[args.index("-c") + 1][:300])
            except Exception:
                sql_hint = ""
        raise RuntimeError(
            "Totem SQL failed database={} user={} port={} command={}{} message={}".format(
                DATABASE,
                TOTEM_USER or "(default)",
                TOTEM_PORT or "(default)",
                " ".join(command),
                sql_hint,
                output,
            )
        )
    return completed.stdout


def query_scalar(sql, default=0):
    output = run_tsql(["-A", "-t", "-c", sql])
    for line in output.splitlines():
        line = line.strip()
        if line and not line.startswith("("):
            return line
    return default


def execute(sql, timeout=120):
    run_tsql(["-c", sql], timeout=timeout)


def try_execute(sql, timeout=120):
    try:
        execute(sql, timeout=timeout)
        return True
    except Exception:
        return False


def table_available(table):
    try:
        run_tsql(["-c", "SELECT 1 FROM {} LIMIT 1;".format(table)], timeout=30)
        return True
    except Exception:
        return False


def copy_from(table, columns, path, timeout=300):
    statement = "\\COPY {}({}) FROM '{}' WITH CSV NULL ''".format(
        table,
        ",".join(columns),
        str(path).replace("\\", "/").replace("'", "''"),
    )
    run_tsql(["-c", statement], timeout=timeout)


TABLE_COLUMNS = {
    "users": ["id", "user_id", "password_hash", "username", "created_at"],
    "genealogies": ["clan_id", "title", "surname", "revised_at", "creator_id"],
    "collaborations": ["clan_id", "user_id"],
    "members": ["member_id", "clan_id", "name", "gender", "birth_year", "death_year", "father_id", "mother_id", "generation_num", "bio", "id_pic"],
    "marriages": ["marriage_id", "clan_id", "spouse_a_id", "spouse_b_id", "marry_year", "divorce_year"],
    "member_photos": ["photo_sha256", "content_type", "content_base64", "created_at", "updated_at"],
}
RESTORE_ORDER = ["users", "genealogies", "collaborations", "members", "marriages", "member_photos"]

OBJECT_OFFSETS = {
    "user": 0,
    "genealogy": 100000000000,
    "member": 200000000000,
    "marriage": 300000000000,
}


def normalize_db_value(value):
    if value in (None, "", "NULL"):
        return None
    return value


def row_value(row, key):
    return normalize_db_value(row.get(key))


def count_where(table, condition):
    return int(query_scalar("SELECT COUNT(*) FROM {} WHERE {};".format(table, condition), 0))


def load_import_bundle(bundle_path):
    path = Path(bundle_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("format") != "totem-genealogy-import-bundle":
        raise ValueError("导入文件格式错误：format 必须为 totem-genealogy-import-bundle")
    if int(data.get("format_version", 0)) != 1:
        raise ValueError("导入文件版本不支持：{}".format(data.get("format_version")))
    tables = data.get("tables")
    if not isinstance(tables, dict):
        raise ValueError("导入文件缺少 tables")
    return data


def validate_bundle_duplicates(bundle, check_database=True):
    tables = bundle.get("tables", {})
    duplicate_messages = []
    seen = {}

    def check_internal(table, key_fields):
        keys = set()
        for index, row in enumerate(tables.get(table, []), start=1):
            key = tuple(row_value(row, field) for field in key_fields)
            if any(value is None for value in key):
                duplicate_messages.append("{} 第 {} 行缺少主键字段 {}".format(table, index, ",".join(key_fields)))
                continue
            if key in keys:
                duplicate_messages.append("{} 导入文件内部重复：{}".format(table, key))
            keys.add(key)
        seen[table] = keys

    check_internal("users", ["id"])
    check_internal("genealogies", ["clan_id"])
    check_internal("collaborations", ["clan_id", "user_id"])
    check_internal("members", ["member_id"])
    check_internal("marriages", ["marriage_id"])
    check_internal("member_photos", ["photo_sha256"])

    user_ids = set()
    for row in tables.get("users", []):
        user_id = row_value(row, "user_id")
        if not user_id:
            duplicate_messages.append("users 中存在空 user_id")
        elif user_id in user_ids:
            duplicate_messages.append("users 导入文件内部账号重复：{}".format(user_id))
        user_ids.add(user_id)

    if check_database:
        for user_id in sorted(user_ids):
            if count_where("users", "user_id = {}".format(sql_literal(user_id))):
                duplicate_messages.append("数据库中已存在账号 user_id={}".format(user_id))

        for key in sorted(seen.get("users", [])):
            if count_where("users", "id = {}".format(sql_literal(key[0]))):
                duplicate_messages.append("数据库中已存在 users.id={}".format(key[0]))
        for key in sorted(seen.get("genealogies", [])):
            if count_where("genealogies", "clan_id = {}".format(sql_literal(key[0]))):
                duplicate_messages.append("数据库中已存在 genealogies.clan_id={}".format(key[0]))
        for key in sorted(seen.get("members", [])):
            if count_where("members", "member_id = {}".format(sql_literal(key[0]))):
                duplicate_messages.append("数据库中已存在 members.member_id={}".format(key[0]))
        for key in sorted(seen.get("marriages", [])):
            if count_where("marriages", "marriage_id = {}".format(sql_literal(key[0]))):
                duplicate_messages.append("数据库中已存在 marriages.marriage_id={}".format(key[0]))
        for key in sorted(seen.get("member_photos", [])):
            if count_where("member_photos", "photo_sha256 = {}".format(sql_literal(key[0]))):
                duplicate_messages.append("数据库中已存在 member_photos.photo_sha256={}".format(key[0]))
        for key in sorted(seen.get("collaborations", [])):
            if count_where("collaborations", "clan_id = {} AND user_id = {}".format(sql_literal(key[0]), sql_literal(key[1]))):
                duplicate_messages.append("数据库中已存在 collaborations(clan_id={}, user_id={})".format(key[0], key[1]))

    if duplicate_messages:
        raise ValueError("导入停止，发现重复或无效数据：\n- " + "\n- ".join(duplicate_messages[:50]))


def insert_rows(table, rows):
    if not rows:
        return 0
    columns = TABLE_COLUMNS[table]
    if len(rows) >= 100:
        temp_path = None
        try:
            handle = tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                suffix="_{}_restore.csv".format(table),
                delete=False,
            )
            temp_path = Path(handle.name)
            with handle:
                writer = csv.writer(handle)
                for row in rows:
                    writer.writerow(["" if row_value(row, column) is None else row_value(row, column) for column in columns])
            copy_from(table, columns, temp_path, timeout=900)
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink()
                except Exception:
                    pass
    else:
        for row in rows:
            values = [sql_literal(row_value(row, column)) for column in columns]
            execute(
                "INSERT INTO {}({}) VALUES ({});".format(
                    table,
                    ",".join(columns),
                    ",".join(values),
                )
            )
    return len(rows)


def import_bundle(bundle_path, reset=False):
    bundle = load_import_bundle(bundle_path)
    if reset:
        reset_all_data()
    validate_bundle_duplicates(bundle, check_database=not reset)
    tables = bundle["tables"]
    inserted = {}
    for table in RESTORE_ORDER:
        inserted[table] = insert_rows(table, tables.get(table, []))
    object_layer = rebuild_object_proxies()
    return {
        "ok": True,
        "mode": "restore",
        "bundle": str(bundle_path),
        "manifest": bundle.get("manifest", {}),
        "inserted": inserted,
        "object_layer": object_layer,
    }


def ensure_generated_files(total=None):
    if total is not None or not all(path.exists() for path in GENERATED_FILES.values()):
        command = [sys.executable, str(APP_DIR / "generate_data.py")]
        if total is not None:
            command.append(str(total))
        subprocess.run(command, cwd=str(APP_DIR), check=True)


def reset_genealogy_data():
    try_execute("DELETE FROM object_proxies WHERE proxy_table IN ('genealogies','members','marriages');")
    try_execute("DELETE FROM objects WHERE object_type IN ('genealogy','member','marriage');")
    execute("DELETE FROM marriages;")
    execute("DELETE FROM members;")
    execute("DELETE FROM collaborations;")
    execute("DELETE FROM genealogies;")


def reset_all_data():
    try_execute("DELETE FROM object_proxies;")
    try_execute("DELETE FROM objects;")
    execute("DELETE FROM marriages;")
    execute("DELETE FROM members;")
    execute("DELETE FROM collaborations;")
    execute("DELETE FROM genealogies;")
    execute("DELETE FROM member_photos;")
    execute("DELETE FROM users;")


def rebuild_object_proxies():
    if not table_available("objects") or not table_available("object_proxies"):
        return {"ok": False, "skipped": True, "reason": "object tables are not available"}

    execute("DELETE FROM object_proxies;", timeout=300)
    execute("DELETE FROM objects;", timeout=300)

    user_offset = OBJECT_OFFSETS["user"]
    genealogy_offset = OBJECT_OFFSETS["genealogy"]
    member_offset = OBJECT_OFFSETS["member"]
    marriage_offset = OBJECT_OFFSETS["marriage"]

    execute(
        "INSERT INTO objects(object_id,object_type,display_name) "
        "SELECT {offset} + id, 'user', user_id FROM users;".format(offset=user_offset),
        timeout=300,
    )
    execute(
        "INSERT INTO object_proxies(proxy_id,object_id,proxy_table,proxy_pk,proxy_label) "
        "SELECT {offset} + id, {offset} + id, 'users', id, user_id FROM users;".format(offset=user_offset),
        timeout=300,
    )
    try_execute("UPDATE users SET object_id = {} + id;".format(user_offset), timeout=300)

    execute(
        "INSERT INTO objects(object_id,object_type,display_name) "
        "SELECT {offset} + clan_id, 'genealogy', title FROM genealogies;".format(offset=genealogy_offset),
        timeout=300,
    )
    execute(
        "INSERT INTO object_proxies(proxy_id,object_id,proxy_table,proxy_pk,proxy_label) "
        "SELECT {offset} + clan_id, {offset} + clan_id, 'genealogies', clan_id, title FROM genealogies;".format(
            offset=genealogy_offset
        ),
        timeout=300,
    )
    try_execute("UPDATE genealogies SET object_id = {} + clan_id;".format(genealogy_offset), timeout=300)

    execute(
        "INSERT INTO objects(object_id,object_type,display_name) "
        "SELECT {offset} + member_id, 'member', name FROM members;".format(offset=member_offset),
        timeout=600,
    )
    execute(
        "INSERT INTO object_proxies(proxy_id,object_id,proxy_table,proxy_pk,proxy_label) "
        "SELECT {offset} + member_id, {offset} + member_id, 'members', member_id, name FROM members;".format(
            offset=member_offset
        ),
        timeout=600,
    )
    try_execute("UPDATE members SET object_id = {} + member_id;".format(member_offset), timeout=600)

    execute(
        "INSERT INTO objects(object_id,object_type,display_name) "
        "SELECT {offset} + marriage_id, 'marriage', "
        "CAST(spouse_a_id AS VARCHAR) || '-' || CAST(spouse_b_id AS VARCHAR) FROM marriages;".format(
            offset=marriage_offset
        ),
        timeout=300,
    )
    execute(
        "INSERT INTO object_proxies(proxy_id,object_id,proxy_table,proxy_pk,proxy_label) "
        "SELECT {offset} + marriage_id, {offset} + marriage_id, 'marriages', marriage_id, "
        "CAST(spouse_a_id AS VARCHAR) || '-' || CAST(spouse_b_id AS VARCHAR) FROM marriages;".format(
            offset=marriage_offset
        ),
        timeout=300,
    )
    try_execute("UPDATE marriages SET object_id = {} + marriage_id;".format(marriage_offset), timeout=300)

    return {"ok": True, "skipped": False}


def import_generated_data(total=None, reset=True, creator_user_id="admin"):
    ensure_generated_files(total)
    if reset:
        reset_genealogy_data()
    copy_from("genealogies", ["clan_id", "title", "surname", "creator_id"], GENERATED_FILES["genealogies"])
    execute(
        "UPDATE genealogies SET creator_id = "
        "(SELECT id FROM users WHERE user_id = {} LIMIT 1);".format(sql_literal(creator_user_id))
    )
    copy_from(
        "members",
        ["member_id", "clan_id", "name", "gender", "birth_year", "death_year", "father_id", "mother_id", "generation_num", "bio"],
        GENERATED_FILES["members"],
    )
    copy_from(
        "marriages",
        ["marriage_id", "clan_id", "spouse_a_id", "spouse_b_id", "marry_year", "divorce_year"],
        GENERATED_FILES["marriages"],
    )
    execute(
        "INSERT INTO collaborations(clan_id, user_id) "
        "SELECT clan_id, creator_id FROM genealogies "
        "WHERE creator_id IS NOT NULL;"
    )
    object_layer = rebuild_object_proxies()
    return {
        "ok": True,
        "mode": "generated",
        "members_file": str(GENERATED_FILES["members"]),
        "marriages_file": str(GENERATED_FILES["marriages"]),
        "object_layer": object_layer,
    }


def read_member_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = []
        for index, row in enumerate(reader, start=1):
            normalized = {str(k).strip().lower(): (v.strip() if isinstance(v, str) else v) for k, v in row.items()}
            normalized["_row"] = index
            rows.append(normalized)
        return rows


def first_value(row, *keys):
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return ""


def import_clan_csv(csv_path, title, surname="", creator_user_id="admin"):
    csv_path = Path(csv_path)
    rows = read_member_csv(csv_path)
    if not rows:
        raise ValueError("CSV 文件没有成员数据")

    creator_id = optional_int(query_scalar("SELECT id FROM users WHERE user_id = {} LIMIT 1;".format(sql_literal(creator_user_id)), None))
    if creator_id is None:
        raise ValueError("未找到创建者用户 {}".format(creator_user_id))

    clan_id = int(query_scalar("SELECT COALESCE(MAX(clan_id), 0) + 1 FROM genealogies;"))
    next_member_id = int(query_scalar("SELECT COALESCE(MAX(member_id), 0) + 1 FROM members;"))
    next_marriage_id = int(query_scalar("SELECT COALESCE(MAX(marriage_id), 0) + 1 FROM marriages;"))

    execute(
        "INSERT INTO genealogies(clan_id,title,surname,creator_id) VALUES ({},{},{},{});".format(
            clan_id,
            sql_literal(title),
            sql_literal(surname),
            creator_id,
        )
    )
    execute("INSERT INTO collaborations(clan_id,user_id) VALUES ({},{});".format(clan_id, creator_id))

    id_map = {}
    prepared = []
    for row in rows:
        old_id = first_value(row, "member_id", "id", "编号")
        member_id = next_member_id
        next_member_id += 1
        if old_id:
            id_map[str(old_id)] = member_id
        prepared.append((row, member_id))

    parent_pairs = set()
    for row, member_id in prepared:
        father_raw = first_value(row, "father_id", "father", "父亲id")
        mother_raw = first_value(row, "mother_id", "mother", "母亲id")
        father_id = id_map.get(str(father_raw)) if father_raw else None
        mother_id = id_map.get(str(mother_raw)) if mother_raw else None
        if father_id and mother_id and father_id != mother_id:
            parent_pairs.add((father_id, mother_id))
        gender = (first_value(row, "gender", "sex", "性别") or "U").upper()
        if gender in ("男", "MALE"):
            gender = "M"
        elif gender in ("女", "FEMALE"):
            gender = "F"
        if gender not in ("M", "F", "U"):
            gender = "U"
        execute(
            "INSERT INTO members(member_id,clan_id,name,gender,birth_year,death_year,father_id,mother_id,generation_num,bio,id_pic) "
            "VALUES ({},{},{},{},{},{},{},{},{},{},{});".format(
                member_id,
                clan_id,
                sql_literal(first_value(row, "name", "姓名") or "未命名{}".format(member_id)),
                sql_literal(gender),
                sql_literal(optional_int(first_value(row, "birth_year", "birth", "出生年"))),
                sql_literal(optional_int(first_value(row, "death_year", "death", "死亡年"))),
                sql_literal(father_id),
                sql_literal(mother_id),
                sql_literal(optional_int(first_value(row, "generation_num", "generation", "世代"))),
                sql_literal(first_value(row, "bio", "简介")),
                sql_literal(first_value(row, "id_pic", "photo_sha256", "照片hash")),
            )
        )

    for father_id, mother_id in sorted(parent_pairs):
        father_birth = optional_int(query_scalar("SELECT birth_year FROM members WHERE member_id = {};".format(father_id), None))
        mother_birth = optional_int(query_scalar("SELECT birth_year FROM members WHERE member_id = {};".format(mother_id), None))
        child_birth = optional_int(query_scalar(
            "SELECT MIN(birth_year) FROM members WHERE father_id = {} AND mother_id = {};".format(father_id, mother_id),
            None,
        ))
        lower = max([year for year in (father_birth, mother_birth) if year] or [0]) + 18
        marry_year = lower
        if child_birth and marry_year >= child_birth:
            marry_year = child_birth - 1
        execute(
            "INSERT INTO marriages(marriage_id,clan_id,spouse_a_id,spouse_b_id,marry_year,divorce_year) "
            "VALUES ({},{},{},{},{},NULL);".format(next_marriage_id, clan_id, father_id, mother_id, sql_literal(marry_year or None))
        )
        next_marriage_id += 1

    object_layer = rebuild_object_proxies()
    return {
        "ok": True,
        "mode": "csv",
        "clan_id": clan_id,
        "members": len(prepared),
        "marriages": len(parent_pairs),
        "title": title,
        "object_layer": object_layer,
    }


def main():
    parser = argparse.ArgumentParser(description="导入族谱数据到 Totem genealogy 数据库")
    subparsers = parser.add_subparsers(dest="command")

    generated = subparsers.add_parser("generated", help="导入 generate_data.py 生成的整库数据")
    generated.add_argument("--total", type=int, default=None)
    generated.add_argument("--append", action="store_true", help="不清空现有族谱数据")
    generated.add_argument("--creator", default="admin")

    csv_parser = subparsers.add_parser("csv", help="基于成员 CSV 新建一个族谱")
    csv_parser.add_argument("csv_path")
    csv_parser.add_argument("--title", required=True)
    csv_parser.add_argument("--surname", default="")
    csv_parser.add_argument("--creator", default="admin")

    restore_parser = subparsers.add_parser("restore", help="导入 export.py 生成的 import_bundle.json")
    restore_parser.add_argument("bundle_path")
    restore_parser.add_argument("--reset", action="store_true", help="导入前清空 users/genealogies/collaborations/members/marriages/member_photos")

    args = parser.parse_args()
    try:
        if args.command == "generated":
            print(import_generated_data(total=args.total, reset=not args.append, creator_user_id=args.creator))
        elif args.command == "csv":
            print(import_clan_csv(args.csv_path, args.title, args.surname, args.creator))
        elif args.command == "restore":
            print(import_bundle(args.bundle_path, reset=args.reset))
        else:
            parser.print_help()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
