#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
TOKEN="${TOKEN:-}"
KNOWN_FILENAME="${KNOWN_FILENAME:-StandSpecRoadBridge.pdf}"

if [[ -z "${TOKEN}" ]]; then
  echo "TOKEN is required. Export TOKEN or pass it inline." >&2
  exit 1
fi

auth_header=(-H "Authorization: Bearer ${TOKEN}")

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

expect_one_of() {
  local want1="$1"
  local want2="$2"
  shift 2
  local got
  got="$(status "$@")"
  if [[ "${got}" != "${want1}" && "${got}" != "${want2}" ]]; then
    echo "Expected ${want1} or ${want2}, got ${got} for: $*" >&2
    exit 1
  fi
}

expect_status 404 "${auth_header[@]}" \
  "${BASE_URL}/documents/open?filename=../../etc/passwd&page=1"

expect_status 404 "${auth_header[@]}" \
  "${BASE_URL}/documents/open?filename=%2e%2e%2f%2e%2e%2fetc%2fpasswd&page=1"

expect_status 404 "${auth_header[@]}" \
  "${BASE_URL}/documents/open?filename=DoesNotExist.pdf&page=1"

expect_status 302 "${auth_header[@]}" \
  "${BASE_URL}/documents/open?filename=${KNOWN_FILENAME}&page=1"

expect_status 200 "${auth_header[@]}" \
  "${BASE_URL}/documents/file?filename=${KNOWN_FILENAME}"

if [[ "${CHECK_PAGE_BOUNDS:-1}" == "1" ]]; then
  expect_one_of 400 404 "${auth_header[@]}" \
    "${BASE_URL}/documents/open?filename=${KNOWN_FILENAME}&page=999999"
fi

echo "Document security tests passed."
