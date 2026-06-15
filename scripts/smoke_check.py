"""用途：执行只读 smoke 检查；默认只读文件，可选只读 API 和只读 SQL。"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Tuple
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
    "queries.md",
    "verify_dataset.sql",
    "generate_data.py",
    "load_db.py",
    "docs/code_audit.md",
    "docs/database_design_review.md",
    "docs/api_route_map.md",
    "docs/manual_test_plan.md",
    "docs/references.md",
    "scripts/schema_readonly_check.sql",
    "resources/defaultpic.jpg",
]

EXPECTED_TABLES = [
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


def strip_sql_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    lines = []
    for line in sql.splitlines():
        lines.append(line.split("--", 1)[0])
    return "\n".join(lines)


def pass_item(message: str) -> Tuple[bool, str]:
    return True, "[PASS] " + message


def fail_item(message: str) -> Tuple[bool, str]:
    return False, "[FAIL] " + message


def check_required_files() -> List[Tuple[bool, str]]:
    results = []
    for relative in REQUIRED_FILES:
        path = ROOT / relative
        if path.exists():
            results.append(pass_item(f"存在 {relative}"))
        else:
            results.append(fail_item(f"缺少 {relative}"))
    return results


def check_readonly_sql() -> List[Tuple[bool, str]]:
    if not READONLY_SQL.exists():
        return [fail_item("缺少 scripts/schema_readonly_check.sql")]

    text = READONLY_SQL.read_text(encoding="utf-8")
    executable = strip_sql_comments(text)
    if FORBIDDEN_SQL.search(executable):
        return [fail_item("schema_readonly_check.sql 出现非只读 SQL 关键字")]

    statements = [part.strip() for part in executable.split(";") if part.strip()]
    if not statements:
        return [fail_item("schema_readonly_check.sql 没有可执行查询")]

    results = []
    for index, statement in enumerate(statements, start=1):
        if statement.upper().startswith("SELECT"):
            results.append(pass_item(f"SQL 语句 {index} 以 SELECT 开头"))
        else:
            results.append(fail_item(f"SQL 语句 {index} 不是 SELECT 开头"))
    return results


def check_schema_file() -> List[Tuple[bool, str]]:
    schema_path = ROOT / "init_db.sql"
    text = schema_path.read_text(encoding="utf-8")
    results = []
    for table in EXPECTED_TABLES:
        marker = f"CREATE TABLE {table}"
        if marker in text:
            results.append(pass_item(f"init_db.sql 定义 {table}"))
        else:
            results.append(fail_item(f"init_db.sql 未找到 {table}"))
    for marker in ["PRIMARY KEY", "UNIQUE NOT NULL", "CHECK"]:
        if marker in text:
            results.append(pass_item(f"init_db.sql 包含 {marker}"))
        else:
            results.append(fail_item(f"init_db.sql 缺少 {marker}"))
    return results


def check_routes() -> List[Tuple[bool, str]]:
    main_text = (ROOT / "main.py").read_text(encoding="utf-8")
    results = []
    for route in EXPECTED_ROUTES:
        if route in main_text:
            results.append(pass_item(f"main.py 包含路由 {route}"))
        else:
            results.append(fail_item(f"main.py 缺少路由 {route}"))
    return results


def check_api(base_url: str, timeout: float) -> List[Tuple[bool, str]]:
    results = []
    normalized = base_url.rstrip("/") + "/"
    for path in SAFE_GET_PATHS:
        url = urljoin(normalized, path.lstrip("/"))
        request = Request(url, method="GET")
        try:
            with urlopen(request, timeout=timeout) as response:
                status = response.getcode()
                if 200 <= status < 300:
                    results.append(pass_item(f"GET {path} -> {status}"))
                else:
                    results.append(fail_item(f"GET {path} -> {status}"))
        except HTTPError as exc:
            results.append(fail_item(f"GET {path} -> HTTP {exc.code}"))
        except URLError as exc:
            results.append(fail_item(f"GET {path} 连接失败：{exc.reason}"))
        except TimeoutError:
            results.append(fail_item(f"GET {path} 超时"))
    return results


def run_readonly_sql(timeout: int) -> List[Tuple[bool, str]]:
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
        return [fail_item(f"找不到 tsql：{tsql}")]
    except subprocess.TimeoutExpired:
        return [fail_item("执行只读 SQL 超时")]

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip().splitlines()
        suffix = f"：{detail[0]}" if detail else ""
        return [fail_item("只读 SQL 执行失败" + suffix)]

    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    return [pass_item(f"只读 SQL 执行成功，输出 {len(lines)} 行")]


def report(results: Iterable[Tuple[bool, str]]) -> int:
    failed = 0
    for ok, message in results:
        print(message)
        if not ok:
            failed += 1
    if failed:
        print(f"\n结果：{failed} 项失败")
        return 1
    print("\n结果：全部通过")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Totem 族谱项目只读 smoke 检查")
    parser.add_argument("--base-url", help="可选：对运行中的 Web 服务执行只读 GET 检查")
    parser.add_argument("--api-timeout", type=float, default=5.0, help="API 请求超时时间，默认 5 秒")
    parser.add_argument("--run-sql", action="store_true", help="可选：用 tsql 执行只读 SQL 检查")
    parser.add_argument("--sql-timeout", type=int, default=60, help="只读 SQL 执行超时时间，默认 60 秒")
    args = parser.parse_args()

    results: List[Tuple[bool, str]] = []
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
