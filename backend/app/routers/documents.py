from __future__ import annotations

from pathlib import Path
from urllib.parse import quote, unquote

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse, FileResponse, JSONResponse

from app.core.config import settings
from app.core.deps import require_user
from app.services.db import get_conn
from app.services.library_search import library_search
from app.schemas.document import DocumentSearchRequest, DocumentSearchResponse

router = APIRouter(prefix="/documents", tags=["documents"])

# PDFs live here in repo
PDF_DIR = settings.PDF_DIR
logger = logging.getLogger(__name__)


def _normalize_filename(filename: str) -> str:
    """
    Normalize and validate a filename from user input.
    Reject traversal, hidden files, and encoded separators.
    """
    decoded = unquote(filename or "").strip()
    p = Path(decoded)
    if not decoded or decoded.startswith(".") or p.is_absolute() or p.name != decoded:
        raise HTTPException(status_code=404, detail="PDF not found")
    return decoded


def _safe_pdf_path(filename: str) -> Path:
    """
    Prevent path traversal. Only allow files that exist under PDF_DIR.
    """
    p = (PDF_DIR / filename).resolve()
    if not str(p).startswith(str(PDF_DIR.resolve())):
        raise HTTPException(status_code=404, detail="PDF not found")

    if not p.exists() or not p.is_file():
        raise HTTPException(status_code=404, detail="PDF not found")

    # Optional: enforce extension
    if p.suffix.lower() != ".pdf":
        raise HTTPException(status_code=400, detail="Invalid file type")

    return p


def _get_document_row(conn, filename: str):
    return conn.execute(
        """
        SELECT
            d.id,
            d.filename,
            (
                SELECT COUNT(1)
                FROM pages p
                WHERE p.document_id = d.id
            ) AS page_count
        FROM documents d
        WHERE d.filename = ?
        LIMIT 1
        """,
        (filename,),
    ).fetchone()


@router.get("")
async def list_documents(_user=Depends(require_user)):
    """
    Real document list from SQLite `documents` table.
    pages is computed from the pages table to avoid relying on a documents.pages column.
    """
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                d.id,
                d.filename,
                d.display_name,
                d.doc_type,
                d.mp_id,
                (
                    SELECT COUNT(1)
                    FROM pages p
                    WHERE p.document_id = d.id
                ) AS page_count
            FROM documents d
            ORDER BY d.doc_type, d.display_name
            """
        ).fetchall()

    docs = []
    for r in rows:
        docs.append(
            {
                "id": int(r["id"]),
                "filename": r["filename"],
                "display_name": r["display_name"],
                "doc_type": r["doc_type"],
                "mp_id": r["mp_id"],
                "pages": int(r["page_count"]),
                "status": "indexed",
            }
        )

    return {"documents": docs}


@router.post("/search", response_model=DocumentSearchResponse)
async def search_documents(req: DocumentSearchRequest, _user=Depends(require_user)):
    """
    Full-text search over chunks for Library search UX.
    Uses hybrid_chunks_search and filters in-memory by doc_type/mp_id.
    """
    return library_search(req)


@router.get("/file")
async def get_document_file(
    filename: str = Query(..., min_length=1),
    _user=Depends(require_user),
):
    """
    Stream the raw PDF bytes. This is what react-pdf / PDF.js should load.
    """
    safe_filename = _normalize_filename(filename)
    # Validate exists in DB
    with get_conn() as conn:
        row = _get_document_row(conn, safe_filename)

    if not row:
        raise HTTPException(status_code=404, detail="Document not found")

    path = _safe_pdf_path(safe_filename)
    return FileResponse(
        path,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{safe_filename}"'},
    )


@router.get("/open")
async def open_document(
    filename: str = Query(..., min_length=1),
    page: int = Query(1, ge=1),
    _user=Depends(require_user),
):
    """
    "Open in Document" deep link.
    Redirects to /documents/file and uses #page= for browser-native viewers.
    (React-PDF will ignore the hash, but the frontend can use the page param.)
    """
    # Pages are 1-based in URLs and UI.
    safe_filename = _normalize_filename(filename)
    try:
        with get_conn() as conn:
            row = _get_document_row(conn, safe_filename)
    except Exception:
        logger.exception("Document lookup failed for open_document; filename=%s page=%s", safe_filename, page)
        return JSONResponse(
            {"error": "Document lookup failed"},
            status_code=500,
        )

    if not row:
        return JSONResponse({"error": "Document not found"}, status_code=404)

    page_count = int(row["page_count"]) if row["page_count"] is not None else 0
    if page_count and page > page_count:
        return JSONResponse(
            {"error": "Page out of range", "page": page, "page_count": page_count},
            status_code=404,
        )

    # URL-encode filename for spaces etc.
    safe_fn = quote(safe_filename)

    url = f"/documents/file?filename={safe_fn}#page={page}"
    try:
        return RedirectResponse(url=url, status_code=302)
    except Exception:
        logger.exception("Open redirect failed; filename=%s page=%s", safe_filename, page)
        return JSONResponse(
            {"error": "Open redirect failed", "page": page},
            status_code=500,
        )
