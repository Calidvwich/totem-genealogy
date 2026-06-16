#!/usr/bin/env bash
set -euo pipefail

PORT="${API_PORT:-8011}"
cd "$(dirname "$0")/.."

export TOTEM_USE_DEMO=0
export TOTEM_DATABASE="${TOTEM_DATABASE:-genealogy}"
export TOTEM_USER="${TOTEM_USER:-totem}"
export TOTEM_PORT="${TOTEM_PORT:-55432}"

. .venv/bin/activate
python -m uvicorn main:app --host 127.0.0.1 --port "$PORT" >/tmp/perf-search-smoke.log 2>&1 &
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
base = "http://127.0.0.1:{}/api/members/search-performance".format(port)
queries = ["张", "张_1_1", "14378"]
for query in queries:
    for mode in ("false", "true"):
        params = urllib.parse.urlencode({
            "clan_id": 0,
            "q": query,
            "performance_mode": mode,
            "current_user_id": "admin",
        })
        data = json.loads(urllib.request.urlopen(base + "?" + params, timeout=60).read().decode("utf-8"))
        print("{} mode={} ok={} elapsed_ms={} memory_kb={} count={} error={}".format(
            query,
            data.get("mode"),
            data.get("ok"),
            data.get("elapsed_ms"),
            data.get("memory_kb"),
            data.get("count"),
            data.get("error", ""),
        ))
PY

tail -20 /tmp/perf-search-smoke.log
