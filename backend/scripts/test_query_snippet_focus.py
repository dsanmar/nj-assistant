from app.services.ask import _make_query_focused_snippet, _has_payment_days_phrase


def _assert_contains(actual: str, needle: str) -> None:
    if needle.lower() not in actual.lower():
        raise SystemExit(f"[FAIL] expected snippet to include: {needle}\n{actual}")


def _assert_false(value: bool, label: str) -> None:
    if value:
        raise SystemExit(f"[FAIL] expected false for {label}")


def main() -> None:
    raw_text = (
        "Prompt payment requirements apply to subcontractors. "
        "Interest begins to accrue on the tenth day. "
        "If a subcontractor is not paid within 10 days after receipt by the Contractor "
        "of payment by the Department, the Contractor shall pay interest at the prime rate plus 1 percent. "
        "Other unrelated text follows here."
    )
    query = "Within how many days must subcontractors be paid after the contractor receives payment?"
    snippet = _make_query_focused_snippet(raw_text, query, window=260, max_len=520)
    _assert_contains(snippet, "within 10 days after receipt")

    missing_text = "Payment terms are described generally without timing details."
    _assert_false(_has_payment_days_phrase(missing_text), "payment-days phrase match")

    print("[PASS] query-focused snippet includes 10 days receipt clause")
    print("[PASS] numeric gate detects missing payment-days phrase")


if __name__ == "__main__":
    main()
