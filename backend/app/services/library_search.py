from __future__ import annotations

from urllib.parse import quote

from app.schemas.document import (
    DocumentSearchRequest,
    DocumentSearchResponse,
    DocumentSearchResult,
)
from app.services.hybrid_chunks import hybrid_chunks_search


def library_search(req: DocumentSearchRequest) -> DocumentSearchResponse:
    """
    Library search: page-level results for browsing, no synthesis.
    """
    limit = int(req.k)
    offset = int(req.offset)
    pool_k = max(200, (offset + limit) * 10)

    mp_ids = [req.mp_id] if (req.scope == "mp_only" and req.mp_id) else None
    hits, _conf = hybrid_chunks_search(
        query=req.query,
        k=pool_k,
        scope=req.scope,
        mp_ids=mp_ids,
    )

    doc_type_filter = (req.doc_type or "").strip().lower()
    mp_filter = (req.mp_id or "").strip().upper()

    filtered = []
    for h in hits:
        if doc_type_filter and (h.doc_type or "").lower() != doc_type_filter:
            continue
        if mp_filter:
            mp = (h.mp_id or "").upper()
            if not mp or (not mp.startswith(mp_filter) and mp != mp_filter):
                continue
        filtered.append(h)

    page_hits = filtered[offset : offset + limit]
    total = None
    if len(filtered) < pool_k:
        total = len(filtered)

    results = [
        DocumentSearchResult(
            chunk_id=h.chunk_id,
            score=h.score,
            snippet=h.snippet,
            page_start=h.page_start,
            page_end=h.page_end,
            filename=h.filename,
            display_name=h.display_name,
            doc_type=h.doc_type,
            mp_id=h.mp_id,
            section_id=h.section_id,
            heading=h.heading,
            chunk_kind=h.chunk_kind,
            table_uid=h.table_uid,
            table_label=h.table_label,
            open_url=f"/documents/open?filename={quote(h.filename)}&page={h.page_start}",
        )
        for h in page_hits
    ]

    return DocumentSearchResponse(
        query=req.query,
        scope=req.scope,
        total=total,
        offset=offset,
        limit=limit,
        results=results,
    )
