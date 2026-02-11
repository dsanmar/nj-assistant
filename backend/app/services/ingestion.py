from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import fitz  # PyMuPDF

from app.core.config import settings
from app.services.db import get_conn


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def now_utc_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def init_db() -> None:
    """
    Migrations are authoritative for schema creation.
    This check prevents silent partial setups when migrations were skipped.
    """
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table' AND name IN ('documents', 'pages')
            """
        ).fetchall()
        have = {r["name"] for r in row}
        if not {"documents", "pages"}.issubset(have):
            missing = {"documents", "pages"} - have
            raise RuntimeError(
                "Missing base tables: "
                + ", ".join(sorted(missing))
                + ". Run migrations (python -m scripts.run_migrations)."
            )


def classify_pdf(pdf_path: Path) -> tuple[str, str | None, str]:
    """
    Returns: (doc_type, mp_id, display_name)
    """
    name = pdf_path.name.lower()

    # Material Procedures
    stem = pdf_path.stem.upper()
    if stem.startswith("MP") and "-" in stem:
        # e.g. MP1-25, MP10-25
        return ("mp", stem, stem)

    # Standard Specs
    if "standspec" in name or "standard spec" in name:
        return ("standspec", None, "2019 Standard Specifications (Road & Bridge)")

    # Scheduling Manual
    if "scheduling" in name:
        return ("scheduling", None, "Construction Scheduling Manual")

    # Fallback
    return ("other", None, pdf_path.stem)


@dataclass
class IngestionResult:
    total_pdfs: int
    ingested: int
    skipped_unchanged: int
    pages_written: int


def extract_pages_text(pdf_path: Path) -> list[str]:
    """
    Extract per-page text using PyMuPDF.
    Returns list where index 0 => page 1.
    """
    doc = fitz.open(pdf_path)
    pages: list[str] = []
    for page in doc:
        # "text" is usually best baseline; later you can switch to dict/json for table-aware parsing
        t = page.get_text("text") or ""
        # normalize a bit
        t = t.replace("\u00a0", " ").strip()
        pages.append(t)
    doc.close()
    return pages


def upsert_document_and_pages(pdf_path: Path) -> tuple[bool, int, int]:
    """
    Returns (did_ingest, document_id, pages_written)
    - Skips ingest if file hash matches existing.
    - If changed/new: upserts document row and replaces all page rows.
    """
    file_hash = sha256_file(pdf_path)
    doc_type, mp_id, display_name = classify_pdf(pdf_path)

    pages = extract_pages_text(pdf_path)
    page_count = len(pages)
    ingested_at = now_utc_iso()

    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id, file_hash FROM documents WHERE file_path = ?",
            (str(pdf_path),),
        ).fetchone()

        if existing and existing["file_hash"] == file_hash:
            return (False, int(existing["id"]), 0)

        # Upsert document
        if existing:
            document_id = int(existing["id"])
            conn.execute("""
                UPDATE documents
                SET filename = ?, display_name = ?, doc_type = ?, mp_id = ?, file_hash = ?,
                    page_count = ?, ingested_at = ?
                WHERE id = ?
            """, (
                pdf_path.name,
                display_name,
                doc_type,
                mp_id,
                file_hash,
                page_count,
                ingested_at,
                document_id,
            ))
            # Replace pages for deterministic behavior
            conn.execute("DELETE FROM pages WHERE document_id = ?", (document_id,))
        else:
            cur = conn.execute("""
                INSERT INTO documents (filename, display_name, doc_type, mp_id, file_path, file_hash, page_count, ingested_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                pdf_path.name,
                display_name,
                doc_type,
                mp_id,
                str(pdf_path),
                file_hash,
                page_count,
                ingested_at,
            ))
            document_id = int(cur.lastrowid)

        # Insert pages
        pages_written = 0
        for idx, text in enumerate(pages, start=1):
            conn.execute("""
                INSERT INTO pages (document_id, page_number, text, char_count)
                VALUES (?, ?, ?, ?)
            """, (document_id, idx, text, len(text)))
            pages_written += 1

    return (True, document_id, pages_written)


def iter_pdfs(pdf_dir: Path) -> Iterable[Path]:
    for p in sorted(pdf_dir.glob("*.pdf")):
        if p.is_file():
            yield p


def ingest_all_pdfs(pdf_dir: Path | None = None) -> IngestionResult:
    init_db()

    pdf_dir = pdf_dir or settings.PDF_DIR
    pdfs = list(iter_pdfs(pdf_dir))

    ingested = 0
    skipped = 0
    pages_written = 0

    for pdf in pdfs:
        did_ingest, _, written = upsert_document_and_pages(pdf)
        if did_ingest:
            ingested += 1
            pages_written += written
        else:
            skipped += 1

    return IngestionResult(
        total_pdfs=len(pdfs),
        ingested=ingested,
        skipped_unchanged=skipped,
        pages_written=pages_written,
    )
