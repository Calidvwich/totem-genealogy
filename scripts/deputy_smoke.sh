#!/usr/bin/env bash
set -euo pipefail

DB="${1:-genealogy_deputy_smoke}"
PORT="${TOTEM_PORT:-55432}"
USER_NAME="${TOTEM_USER:-totem}"
TSQL="${TOTEM_TSQL:-/usr/local/totem/bin/tsql}"
CREATEDB="${TOTEM_CREATEDB:-/usr/local/totem/bin/createdb}"
DROPDB="${TOTEM_DROPDB:-/usr/local/totem/bin/dropdb}"
DROP_LOG="/tmp/${DB}_deputy_smoke_drop.log"
DROP_FINAL_LOG="/tmp/${DB}_deputy_smoke_drop_final.log"

cd "$(dirname "$0")/.."

"$DROPDB" -p "$PORT" -U "$USER_NAME" "$DB" >"$DROP_LOG" 2>&1 || true
"$CREATEDB" -p "$PORT" -U "$USER_NAME" "$DB"
if [ "${KEEP_DEPUTY_SMOKE_DB:-0}" != "1" ]; then
  trap '"$DROPDB" -p "$PORT" -U "$USER_NAME" "$DB" >"$DROP_FINAL_LOG" 2>&1 || true' EXIT
fi
"$TSQL" -U "$USER_NAME" -p "$PORT" -d "$DB" -f init_db.sql
export TOTEM_DATABASE="$DB"
export TOTEM_USER="$USER_NAME"
export TOTEM_PORT="$PORT"
. .venv/bin/activate
python import.py restore fulldb/import_bundle.json --reset

"$TSQL" -U "$USER_NAME" -p "$PORT" -d "$DB" -c "
SELECT 'member_objects' AS deputy_class, COUNT(*) FROM member_objects
UNION ALL SELECT 'marriage_objects', COUNT(*) FROM marriage_objects
UNION ALL SELECT 'father_down_edges', COUNT(*) FROM father_down_edges
UNION ALL SELECT 'mother_down_edges', COUNT(*) FROM mother_down_edges
UNION ALL SELECT 'father_up_edges', COUNT(*) FROM father_up_edges
UNION ALL SELECT 'mother_up_edges', COUNT(*) FROM mother_up_edges
UNION ALL SELECT 'spouse_a_edges', COUNT(*) FROM spouse_a_edges
UNION ALL SELECT 'spouse_b_edges', COUNT(*) FROM spouse_b_edges
UNION ALL SELECT 'male_50_plus', COUNT(*) FROM male_50_plus
UNION ALL SELECT 'living_members', COUNT(*) FROM living_members
UNION ALL SELECT 'known_lifespan_members', COUNT(*) FROM known_lifespan_members
UNION ALL SELECT 'male_members', COUNT(*) FROM male_members
UNION ALL SELECT 'female_members', COUNT(*) FROM female_members
UNION ALL SELECT 'active_marriages', COUNT(*) FROM active_marriages
UNION ALL SELECT 'divorced_marriages', COUNT(*) FROM divorced_marriages
ORDER BY deputy_class;
"
