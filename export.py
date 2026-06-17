import argparse
import csv
import json
import os
import subprocess
from datetime import datetime
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = APP_DIR / "output"
EXPORT_DIR = OUTPUT_DIR / "export"
DATABASE = os.getenv("TOTEM_DATABASE", "genealogy")
TSQL = os.getenv("TOTEM_TSQL", "/usr/local/totem/bin/tsql")
TOTEM_PORT = os.getenv("TOTEM_PORT", "")
TOTEM_USER = os.getenv("TOTEM_USER", "totem")


BASE_EXPORT_TABLES = ("users", "genealogies", "collaborations", "members", "marriages", "member_photos")
OBJECT_SNAPSHOT_TABLES = ("objects", "object_proxies", "member_objects", "marriage_objects")
DEPUTY_SNAPSHOT_TABLES = (
    "father_down_edges",
    "mother_down_edges",
    "father_up_edges",
    "mother_up_edges",
    "spouse_a_edges",
    "spouse_b_edges",
    "male_50_plus",
    "living_members",
    "known_lifespan_members",
    "male_members",
    "female_members",
    "active_marriages",
    "divorced_marriages",
)


def run_tsql(args, timeout=300):
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
        output = completed.stderr.strip() or completed.stdout.strip() or "no output"
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


def copy_to(query, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output = run_tsql(["-A", "-F", "\t", "-c", query])
    lines = [line for line in output.splitlines() if line and not line.startswith("(")]
    if not lines:
        output_path.write_text("", encoding="utf-8", newline="")
        return
    reader = csv.reader(lines, delimiter="\t")
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerows(reader)


def query_rows(query):
    output = run_tsql(["-A", "-F", "\t", "-c", query])
    lines = [line for line in output.splitlines() if line and not line.startswith("(")]
    if not lines:
        return [], []
    reader = csv.DictReader(lines, delimiter="\t")
    return reader.fieldnames or [], list(reader)


def write_dict_rows(path, headers, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def read_csv_dict(path):
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def table_available(table):
    try:
        run_tsql(["-c", "SELECT 1 FROM {} LIMIT 1;".format(table)], timeout=30)
        return True
    except Exception:
        return False


def execute(sql, timeout=300):
    run_tsql(["-c", sql], timeout=timeout)


def try_execute(sql, timeout=300):
    try:
        execute(sql, timeout=timeout)
        return True
    except Exception:
        return False


def sync_deputy_objects():
    if not table_available("member_objects") or not table_available("marriage_objects"):
        return {"ok": False, "skipped": True, "reason": "Totem object classes are not available"}

    execute("DELETE FROM marriage_objects;", timeout=300)
    execute("DELETE FROM member_objects;", timeout=600)
    execute(
        "INSERT INTO member_objects(member_id,clan_id,name,gender,birth_year,death_year,father_id,mother_id,generation_num) "
        "SELECT member_id,clan_id,name,gender,birth_year,death_year,father_id,mother_id,generation_num "
        "FROM members;",
        timeout=900,
    )
    execute(
        "INSERT INTO marriage_objects(marriage_id,clan_id,spouse_a_id,spouse_b_id,marry_year,divorce_year) "
        "SELECT marriage_id,clan_id,spouse_a_id,spouse_b_id,marry_year,divorce_year "
        "FROM marriages;",
        timeout=600,
    )
    return {"ok": True, "skipped": False}


def export_table_if_available(target, table_name, query):
    if not table_available(table_name):
        return None
    try:
        file_name = table_name + ".csv"
        copy_to(query, target / file_name)
        return file_name
    except Exception:
        return None


def export_optional_snapshots(target, clan_filter=None):
    files = []
    for table_name in OBJECT_SNAPSHOT_TABLES:
        if clan_filter and table_name in {"member_objects", "marriage_objects"}:
            query = "SELECT * FROM {} WHERE clan_id IN ({}) ORDER BY 1".format(table_name, clan_filter)
        else:
            query = "SELECT * FROM {} ORDER BY 1".format(table_name)
        file_name = export_table_if_available(target, table_name, query)
        if file_name:
            files.append(file_name)
    return files


def export_deputy_snapshots(target, clan_filter=None):
    files = []
    for table_name in DEPUTY_SNAPSHOT_TABLES:
        if clan_filter:
            query = "SELECT * FROM {} WHERE clan_id IN ({}) ORDER BY 1".format(table_name, clan_filter)
        else:
            query = "SELECT * FROM {} ORDER BY 1".format(table_name)
        file_name = export_table_if_available(target, table_name, query)
        if file_name:
            files.append(file_name)
    return files


def write_import_bundle(target, manifest):
    tables = {}
    for table_name in BASE_EXPORT_TABLES:
        csv_path = target / (table_name + ".csv")
        if csv_path.exists():
            tables[table_name] = read_csv_dict(csv_path)
    bundle = {
        "format": "totem-genealogy-import-bundle",
        "format_version": 1,
        "manifest": manifest,
        "tables": tables,
    }
    bundle_path = target / "import_bundle.json"
    bundle_path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    return bundle_path


def timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def export_manifest(target, manifest):
    write_import_bundle(target, manifest)
    (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def export_database(output_dir=None):
    target = Path(output_dir) if output_dir else EXPORT_DIR / ("database_" + timestamp())
    target.mkdir(parents=True, exist_ok=True)

    files = []
    deputy_sync = sync_deputy_objects()
    snapshot_files = export_optional_snapshots(target) + export_deputy_snapshots(target)
    files.extend(snapshot_files)

    copy_to("SELECT * FROM users ORDER BY id", target / "users.csv")
    copy_to("SELECT * FROM genealogies ORDER BY clan_id", target / "genealogies.csv")
    copy_to("SELECT * FROM collaborations ORDER BY clan_id,user_id", target / "collaborations.csv")
    copy_to("SELECT * FROM members ORDER BY clan_id,generation_num,member_id", target / "members.csv")
    copy_to("SELECT * FROM marriages ORDER BY clan_id,marriage_id", target / "marriages.csv")
    files.extend(["users.csv", "genealogies.csv", "collaborations.csv", "members.csv", "marriages.csv"])
    try:
        copy_to("SELECT * FROM member_photos ORDER BY photo_sha256", target / "member_photos.csv")
        files.append("member_photos.csv")
    except Exception:
        pass

    manifest = {
        "type": "database",
        "database": DATABASE,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "files": files,
        "base_tables": list(BASE_EXPORT_TABLES),
        "snapshot_files": snapshot_files,
        "import_file": "import_bundle.json",
        "import_rebuilds": ["objects", "object_proxies", "member_objects", "marriage_objects", "select_deputy_classes"],
        "deputy_sync": deputy_sync,
    }
    export_manifest(target, manifest)
    return {"ok": True, "type": "database", "output_dir": str(target), "deputy_sync": deputy_sync}


def export_clans(clan_ids, output_dir=None):
    ids = [int(item) for item in clan_ids if str(item).strip()]
    if not ids:
        raise ValueError("至少需要选择一个族谱")
    id_list = ",".join(str(item) for item in sorted(set(ids)))
    target = Path(output_dir) if output_dir else EXPORT_DIR / ("clans_" + timestamp())
    target.mkdir(parents=True, exist_ok=True)

    files = []
    deputy_sync = sync_deputy_objects()
    snapshot_files = export_optional_snapshots(target, id_list) + export_deputy_snapshots(target, id_list)
    files.extend(snapshot_files)

    copy_to("SELECT * FROM genealogies WHERE clan_id IN ({}) ORDER BY clan_id".format(id_list), target / "genealogies.csv")
    copy_to("SELECT * FROM collaborations WHERE clan_id IN ({}) ORDER BY clan_id,user_id".format(id_list), target / "collaborations.csv")
    copy_to("SELECT * FROM members WHERE clan_id IN ({}) ORDER BY clan_id,generation_num,member_id".format(id_list), target / "members.csv")
    copy_to("SELECT * FROM marriages WHERE clan_id IN ({}) ORDER BY clan_id,marriage_id".format(id_list), target / "marriages.csv")
    files.extend(["users.csv", "genealogies.csv", "collaborations.csv", "members.csv", "marriages.csv"])
    try:
        copy_to(
            "SELECT p.* FROM member_photos p JOIN members m ON m.id_pic = p.photo_sha256 "
            "WHERE m.clan_id IN ({}) ORDER BY p.photo_sha256".format(id_list),
            target / "member_photos.csv",
        )
        files.append("member_photos.csv")
    except Exception:
        pass
    copy_to(
        "SELECT DISTINCT u.* FROM users u "
        "JOIN ("
        "SELECT creator_id AS user_id FROM genealogies WHERE clan_id IN ({ids}) "
        "UNION SELECT user_id FROM collaborations WHERE clan_id IN ({ids})"
        ") r ON r.user_id = u.id ORDER BY u.id".format(ids=id_list),
        target / "users.csv",
    )

    manifest = {
        "type": "clans",
        "database": DATABASE,
        "clan_ids": sorted(set(ids)),
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "files": files,
        "base_tables": list(BASE_EXPORT_TABLES),
        "snapshot_files": snapshot_files,
        "import_file": "import_bundle.json",
        "import_rebuilds": ["objects", "object_proxies", "member_objects", "marriage_objects", "select_deputy_classes"],
        "deputy_sync": deputy_sync,
    }
    export_manifest(target, manifest)
    return {"ok": True, "type": "clans", "clan_ids": sorted(set(ids)), "output_dir": str(target), "deputy_sync": deputy_sync}


def export_member_ancestors(member_id, path):
    headers = ["member_id", "name", "gender", "birth_year", "death_year", "father_id", "mother_id", "generation_num", "depth"]
    result = []
    queue = [(int(member_id), 0)]
    seen = {int(member_id)}
    while queue:
        current_id, depth = queue.pop(0)
        _, rows = query_rows(
            "SELECT member_id,name,gender,birth_year,death_year,father_id,mother_id,generation_num "
            "FROM members WHERE member_id = {}".format(current_id)
        )
        if not rows:
            continue
        row = rows[0]
        if depth > 0:
            item = {key: row.get(key, "") for key in headers}
            item["depth"] = depth
            result.append(item)
        for key in ("father_id", "mother_id"):
            parent = row.get(key)
            if parent and parent != "NULL":
                parent_id = int(parent)
                if parent_id not in seen:
                    seen.add(parent_id)
                    queue.append((parent_id, depth + 1))
    write_dict_rows(path, headers, result)


def export_member(member_id, output_dir=None):
    member_id = int(member_id)
    target = Path(output_dir) if output_dir else EXPORT_DIR / ("member_{}_{}".format(member_id, timestamp()))
    target.mkdir(parents=True, exist_ok=True)
    copy_to("SELECT * FROM members WHERE member_id = {}".format(member_id), target / "member.csv")
    copy_to(
        "SELECT g.* FROM genealogies g JOIN members m ON m.clan_id = g.clan_id WHERE m.member_id = {}".format(member_id),
        target / "genealogy.csv",
    )
    copy_to(
        "SELECT p.* FROM members m JOIN members p ON p.member_id = m.father_id OR p.member_id = m.mother_id "
        "WHERE m.member_id = {} ORDER BY p.member_id".format(member_id),
        target / "parents.csv",
    )
    copy_to(
        "SELECT * FROM members WHERE father_id = {mid} OR mother_id = {mid} ORDER BY generation_num,member_id".format(mid=member_id),
        target / "children.csv",
    )
    copy_to(
        "SELECT * FROM marriages WHERE spouse_a_id = {mid} OR spouse_b_id = {mid} ORDER BY marriage_id".format(mid=member_id),
        target / "marriages.csv",
    )
    copy_to(
        "SELECT s.* FROM marriages mg JOIN members s ON "
        "s.member_id = CASE WHEN mg.spouse_a_id = {mid} THEN mg.spouse_b_id ELSE mg.spouse_a_id END "
        "WHERE mg.spouse_a_id = {mid} OR mg.spouse_b_id = {mid} ORDER BY s.member_id".format(mid=member_id),
        target / "spouses.csv",
    )
    files = ["member.csv", "genealogy.csv", "parents.csv", "children.csv", "marriages.csv", "spouses.csv", "ancestors.csv"]
    try:
        copy_to(
            "SELECT p.* FROM member_photos p JOIN members m ON m.id_pic = p.photo_sha256 "
            "WHERE m.member_id = {}".format(member_id),
            target / "member_photos.csv",
        )
        files.append("member_photos.csv")
    except Exception:
        pass
    export_member_ancestors(member_id, target / "ancestors.csv")
    manifest = {
        "type": "member",
        "database": DATABASE,
        "member_id": member_id,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "files": files,
    }
    (target / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "type": "member", "member_id": member_id, "output_dir": str(target)}


def main():
    parser = argparse.ArgumentParser(description="导出 Totem genealogy 数据库")
    subparsers = parser.add_subparsers(dest="command")

    all_parser = subparsers.add_parser("all", help="导出整个数据库")
    all_parser.add_argument("--output", default=None)

    clans_parser = subparsers.add_parser("clans", help="导出一个或多个族谱")
    clans_parser.add_argument("clan_ids", nargs="+")
    clans_parser.add_argument("--output", default=None)

    member_parser = subparsers.add_parser("member", help="导出单个成员对象的所有关联信息")
    member_parser.add_argument("member_id")
    member_parser.add_argument("--output", default=None)

    args = parser.parse_args()
    if args.command == "all":
        print(export_database(args.output))
    elif args.command == "clans":
        print(export_clans(args.clan_ids, args.output))
    elif args.command == "member":
        print(export_member(args.member_id, args.output))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
