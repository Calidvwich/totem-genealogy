import argparse
import csv
import os
import subprocess
import sys
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
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
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


def copy_from(table, columns, path, timeout=300):
    statement = "\\COPY {}({}) FROM '{}' WITH CSV NULL ''".format(
        table,
        ",".join(columns),
        str(path).replace("\\", "/").replace("'", "''"),
    )
    run_tsql(["-c", statement], timeout=timeout)


def ensure_generated_files(total=None):
    if total is not None or not all(path.exists() for path in GENERATED_FILES.values()):
        command = [sys.executable, str(APP_DIR / "generate_data.py")]
        if total is not None:
            command.append(str(total))
        subprocess.run(command, cwd=str(APP_DIR), check=True)


def reset_genealogy_data():
    execute("DELETE FROM marriages;")
    execute("DELETE FROM members;")
    execute("DELETE FROM collaborations;")
    execute("DELETE FROM genealogies;")


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
    return {
        "ok": True,
        "mode": "generated",
        "members_file": str(GENERATED_FILES["members"]),
        "marriages_file": str(GENERATED_FILES["marriages"]),
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

    return {
        "ok": True,
        "mode": "csv",
        "clan_id": clan_id,
        "members": len(prepared),
        "marriages": len(parent_pairs),
        "title": title,
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

    args = parser.parse_args()
    if args.command == "generated":
        print(import_generated_data(total=args.total, reset=not args.append, creator_user_id=args.creator))
    elif args.command == "csv":
        print(import_clan_csv(args.csv_path, args.title, args.surname, args.creator))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
