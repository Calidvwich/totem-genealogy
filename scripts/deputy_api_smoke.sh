#!/usr/bin/env bash
set -euo pipefail

PORT="${API_PORT:-8012}"
DB="${TOTEM_DATABASE:-genealogy_deputy_api_smoke}"
cd "$(dirname "$0")/.."

export TOTEM_USE_DEMO=0
export TOTEM_DATABASE="$DB"
export TOTEM_USER="${TOTEM_USER:-totem}"
export TOTEM_PORT="${TOTEM_PORT:-55432}"

. .venv/bin/activate
python -m uvicorn main:app --host 127.0.0.1 --port "$PORT" >/tmp/deputy-api-smoke.log 2>&1 &
PID=$!
trap 'kill "$PID" >/dev/null 2>&1 || true; wait "$PID" >/dev/null 2>&1 || true' EXIT

for _ in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS "http://127.0.0.1:${PORT}/" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

python3 - "$PORT" <<'PY'
import json
import sys
import urllib.parse
import urllib.request

port = sys.argv[1]
base = "http://127.0.0.1:{}".format(port)
checks = [
    "/api/query/spouse_children?member_id=1",
    "/api/query/ancestors?member_id=14378",
    "/api/members/1/relationship?target_id=14378",
    "/api/query/longevity?clan_id=1",
    "/api/query/singles?clan_id=1",
    "/api/query/great_grandchildren?member_id=1",
]
for path in checks:
    data = urllib.request.urlopen(base + path, timeout=120).read().decode("utf-8")
    parsed = json.loads(data)
    if isinstance(parsed, dict):
        size = {k: (len(v) if isinstance(v, list) else "obj") for k, v in parsed.items()}
    else:
        size = len(parsed)
    print("{} -> {}".format(path, size))
PY

tail -20 /tmp/deputy-api-smoke.log
