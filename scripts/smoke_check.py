"""Read-only smoke checks for the Totem genealogy project.

The script is intentionally Python 3.6 compatible because the WSL test
environment currently uses Ubuntu 18.04.
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
READONLY_SQL = ROOT / "scripts" / "schema_readonly_check.sql"

REQUIRED_FILES = [
    "README.md",
    "main.py",
    "interface.py",
    "init_db.sql",
    "instructions/queries.md",
    "verify_dataset.sql",
    "generate_data.py",
    "load_db.py",
    "resources/defaultpic.jpg",
]

EXPECTED_TABLES = [
    "objects",
    "object_proxies",
    "users",
    "genealogies",
    "collaborations",
    "members",
    "marriages",
    "member_photos",
]

EXPECTED_ROUTES = [
    '"/"',
    '"/api/login"',
    '"/api/users"',
    '"/api/clans"',
    '"/api/members"',
    '"/api/tree"',
    '"/api/query/spouse_children"',
    '"/api/import/bundle"',
    '"/api/export/database"',
]

SAFE_GET_PATHS = [
    "/",
    "/api/clans",
    "/api/dashboard",
    "/api/members?clan_id=1",
    "/api/tree?clan_id=1",
]

FORBIDDEN_SQL = re.compile(
    r"\b(ALTER|CREATE|DELETE|DROP|GRANT|INSERT|MERGE|REPLACE|REVOKE|TRUNCATE|UPDATE)\b|\\COPY",
    re.IGNORECASE,
)


def strip_sql_comments(sql):
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    lines = []
    for line in sql.splitlines():
        lines.append(line.split("--", 1)[0])
    return "\n".join(lines)


def pass_item(message):
    return True, "[PASS] " + message


def fail_item(message):
    return False, "[FAIL] " + message


def check_required_files():
    results = []
    for relative in REQUIRED_FILES:
        path = ROOT / relative
        if path.exists():
            results.append(pass_item("file exists: {}".format(relative)))
        else:
            results.append(fail_item("missing file: {}".format(relative)))
    return results


def check_readonly_sql():
    if not READONLY_SQL.exists():
        return [fail_item("missing scripts/schema_readonly_check.sql")]

    text = READONLY_SQL.read_text(encoding="utf-8")
    executable = strip_sql_comments(text)
    if FORBIDDEN_SQL.search(executable):
        return [fail_item("schema_readonly_check.sql contains non-read-only SQL")]

    statements = [part.strip() for part in executable.split(";") if part.strip()]
    if not statements:
        return [fail_item("schema_readonly_check.sql has no executable SELECT")]

    results = []
    for index, statement in enumerate(statements, start=1):
        if statement.upper().startswith("SELECT"):
            results.append(pass_item("SQL statement {} starts with SELECT".format(index)))
        else:
            results.append(fail_item("SQL statement {} is not SELECT".format(index)))
    return results


def check_schema_file():
    schema_path = ROOT / "init_db.sql"
    text = schema_path.read_text(encoding="utf-8")
    results = []
    for table in EXPECTED_TABLES:
        marker = "CREATE TABLE {}".format(table)
        if marker in text:
            results.append(pass_item("init_db.sql defines {}".format(table)))
        else:
            results.append(fail_item("init_db.sql does not define {}".format(table)))
    for marker in ("PRIMARY KEY", "UNIQUE NOT NULL", "CHECK"):
        if marker in text:
            results.append(pass_item("init_db.sql contains {}".format(marker)))
        else:
            results.append(fail_item("init_db.sql lacks {}".format(marker)))
    return results


def check_routes():
    main_text = (ROOT / "main.py").read_text(encoding="utf-8")
    results = []
    for route in EXPECTED_ROUTES:
        if route in main_text:
            results.append(pass_item("main.py contains route {}".format(route)))
        else:
            results.append(fail_item("main.py lacks route {}".format(route)))
    return results


def check_api(base_url, timeout):
    results = []
    normalized = base_url.rstrip("/") + "/"
    for path in SAFE_GET_PATHS:
        url = urljoin(normalized, path.lstrip("/"))
        request = Request(url, method="GET")
        try:
            with urlopen(request, timeout=timeout) as response:
                status = response.getcode()
                if 200 <= status < 300:
                    results.append(pass_item("GET {} -> {}".format(path, status)))
                else:
                    results.append(fail_item("GET {} -> {}".format(path, status)))
        except HTTPError as exc:
            results.append(fail_item("GET {} -> HTTP {}".format(path, exc.code)))
        except URLError as exc:
            results.append(fail_item("GET {} connection failed: {}".format(path, exc.reason)))
        except TimeoutError:
            results.append(fail_item("GET {} timed out".format(path)))
    return results


def run_readonly_sql(timeout):
    check_result = check_readonly_sql()
    if not all(ok for ok, _ in check_result):
        return check_result

    tsql = os.getenv("TOTEM_TSQL", "/usr/local/totem/bin/tsql")
    database = os.getenv("TOTEM_DATABASE", "genealogy")
    port = os.getenv("TOTEM_PORT", "")
    user = os.getenv("TOTEM_USER", "totem")

    command = [tsql]
    if port:
        command.extend(["-p", port])
    if user:
        command.extend(["-U", user])
    command.extend(["-d", database, "-f", str(READONLY_SQL)])

    try:
        completed = subprocess.run(
            command,
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            check=False,
            timeout=timeout,
        )
    except FileNotFoundError:
        return [fail_item("tsql not found: {}".format(tsql))]
    except subprocess.TimeoutExpired:
        return [fail_item("read-only SQL timed out")]

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip().splitlines()
        suffix = ": {}".format(detail[0]) if detail else ""
        return [fail_item("read-only SQL failed" + suffix)]

    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    return [pass_item("read-only SQL succeeded, output lines: {}".format(len(lines)))]


def report(results):
    failed = 0
    for ok, message in results:
        print(message)
        if not ok:
            failed += 1
    if failed:
        print("\nResult: {} failed".format(failed))
        return 1
    print("\nResult: all passed")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Totem genealogy smoke checks")
    parser.add_argument("--base-url", help="Optional running web service base URL")
    parser.add_argument("--api-timeout", type=float, default=5.0)
    parser.add_argument("--run-sql", action="store_true")
    parser.add_argument("--sql-timeout", type=int, default=60)
    args = parser.parse_args()

    results = []
    results.extend(check_required_files())
    results.extend(check_readonly_sql())
    results.extend(check_schema_file())
    results.extend(check_routes())

    if args.base_url:
        results.extend(check_api(args.base_url, args.api_timeout))
    if args.run_sql:
        results.extend(run_readonly_sql(args.sql_timeout))

    return report(results)


if __name__ == "__main__":
    sys.exit(main())
