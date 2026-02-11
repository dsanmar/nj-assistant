from dotenv import load_dotenv

load_dotenv(override=False)

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers import chat, documents, tables

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())

app = FastAPI(
    title="NJDOT Assistant API",
    version="0.1.0"
)

def _cors_origins() -> list[str]:
    origins: list[str] = []
    frontend = os.getenv("FRONTEND_URL", "").strip()
    if frontend:
        origins.append(frontend)
    allow = os.getenv("ALLOW_ORIGINS", "").strip()
    if allow:
        origins.extend([o.strip() for o in allow.split(",") if o.strip()])
    return origins or ["http://localhost:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# NOTE: We do not mount /static for PDFs to avoid unauthenticated access.

@app.get("/")
def root():
    return {"status": "ok"}


@app.get("/health")
def health():
    warnings: list[str] = []
    if not settings.DB_PATH.exists():
        warnings.append(f"db_missing:{settings.DB_PATH}")
    if not settings.PDF_DIR.exists():
        warnings.append(f"pdf_dir_missing:{settings.PDF_DIR}")

    expected = [
        settings.BM25_PATH,
        settings.FAISS_INDEX_PATH,
        settings.FAISS_META_PATH,
        settings.INDEX_DIR / "bm25_chunks.pkl",
        settings.INDEX_DIR / "faiss_chunks.index",
        settings.INDEX_DIR / "faiss_chunks_meta.pkl",
    ]
    for p in expected:
        if not p.exists():
            warnings.append(f"index_missing:{p}")

    payload = {"status": "ok"}
    if warnings:
        payload["warnings"] = warnings
    return payload

app.include_router(chat.router)
app.include_router(documents.router)
app.include_router(tables.router)
