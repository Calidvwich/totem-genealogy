#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
MEMBER_ID="${1:-14378}"

python3 - "$BASE_URL" "$MEMBER_ID" <<'PY'
import json
import sys
import urllib.error
import urllib.request

base_url = sys.argv[1].rstrip("/")
member_id = sys.argv[2]

detail = json.loads(urllib.request.urlopen(base_url + "/api/members/{}/detail".format(member_id), timeout=20).read().decode("utf-8"))
member = detail["member"]
payload = {
    "clan_id": int(member["clan_id"]),
    "name": member["name"],
    "gender": member["gender"] or "U",
    "birth_year": int(member["birth_year"]) if member.get("birth_year") else None,
    "death_year": int(member["death_year"]) if member.get("death_year") else None,
    "father_id": int(member["father_id"]) if member.get("father_id") else None,
    "mother_id": int(member["mother_id"]) if member.get("mother_id") else None,
    "generation_num": int(member["generation_num"]) if member.get("generation_num") else None,
    "bio": member.get("bio") or "",
}

request = urllib.request.Request(
    base_url + "/api/members/{}?current_user_id=admin".format(member_id),
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="PUT",
)
try:
    response = urllib.request.urlopen(request, timeout=30)
    print(response.status)
    print(response.read().decode("utf-8")[:500])
except urllib.error.HTTPError as exc:
    print(exc.code)
    print(exc.read().decode("utf-8")[:1000])
    sys.exit(1)
PY
