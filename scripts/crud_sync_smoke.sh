#!/usr/bin/env bash
set -euo pipefail

DB="${1:-genealogy_crud_sync_smoke}"
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
export TOTEM_USE_DEMO=0

. .venv/bin/activate
python - <<'PY'
import main

svc = main.service
svc.create_member(main.MemberIn(clan_id=1, name="父_1_1", gender="M", birth_year=1970, generation_num=1))
svc.create_member(main.MemberIn(clan_id=1, name="母_1_2", gender="F", birth_year=1972, generation_num=1))
child = svc.create_member(
    main.MemberIn(
        clan_id=1,
        name="子_2_1",
        gender="M",
        birth_year=1995,
        father_id=1,
        mother_id=2,
        generation_num=2,
    )
)
print("created_child={}".format(child["member_id"]))
PY

"$TSQL" -U "$USER_NAME" -p "$PORT" -d "$DB" -A -t -c "
SELECT 'member_objects', COUNT(*) FROM member_objects
UNION ALL SELECT 'marriage_objects', COUNT(*) FROM marriage_objects
UNION ALL SELECT 'father_down_edges', COUNT(*) FROM father_down_edges
UNION ALL SELECT 'mother_down_edges', COUNT(*) FROM mother_down_edges
UNION ALL SELECT 'spouse_a_edges', COUNT(*) FROM spouse_a_edges;
"
