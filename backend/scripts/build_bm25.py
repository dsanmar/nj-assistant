from app.services.bm25 import build_bm25_index

def main():
    path = build_bm25_index()
    print("BM25 index built:", path)

if __name__ == "__main__":
    main()
