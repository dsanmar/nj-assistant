from app.services.bm25 import bm25_search

def main():
    q = input("Query: ").strip()
    hits = bm25_search(q, k=8)

    print("\nTop results:\n")
    for idx, h in enumerate(hits, start=1):
        label = h.display_name
        if h.mp_id:
            label = f"{h.mp_id} ({h.display_name})"
        print(f"{idx}) score={h.score:.3f} | {label} | page {h.page_number}")
        print(f"   {h.snippet}\n")

if __name__ == "__main__":
    main()
