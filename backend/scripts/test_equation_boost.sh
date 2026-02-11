#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
TOKEN="${TOKEN:-}"

if [[ -z "${TOKEN}" ]]; then
  echo "TOKEN is required. Export TOKEN or pass it inline." >&2
  exit 1
fi

status() {
  curl -s -o /dev/null -w "%{http_code}" "$@"
}

expect_status() {
  local want="$1"
  shift
  local got
  got="$(status "$@")"
  if [[ "${got}" != "${want}" ]]; then
    echo "Expected ${want}, got ${got} for: $*" >&2
    exit 1
  fi
}

expect_status 401 \
  -X POST "${BASE_URL}/chat/ask" \
  -H "Content-Type: application/json" \
  -d '{"query":"equation for pay adjustment","scope":"all","k":8,"mode":"sources_only"}'

check_query() {
  local query="$1"
  local resp
  resp="$(curl -s \
    -X POST "${BASE_URL}/chat/ask" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${TOKEN}" \
    -d "{\"query\":\"${query}\",\"scope\":\"all\",\"k\":8,\"mode\":\"sources_only\"}")"

  python - "$resp" "$query" <<'PY'
import json
import sys

raw = sys.argv[1]
query = sys.argv[2]
data = json.loads(raw)
citations = data.get("citations") or []
top = citations[:3]
if not top:
    print(f"No citations returned for query: {query}", file=sys.stderr)
    sys.exit(1)
if not any(c.get("chunk_kind") == "equation" for c in top):
    print(f"No equation chunk in top 3 for query: {query}", file=sys.stderr)
    sys.exit(1)
PY
}

check_query "equation for pay adjustment"
check_query "pay equations for ride quality"
check_query "PPA equation thickness"

echo "Equation boost tests passed."
