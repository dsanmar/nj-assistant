# It’s a tiny regression test
from app.services.ask import ask_question


def main() -> None:
    out = ask_question(
        query="701.02.01",
        scope="standspec",
        k=5,
        mode="answer",
    )
    assert out["confidence"] == "strong", f"expected strong, got {out['confidence']}"
    assert out["answer"], "expected non-empty answer"
    print("✅ ask_question section intent confidence strong and answer present")


if __name__ == "__main__":
    main()
