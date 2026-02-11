## Retrieval Overview

This project separates retrieval paths for clarity and UX consistency.

Endpoints:
- `/documents/search` uses **library_search** (page-level results, no LLM).
- `/chat/ask` uses **chat_retrieve** (chunk-level hybrid retrieval with section/table intent handling and guarded synthesis).

Definitions:
- **Page-level**: returns document/page hits suitable for browsing and opening PDFs.
- **Chunk-level**: returns smaller text chunks used for Q&A answers with citations.

Why it matters:
- Library search favors recall and quick browsing without synthesis.
- Chat Q&A prioritizes accuracy and intent handling (sections, tables) with safe citations.

## Deploy checklist

Environment:
- `SUPABASE_URL`, `SUPABASE_JWT_SECRET`
- `LLM_PROVIDER`, `GROQ_API_KEY`
- `FRONTEND_URL`, `ALLOW_ORIGINS`
- `PDF_DIR`, `LOG_LEVEL`

Data + indexes:
- Run migrations: `python -m scripts.run_migrations`
- Build indexes:
  - `python -m scripts.build_bm25`
  - `python -m scripts.build_faiss`
  - `python -m scripts.build_bm25_chunks`
  - `python -m scripts.build_faiss_chunks`
