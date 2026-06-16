#!/usr/bin/env bash
set -euo pipefail

DB="${1:-genealogy_smoke_codex}"
PORT="${TOTEM_PORT:-55432}"
USER_NAME="${TOTEM_USER:-totem}"
TSQL="${TOTEM_TSQL:-/usr/local/totem/bin/tsql}"
CREATEDB="${TOTEM_CREATEDB:-/usr/local/totem/bin/createdb}"
DROPDB="${TOTEM_DROPDB:-/usr/local/totem/bin/dropdb}"

cd "$(dirname "$0")/.."

"$DROPDB" -p "$PORT" -U "$USER_NAME" "$DB" >/tmp/genealogy_restore_smoke_drop.log 2>&1 || true
"$CREATEDB" -p "$PORT" -U "$USER_NAME" "$DB"
"$TSQL" -U "$USER_NAME" -p "$PORT" -d "$DB" -f init_db.sql

export TOTEM_DATABASE="$DB"
export TOTEM_USER="$USER_NAME"
export TOTEM_PORT="$PORT"

. .venv/bin/activate
python import.py restore fulldb/import_bundle.json --reset

"$TSQL" -U "$USER_NAME" -p "$PORT" -d "$DB" -c "
SELECT 'users' AS table_name, COUNT(*) FROM users
UNION ALL SELECT 'genealogies', COUNT(*) FROM genealogies
UNION ALL SELECT 'members', COUNT(*) FROM members
UNION ALL SELECT 'marriages', COUNT(*) FROM marriages
UNION ALL SELECT 'objects', COUNT(*) FROM objects
UNION ALL SELECT 'object_proxies', COUNT(*) FROM object_proxies
ORDER BY table_name;
"

"$TSQL" -U "$USER_NAME" -p "$PORT" -d "$DB" -c "
SELECT proxy_table, COUNT(*) FROM object_proxies
GROUP BY proxy_table
ORDER BY proxy_table;
"
