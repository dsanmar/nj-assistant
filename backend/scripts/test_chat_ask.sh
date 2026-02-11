#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
TOKEN="${TOKEN:-}"

curl -s "${BASE_URL}/chat/ask" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{"query":"bridge bearings","scope":"standspec","k":6,"mode":"answer"}' | head -c 1200
