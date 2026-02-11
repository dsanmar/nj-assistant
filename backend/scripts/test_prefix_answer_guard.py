from app.services.ask import ask_question


def main() -> None:
    out = ask_question(
        query="What materials are required for Section 701?",
        scope="standspec",
        k=8,
        mode="answer",
    )

    assert out["confidence"] in ("medium", "strong"), f"unexpected confidence {out['confidence']}"
    assert "[1]" in out["answer"], "answer must contain at least one citation marker"

    hits = out.get("hits", [])
    assert hits, "expected hits"
    assert any(
        h.section_id and (h.section_id.startswith("701.02") or h.section_id.startswith("701.02.01"))
        for h in hits
    ), "expected 701.02* section in citations"

    # Guard against long fabricated lists when sources are thin
    assert len(out["answer"]) < 500, "answer seems too long for thin sources"
    print("✅ prefix answer guard OK")


if __name__ == "__main__":
    main()
