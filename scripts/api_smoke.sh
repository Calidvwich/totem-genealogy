#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PORT="${API_PORT:-8010}"
export TOTEM_DATABASE="${TOTEM_DATABASE:-genealogy_smoke_codex}"
export TOTEM_USER="${TOTEM_USER:-totem}"
export TOTEM_PORT="${TOTEM_PORT:-55432}"
export TOTEM_USE_DEMO=0

. .venv/bin/activate

python -m uvicorn main:app --host 127.0.0.1 --port "$PORT" >/tmp/genealogy_api_smoke.log 2>&1 &
PID=$!
trap 'kill "$PID" >/dev/null 2>&1 || true; wait "$PID" >/dev/null 2>&1 || true' EXIT

ready=0
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS "http://127.0.0.1:${PORT}/" >/tmp/api_root.html 2>/tmp/api_root.err; then
    ready=1
    break
  fi
  if ! kill -0 "$PID" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

if [ "$ready" -ne 1 ]; then
  echo "API_SMOKE_CODE=1"
  echo "SERVER_NOT_READY"
  echo "PID=${PID}"
  echo "PROCESS_ALIVE=$(kill -0 "$PID" >/dev/null 2>&1 && echo yes || echo no)"
  echo "CURL_ERROR"
  cat /tmp/api_root.err 2>/dev/null || true
  echo "SERVER_LOG"
  cat /tmp/genealogy_api_smoke.log 2>/dev/null || true
  exit 1
fi

code=0
curl -fsS "http://127.0.0.1:${PORT}/api/dashboard" >/tmp/api_dashboard.json || code=1
curl -fsS "http://127.0.0.1:${PORT}/api/members?clan_id=1&q=%E5%BC%A0_1_1" >/tmp/api_members.json || code=1
curl -fsS \
  -H "Content-Type: application/json" \
  -d '{"user_id":"admin","password":"123456"}' \
  "http://127.0.0.1:${PORT}/api/login" >/tmp/api_login.json || code=1
curl -fsS -X POST "http://127.0.0.1:${PORT}/api/export/database?current_user_id=admin" >/tmp/api_export.json || code=1

echo "API_SMOKE_CODE=${code}"
echo "LOGIN_RESULT"
cat /tmp/api_login.json
echo
echo "DASHBOARD_HEAD"
head -c 300 /tmp/api_dashboard.json
echo
echo "MEMBERS_HEAD"
head -c 300 /tmp/api_members.json
echo
echo "EXPORT_RESULT"
cat /tmp/api_export.json
echo
echo "SERVER_LOG_TAIL"
tail -40 /tmp/genealogy_api_smoke.log

exit "$code"
