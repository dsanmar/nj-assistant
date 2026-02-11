from app.services.bm25_chunks import build_bm25_chunks_index

def main():
    p = build_bm25_chunks_index()
    print("✅ BM25 chunks index built:", p)

if __name__ == "__main__":
    main()
