#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
TOKEN="${TOKEN:-}"
TABLE_UID="${TABLE_UID:-}"

if [[ -z "${TOKEN}" ]]; then
  echo "TOKEN is required. Export TOKEN or pass it inline." >&2
  exit 1
fi

if [[ -z "${TABLE_UID}" ]]; then
  echo "TABLE_UID is required. Export TABLE_UID or pass it inline." >&2
  exit 1
fi

auth_header=(-H "Authorization: Bearer ${TOKEN}")

curl -s "${BASE_URL}/health" | head -c 1000
echo

curl -s "${BASE_URL}/chat/ask" \
  -H "Content-Type: application/json" \
  "${auth_header[@]}" \
  -d '{"query":"bridge bearings","scope":"standspec","k":6,"mode":"answer"}' | head -c 1500
echo

curl -s "${BASE_URL}/tables/rows?table_uid=${TABLE_UID}&limit=10&offset=0" \
  "${auth_header[@]}" | head -c 1500
