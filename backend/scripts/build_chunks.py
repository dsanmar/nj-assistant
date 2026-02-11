from app.services.chunk_ingestion import rebuild_chunks

def main():
    out = rebuild_chunks()
    print("✅ chunks rebuilt:", out)

if __name__ == "__main__":
    main()
