#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
TOKEN="${TOKEN:-}"
TABLE_UID="${1:-}"

if [[ -z "${TOKEN}" ]]; then
  echo "TOKEN is required. Export TOKEN or pass it inline." >&2
  exit 1
fi

if [[ -z "${TABLE_UID}" ]]; then
  echo "Usage: $0 <table_uid>" >&2
  exit 1
fi

auth_header=(-H "Authorization: Bearer ${TOKEN}")

status() {
  curl -s -o /dev/null -w "%{http_code}" "$@"
}

body() {
  curl -s "$@"
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
  "${BASE_URL}/tables/cells?table_uid=${TABLE_UID}"

cells_status="$(status "${auth_header[@]}" "${BASE_URL}/tables/cells?table_uid=${TABLE_UID}")"
if [[ "${cells_status}" == "200" ]]; then
  rows_payload="$(body "${auth_header[@]}" "${BASE_URL}/tables/rows?table_uid=${TABLE_UID}&include_cells=true")"
  if ! echo "${rows_payload}" | grep -q '"cells"'; then
    echo "Expected cells in /tables/rows payload when cells exist." >&2
    exit 1
  fi
  echo "Cells present for ${TABLE_UID}."
else
  echo "No cells for ${TABLE_UID} (status ${cells_status})."
fi
