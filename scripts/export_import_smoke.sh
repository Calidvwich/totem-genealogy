#!/usr/bin/env bash
set -euo pipefail

BUNDLE_PATH="${1:-/tmp/genealogy_export_clan_test/import_bundle.json}"
DB="${2:-genealogy_export_import_smoke}"
PORT="${TOTEM_PORT:-55432}"
USER_NAME="${TOTEM_USER:-totem}"
TSQL="${TOTEM_TSQL:-/usr/local/totem/bin/tsql}"
CREATEDB="${TOTEM_CREATEDB:-/usr/local/totem/bin/createdb}"
DROPDB="${TOTEM_DROPDB:-/usr/local/totem/bin/dropdb}"

cd "$(dirname "$0")/.."

"$DROPDB" -p "$PORT" -U "$USER_NAME" "$DB" >/tmp/"${DB}"_drop.log 2>&1 || true
"$CREATEDB" -p "$PORT" -U "$USER_NAME" "$DB"
trap '"$DROPDB" -p "$PORT" -U "$USER_NAME" "$DB" >/tmp/"${DB}"_drop_final.log 2>&1 || true' EXIT

"$TSQL" -U "$USER_NAME" -p "$PORT" -d "$DB" -f init_db.sql >/tmp/"${DB}"_init.log

export TOTEM_DATABASE="$DB"
export TOTEM_PORT="$PORT"
export TOTEM_USER="$USER_NAME"
. .venv/bin/activate
python import.py restore "$BUNDLE_PATH" --reset

"$TSQL" -U "$USER_NAME" -p "$PORT" -d "$DB" -A -t -c "
SELECT 'members', COUNT(1) FROM members
UNION ALL SELECT 'member_objects', COUNT(1) FROM member_objects
UNION ALL SELECT 'marriages', COUNT(1) FROM marriages
UNION ALL SELECT 'marriage_objects', COUNT(1) FROM marriage_objects
UNION ALL SELECT 'father_down_edges', COUNT(1) FROM father_down_edges;
"
