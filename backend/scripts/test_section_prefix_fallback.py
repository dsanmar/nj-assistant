from app.services.ask import ask_question


def main() -> None:
    out = ask_question(
        query="What materials are required for Section 701?",
        scope="standspec",
        k=8,
        mode="sources_only",
    )
    hits = out.get("hits", [])
    assert hits, "expected hits for section prefix fallback"
    for h in hits:
        assert h.section_id and h.section_id.startswith("701."), f"unexpected section_id {h.section_id}"

    assert any(h.section_id.startswith("701.02") for h in hits), "expected 701.02* hit"
    print("✅ section prefix fallback returns only 701.* chunks")


if __name__ == "__main__":
    main()
