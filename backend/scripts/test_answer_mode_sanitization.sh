#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
TOKEN="${TOKEN:-}"

if [[ -z "${TOKEN}" ]]; then
  echo "TOKEN is required. Export TOKEN or pass it inline." >&2
  exit 1
fi

auth_header=(-H "Authorization: Bearer ${TOKEN}")

query1='Where can I find contractor responsibilities in the standard specs?'
query2='What percentage is the Proposal Bond required to be?'
query3='How many days does the bidder have to execute the contract after award?'
query4='103.04'
query5='Under N.J.S.A. 52:32-40/41, when does interest apply if a subcontractor is not paid?'

tmp_body="$(mktemp)"
tmp_code="$(mktemp)"
trap 'rm -f "$tmp_body" "$tmp_code"' EXIT

for q in "$query1" "$query2" "$query3" "$query4" "$query5"; do
  echo "Q: $q" >&2

  # Write body to file; write HTTP code to another file
  curl -sS "${BASE_URL}/chat/ask" \
    -H "Content-Type: application/json" \
    "${auth_header[@]}" \
    -d "{\"query\":\"${q}\",\"scope\":\"standspec\",\"k\":6,\"mode\":\"answer\"}" \
    -o "$tmp_body" \
    -w "%{http_code}" > "$tmp_code"

  http_code="$(cat "$tmp_code")"

  if [[ "$http_code" != "200" ]]; then
    echo "[FAIL] HTTP $http_code" >&2
    echo "Raw response body:" >&2
    cat "$tmp_body" >&2
    echo >&2
    continue
  fi

  # Validate JSON
  if ! python -c "import json,sys; json.load(open('$tmp_body','r',encoding='utf-8'))" >/dev/null 2>&1; then
    echo "[FAIL] Response was not valid JSON" >&2
    echo "Raw response body:" >&2
    cat "$tmp_body" >&2
    echo >&2
    continue
  fi

  # Parse once
  python - <<PY
import json, re, sys
with open("$tmp_body","r",encoding="utf-8") as f:
    obj = json.load(f)
answer = obj.get("answer") or ""
q = """$q"""
print("A:", answer)
print("Citations:", len(obj.get("citations") or []))
print("HAS_BRACKETS:", bool(re.search(r"\\[\\d+\\]", answer)))
print("HAS_SECTION_WORD:", "section" in answer.lower())
print("HAS_PAGE_WORD:", "page" in answer.lower())
print("HAS_SECTION_ID:", bool(re.search(r"\\b\\d{3}(?:\\.\\d{2}){1,2}\\b", answer)))
print("HAS_RELEVANT_EXCERPTS:", "relevant excerpts" in answer.lower())
print("HAS_SOURCE_MARKER:", "source" in answer.lower())
print("HAS_CITATIONS_PANEL:", "see the citations panel" in answer.lower())
def fail(msg):
    print("[FAIL]", msg)
    sys.exit(1)
low = answer.lower().strip()
if q == "Where can I find contractor responsibilities in the standard specs?":
    if "source" in low or re.search(r"\\[\\d+\\]", answer):
        fail("location query contains SOURCE or brackets")
elif q == "What percentage is the Proposal Bond required to be?":
    if "50" not in answer:
        fail("proposal bond answer missing 50")
    if "according to" in low or "source" in low or re.search(r"\\[\\d+\\]", answer):
        fail("proposal bond answer contains meta/source/brackets")
    if re.search(r"(\\b(in|to)\\s*$|,\\s*$)", low):
        fail("proposal bond answer ends with dangling fragment")
elif q == "How many days does the bidder have to execute the contract after award?":
    if "14" not in answer:
        fail("execute contract answer missing 14")
    if "according to" in low or "source" in low or re.search(r"\\[\\d+\\]", answer):
        fail("execute contract answer contains meta/source/brackets")
elif q == "103.04":
    if "see the citations panel" not in low:
        fail("bare section id did not defer to citations panel")
    if "relevant excerpts" in low or "source" in low or re.search(r"\\[\\d+\\]", answer):
        fail("bare section id answer contains excerpts/source/brackets")
elif q == "Under N.J.S.A. 52:32-40/41, when does interest apply if a subcontractor is not paid?":
    if "10" not in answer or "days" not in low:
        fail("prompt payment interest answer missing 10 days")
    if "5 days" in low:
        fail("prompt payment interest answer contains 5 days")
PY

  echo
done

echo "Asserts:"
echo "1) 'Where can I find' should NOT contain SOURCE or brackets."
echo "2) Proposal Bond answer should mention '50' and not contain Section/page/brackets/SOURCE."
echo "3) Execute contract answer should mention '14' and not contain meta/source/brackets."
echo "4) '103.04' should include 'See the citations panel' and not contain Relevant excerpts/brackets/SOURCE."
echo "5) Prompt payment interest should mention 10 days and not 5 days."

python - <<'PY'
from app.services.ask import _polish_answer_text

raw = (
    "The contractor must pay subcontractors within 5 days after receiving payment "
    "from the Department. This requirement is specified"
)
clean = _polish_answer_text(raw)
assert "requirement is specified" not in clean.lower(), clean
assert not clean.lower().endswith("specified"), clean
assert not clean.lower().endswith("specified in"), clean
assert "source" not in clean.lower(), clean
assert "[" not in clean, clean
print("[PASS] _polish_answer_text removes trailing meta fragments")
PY
