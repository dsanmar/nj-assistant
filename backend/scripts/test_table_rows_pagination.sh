#!/usr/bin/env bash
set -euo pipefail

TABLE_UID="${1:-}"
BASE_URL="${BASE_URL:-http://localhost:8000}"
LIMIT="${LIMIT:-25}"

if [[ -z "$TABLE_UID" ]]; then
  echo "Usage: $0 <table_uid>"
  echo "Optional env: BASE_URL, LIMIT"
  exit 1
fi

curl -s "${BASE_URL}/tables/rows?table_uid=${TABLE_UID}&limit=${LIMIT}&offset=0"
echo
curl -s "${BASE_URL}/tables/rows?table_uid=${TABLE_UID}&limit=${LIMIT}&offset=${LIMIT}"
echo
curl -s "${BASE_URL}/tables/rows?table_uid=${TABLE_UID}&limit=${LIMIT}&offset=$((LIMIT * 2))"
echo
