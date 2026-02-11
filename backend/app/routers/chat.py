import re
from urllib.parse import quote

from fastapi import APIRouter, Depends

from app.schemas.retrieval import RetrievalRequest, RetrievalResponse
from app.services.retrieval import retrieve, chat_retrieve as chat_ask_retrieve

from app.schemas.hybrid import (
    HybridRetrieveRequest,
    HybridRetrieveResponse,
    HybridCitation,
)
from app.services.hybrid import hybrid_search

from app.schemas.hybrid_chunks import (
    HybridChunksRequest,
    HybridChunksResponse,
    HybridChunkCitation,
)
from app.services.hybrid_chunks import hybrid_chunks_search

from app.core.deps import require_user
from app.schemas.ask import AskRequest, AskResponse, AskCitation
from app.services.retrieval import chat_retrieve

router = APIRouter(prefix="/chat", tags=["chat"])

_CITE_MARK_RE = re.compile(r"\[(\d+)\]")


def filter_citations_by_answer_markers(answer: str, citations: list[AskCitation]) -> list[AskCitation]:
    nums = {int(m.group(1)) for m in _CITE_MARK_RE.finditer(answer or "")}
    if not nums:
        return citations[: min(3, len(citations))]
    kept: list[AskCitation] = []
    for idx, c in enumerate(citations, start=1):
        if idx in nums:
            kept.append(c)
    return kept


def is_tocish(snippet: str) -> bool:
    s = (snippet or "").upper()
    if "TABLE OF CONTENTS" in s:
        return True
    return s.count("...") >= 8


def filter_sources_only(citations: list[AskCitation], k: int) -> list[AskCitation]:
    cleaned = [c for c in citations if not is_tocish(c.snippet)]
    return cleaned[:k]


def normalize_section(value: str | None) -> str:
    if not value:
        return ""
    out = value.strip().upper()
    if out.startswith("SECTION"):
        out = out.replace("SECTION", "", 1).strip()
    return out


def extract_section_id(query: str) -> str | None:
    # Match 701, 701.03, 701.03.01 with optional "Section" prefix.
    q = query or ""
    match = re.search(r"\b(?:section\s*)?(\d{3}(?:\.\d{2}){0,2})\b", q, re.I)
    return match.group(1) if match else None


def section_prefix_match(target: str, candidate: str | None) -> bool:
    # Prefix match with boundary: "701" matches "701" and "701.03" but not "7011".
    tgt = normalize_section(target)
    cand = normalize_section(candidate)
    if not tgt or not cand:
        return False
    if cand == tgt:
        return True
    return cand.startswith(f"{tgt}.")


@router.post("/retrieve", response_model=RetrievalResponse)
def chat_retrieve_endpoint(req: RetrievalRequest):
    return retrieve(req)


@router.post("/hybrid_retrieve", response_model=HybridRetrieveResponse)
def chat_hybrid_retrieve(req: HybridRetrieveRequest):
    hits, conf = hybrid_search(
        query=req.query,
        k=req.k,
        scope=req.scope,
        mp_ids=req.mp_ids,
    )

    return HybridRetrieveResponse(
        query=req.query,
        k=req.k,
        scope=req.scope,
        mp_ids=req.mp_ids,
        confidence=conf,
        results=[
            HybridCitation(
                display_name=h.display_name,
                filename=h.filename,
                doc_type=h.doc_type,
                mp_id=h.mp_id,
                page_number=h.page_number,
                score=h.score,
                snippet=h.snippet,
                bm25_score=h.bm25_score,
                vec_score=h.vec_score,
            )
            for h in hits
        ],
    )


@router.post("/hybrid_retrieve_chunks", response_model=HybridChunksResponse)
def chat_hybrid_retrieve_chunks(req: HybridChunksRequest):
    hits, conf = hybrid_chunks_search(
        query=req.query,
        k=req.k,
        scope=req.scope,
        mp_ids=req.mp_ids,
    )

    return HybridChunksResponse(
        query=req.query,
        k=req.k,
        scope=req.scope,
        mp_ids=req.mp_ids,
        confidence=conf,
        results=[
            HybridChunkCitation(
                chunk_id=h.chunk_id,
                display_name=h.display_name,
                filename=h.filename,
                doc_type=h.doc_type,
                mp_id=h.mp_id,
                section_id=h.section_id,
                heading=h.heading,
                page_start=h.page_start,
                page_end=h.page_end,
                score=h.score,
                snippet=h.snippet,
                open_url=f"/documents/open?filename={quote(h.filename)}&page={h.page_start}",
                bm25_score=h.bm25_score,
                vec_score=h.vec_score,
                chunk_kind=getattr(h, "chunk_kind", None),
                table_uid=getattr(h, "table_uid", None),
                table_label=getattr(h, "table_label", None),
                table_row_index=getattr(h, "table_row_index", None),
            )
            for h in hits
        ],
    )


@router.post("/ask", response_model=AskResponse)
def chat_ask(req: AskRequest, user=Depends(require_user)):
    out = chat_ask_retrieve(
        query=req.query,
        scope=req.scope,
        mp_ids=req.mp_ids,
        k=req.k,
        mode=req.mode,
    )

    hits = out.get("hits", [])
    citations = [
            AskCitation(
                chunk_id=h.chunk_id,
                display_name=h.display_name,
                filename=h.filename,
                doc_type=h.doc_type,
            mp_id=h.mp_id,
            section_id=h.section_id,
            heading=h.heading,
            page_start=h.page_start,
                page_end=h.page_end,
                snippet=h.snippet,
                open_url=f"/documents/open?filename={quote(h.filename)}&page={h.page_start}",
                chunk_kind=getattr(h, "chunk_kind", None),
                table_uid=getattr(h, "table_uid", None),
                table_label=getattr(h, "table_label", None),
                table_row_index=getattr(h, "table_row_index", None),
            )
            for h in hits
        ]

    original_citations = citations
    if req.mode == "answer":
        citations = filter_citations_by_answer_markers(out.get("answer", ""), citations)
    elif req.mode == "sources_only":
        citations = filter_sources_only(citations, req.k)
        target = extract_section_id(req.query)
        if target:
            # Use prefix match so "701" matches "701.03.01"; keep originals if none match.
            filtered = [c for c in citations if section_prefix_match(target, c.section_id)]
            if filtered:
                citations = filtered

    if not citations:
        # LLM answers may omit [n] markers; still return a few top citations for UI evidence.
        citations = original_citations[: min(3, len(original_citations))]

    return AskResponse(
        query=req.query,
        scope=req.scope,
        mp_ids=req.mp_ids,
        confidence=out.get("confidence"),
        answer=out.get("answer", ""),
        citations=citations,
        table=out.get("table"),
    )
