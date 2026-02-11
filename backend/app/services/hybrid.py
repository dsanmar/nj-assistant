from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.services.bm25 import bm25_search_filtered, BM25Hit
from app.services.faiss_store import faiss_search_filtered, FaissHit
from app.services.rerank import is_section_intent, toc_entry_count, toc_penalty


@dataclass
class HybridHit:
    # final fused score (RRF)
    score: float

    document_id: int
    filename: str
    display_name: str
    doc_type: str
    mp_id: Optional[str]
    page_number: int
    snippet: str

    # for debugging/explainability
    bm25_score: Optional[float] = None
    vec_score: Optional[float] = None


def reciprocal_rank_fusion(
    ranked_lists: list[list[tuple[int, int]]],
    k: int = 60,
) -> dict[tuple[int, int], float]:
    """
    RRF: sum( 1 / (k + rank) ) over ranked lists.
    Key is (document_id, page_number).
    """
    fused: dict[tuple[int, int], float] = {}
    for lst in ranked_lists:
        for rank, key in enumerate(lst, start=1):
            fused[key] = fused.get(key, 0.0) + 1.0 / (k + rank)
    return fused


def compute_confidence(
    top_rrf: float,
    overlap_top10: int,
) -> str:
    """
    Explainable heuristic confidence.
    - Strong: methods agree (overlap) and top score is clearly above baseline
    - Medium: decent top score
    - Weak: otherwise
    """
    if top_rrf >= 0.035 and overlap_top10 >= 1:
        return "strong"
    if top_rrf >= 0.02:
        return "medium"
    return "weak"


def hybrid_search(
    query: str,
    k: int = 8,
    scope: str = "all",
    mp_ids: list[str] | None = None,
) -> tuple[list[HybridHit], str]:
    # Pull more than k so fusion has enough candidates
    bm25_hits: list[BM25Hit] = bm25_search_filtered(query=query, k=max(20, k), scope=scope, mp_ids=mp_ids)
    vec_hits: list[FaissHit] = faiss_search_filtered(query=query, k=max(20, k), scope=scope, mp_ids=mp_ids)

    bm25_keys = [(h.document_id, h.page_number) for h in bm25_hits]
    vec_keys = [(h.document_id, h.page_number) for h in vec_hits]

    fused = reciprocal_rank_fusion([bm25_keys, vec_keys], k=60)

    # Score maps for explainability
    bm25_map = {(h.document_id, h.page_number): h for h in bm25_hits}
    vec_map = {(h.document_id, h.page_number): h for h in vec_hits}

    section_intent = is_section_intent(query)

    def fused_with_penalty(key: tuple[int, int]) -> float:
        base = fused[key]
        b = bm25_map.get(key)
        v = vec_map.get(key)
        text = None
        if b is not None:
            text = b.snippet
        if v is not None and text is None:
            text = v.snippet
        return base * toc_penalty(text or "", strong=section_intent)

    ranked_keys = sorted(fused.keys(), key=fused_with_penalty, reverse=True)[: max(k * 5, 50)]

    results: list[HybridHit] = []
    for key in ranked_keys:
        b = bm25_map.get(key)
        v = vec_map.get(key)
        ref = b or v
        if not ref:
            continue

        results.append(
            HybridHit(
                score=float(fused[key]),
                document_id=ref.document_id,
                filename=ref.filename,
                display_name=ref.display_name,
                doc_type=ref.doc_type,
                mp_id=ref.mp_id,
                page_number=ref.page_number,
                snippet=ref.snippet,
                bm25_score=(b.bm25_score if b else None) if hasattr(b, "bm25_score") else (b.score if b else None),
                vec_score=(v.score if v else None),
            )
        )

    # Post-filter TOC junk for section-intent queries
    if is_section_intent(query):
        cleaned = []
        for h in results:
            snip_upper = (h.snippet or "").upper()
            if "TABLE OF CONTENTS" in snip_upper:
                continue
            if toc_entry_count(h.snippet or "") >= 6:
                continue
            cleaned.append(h)
        results = cleaned[:k]

    overlap_top10 = len(set(bm25_keys[:10]) & set(vec_keys[:10]))
    conf = compute_confidence(results[0].score, overlap_top10) if results else "weak"
    return results, conf
