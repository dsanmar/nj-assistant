from app.services.ingestion import ingest_all_pdfs

def main():
    result = ingest_all_pdfs()
    print("✅ Ingestion complete")
    print(f"Total PDFs: {result.total_pdfs}")
    print(f"Ingested (new/changed): {result.ingested}")
    print(f"Skipped (unchanged): {result.skipped_unchanged}")
    print(f"Pages written: {result.pages_written}")

if __name__ == "__main__":
    main()
