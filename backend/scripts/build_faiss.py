from app.services.faiss_store import build_faiss_index

def main():
    ip, mp = build_faiss_index()
    print("✅ FAISS built:", ip)
    print("✅ FAISS meta:", mp)

if __name__ == "__main__":
    main()
