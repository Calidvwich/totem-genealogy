import os
import subprocess
import sys
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
DATABASE = os.getenv("TOTEM_DATABASE", "genealogy")
TSQL = os.getenv("TOTEM_TSQL", "/usr/local/totem/bin/tsql")
TOTEM_PORT = os.getenv("TOTEM_PORT", "")
TOTEM_USER = os.getenv("TOTEM_USER", "totem")


def run_tsql(args):
    command = [TSQL]
    if TOTEM_PORT:
        command.extend(["-p", TOTEM_PORT])
    if TOTEM_USER:
        command.extend(["-U", TOTEM_USER])
    command.extend(["-d", DATABASE, *args])
    completed = subprocess.run(command, cwd=APP_DIR, universal_newlines=True)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main() -> None:
    genealogies_csv = APP_DIR / "genealogies_load.csv"
    members_csv = APP_DIR / "members_load.csv"
    marriages_csv = APP_DIR / "marriages_load.csv"
    if not members_csv.exists() or not marriages_csv.exists() or not genealogies_csv.exists():
        subprocess.run([sys.executable, str(APP_DIR / "generate_data.py")], check=True)

    if os.getenv("TOTEM_INIT_SCHEMA") == "1":
        run_tsql(["-f", str(APP_DIR / "init_db.sql")])

    run_tsql(["-c", "DELETE FROM marriages;"])
    run_tsql(["-c", "DELETE FROM members;"])
    run_tsql(["-c", "DELETE FROM collaborations;"])
    run_tsql(["-c", "DELETE FROM genealogies;"])
    run_tsql(["-c", "UPDATE users SET password_hash = '123456', username = '管理员' WHERE user_id = 'admin';"])
    run_tsql([
        "-c",
        "INSERT INTO users(id, user_id, password_hash, username) "
        "SELECT 1, 'admin', '123456', '管理员' "
        "WHERE NOT EXISTS (SELECT 1 FROM users WHERE user_id = 'admin');",
    ])

    copy_genealogies_sql = (
        "\\COPY genealogies(clan_id, title, surname, creator_id) "
        f"FROM '{genealogies_csv}' WITH CSV NULL ''"
    )
    run_tsql(["-c", copy_genealogies_sql])
    run_tsql(["-c", "UPDATE genealogies SET creator_id = (SELECT id FROM users WHERE user_id = 'admin');"])

    copy_members_sql = (
        "\\COPY members(member_id, clan_id, name, gender, birth_year, death_year, "
        "father_id, mother_id, generation_num, bio) "
        f"FROM '{members_csv}' WITH CSV NULL ''"
    )
    run_tsql(["-c", copy_members_sql])

    copy_marriages_sql = (
        "\\COPY marriages(marriage_id, clan_id, spouse_a_id, spouse_b_id, marry_year, divorce_year) "
        f"FROM '{marriages_csv}' WITH CSV NULL ''"
    )
    run_tsql(["-c", copy_marriages_sql])
    run_tsql([
        "-c",
        "INSERT INTO collaborations(clan_id, user_id) "
        "SELECT clan_id, (SELECT id FROM users WHERE user_id = 'admin') FROM genealogies;",
    ])


if __name__ == "__main__":
    main()
