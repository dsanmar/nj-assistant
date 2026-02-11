from app.services.faiss_chunks import build_faiss_chunks_index

def main():
    ip, mp = build_faiss_chunks_index()
    print("✅ FAISS chunks built:", ip)
    print("✅ FAISS chunks meta:", mp)

if __name__ == "__main__":
    main()
