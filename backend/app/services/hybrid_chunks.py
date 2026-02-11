from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import re

from app.services.bm25_chunks import bm25_chunks_search_filtered, BM25ChunkHit
from app.services.faiss_chunks import faiss_chunks_search_filtered, FaissChunkHit
from app.services.db import get_conn
from app.services.rerank import is_section_intent


def extract_section_dot(query: str) -> str | None:
    # supports 701.02 and 701.02.01
    m = re.search(r"\b(\d{3}\.\d{2}(?:\.\d{2})?)\b", query or "")
    return m.group(1) if m else None


def extract_section_prefix(query: str) -> str | None:
    q = query or ""
    m = re.search(r"\bsection\s*(\d{3})\b", q, re.I)
    if m:
        return m.group(1)
    m = re.search(r"\b§\s*(\d{3})\b", q)
    if m:
        return m.group(1)
    return None


_TABLE_QUERY_RE = re.compile(r"\b(table|tbl|tab\.)\b", re.I)
_EQUATION_QUERY_RE = re.compile(
    r"\b(equation|equations|formula|calculate|calculation|compute|how to compute|pay adjustment|ppa|pd|ql|iri)\b",
    re.I,
)


def is_table_query(q: str) -> bool:
    return bool(_TABLE_QUERY_RE.search(q or ""))


def is_equation_query(q: str) -> bool:
    return bool(_EQUATION_QUERY_RE.search(q or ""))


def table_row_count(table_uid: str) -> int:
    with get_conn() as conn:
        r = conn.execute(
            "SELECT COUNT(1) AS n FROM table_rows WHERE table_uid = ?",
            (table_uid,),
        ).fetchone()
    return int(r["n"]) if r and r["n"] is not None else 0


def boost_table_hits_for_table_queries(query: str, hits: list) -> list:
    """
    Boost tables that look like real multi-row tables and/or match a likely section/table reference.
    """
    q = (query or "").lower()

    m = re.search(r"\b(\d{3}\.\d{2}(?:\.\d{2})?)\b", q)
    target_section = m.group(1) if m else None

    boosted = []
    for h in hits:
        score = float(getattr(h, "score", 0.0))
        tuid = getattr(h, "table_uid", None)
        heading = (getattr(h, "heading", "") or "").lower()
        section_id = (getattr(h, "section_id", "") or "").lower()
        snippet = (getattr(h, "snippet", "") or "").lower()

        if tuid:
            nrows = table_row_count(tuid)

            if nrows >= 6:
                score += 0.08
            elif nrows <= 2:
                score -= 0.03

            if "coarse aggregate" in heading or "coarse aggregate" in snippet:
                score += 0.05

            if "table" in snippet:
                score += 0.03

            if target_section and section_id == target_section:
                score += 0.12

        boosted.append((score, h))

    boosted.sort(key=lambda x: x[0], reverse=True)
    return [h for _, h in boosted]


def _text_dominant_section(snippet: str) -> str | None:
    if not snippet:
        return None
    head = snippet[:350]
    m = re.search(r"(?m)^\s*(\d{3}\.\d{2}(?:\.\d{2})?)\b", head)
    return m.group(1) if m else None


@dataclass
class HybridChunkHit:
    score: float  # fused (RRF)
    chunk_id: int

    document_id: int
    filename: str
    display_name: str
    doc_type: str
    mp_id: Optional[str]

    section_id: Optional[str]
    heading: Optional[str]
    page_start: int
    page_end: int

    snippet: str
    chunk_kind: Optional[str] = None
    bm25_score: Optional[float] = None
    vec_score: Optional[float] = None
    table_uid: Optional[str] = None
    table_row_index: Optional[int] = None
    table_label: Optional[str] = None


def reciprocal_rank_fusion(
    ranked_lists: list[list[int]],
    k: int = 60,
) -> dict[int, float]:
    fused: dict[int, float] = {}
    for lst in ranked_lists:
        for rank, key in enumerate(lst, start=1):
            fused[key] = fused.get(key, 0.0) + 1.0 / (k + rank)
    return fused


def compute_confidence(top_rrf: float, overlap_top10: int) -> str:
    if top_rrf >= 0.035 and overlap_top10 >= 1:
        return "strong"
    if top_rrf >= 0.02:
        return "medium"
    return "weak"


def hybrid_chunks_search(
    query: str,
    k: int = 8,
    scope: str = "all",
    mp_ids: list[str] | None = None,
) -> tuple[list[HybridChunkHit], str]:
    # Pull deeper candidate pools so we can rerank AFTER fusion.
    pool_k = max(60, k * 12)

    bm25_hits: list[BM25ChunkHit] = bm25_chunks_search_filtered(
        query=query, k=pool_k, scope=scope, mp_ids=mp_ids
    )
    vec_hits: list[FaissChunkHit] = faiss_chunks_search_filtered(
        query=query, k=pool_k, scope=scope, mp_ids=mp_ids
    )

    bm25_keys = [h.chunk_id for h in bm25_hits]
    vec_keys = [h.chunk_id for h in vec_hits]
    ranked_lists: list[list[int]] = [bm25_keys, vec_keys]

    eq_bm25_hits: list[BM25ChunkHit] = []
    eq_vec_hits: list[FaissChunkHit] = []
    if is_equation_query(query):
        eq_bm25_hits = bm25_chunks_search_filtered(
            query=query,
            k=50,
            scope=scope,
            mp_ids=mp_ids,
            min_equation_score=0.45,
        )
        eq_vec_hits = faiss_chunks_search_filtered(
            query=query,
            k=50,
            scope=scope,
            mp_ids=mp_ids,
            min_equation_score=0.45,
        )
        eq_keys: list[int] = []
        seen = set()
        for h in eq_bm25_hits + eq_vec_hits:
            if h.chunk_id in seen:
                continue
            seen.add(h.chunk_id)
            eq_keys.append(h.chunk_id)
        if eq_keys:
            ranked_lists.append(eq_keys)

    fused = reciprocal_rank_fusion(ranked_lists, k=60)

    bm25_map = {h.chunk_id: h for h in bm25_hits}
    vec_map = {h.chunk_id: h for h in vec_hits}
    eq_map = {h.chunk_id: h for h in eq_bm25_hits}
    eq_map.update({h.chunk_id: h for h in eq_vec_hits})

    # IMPORTANT: keep a bigger fused pool; do NOT truncate to k yet.
    ranked_ids = sorted(fused.keys(), key=lambda cid: fused[cid], reverse=True)[: max(pool_k, 120)]

    results: list[HybridChunkHit] = []
    for cid in ranked_ids:
        b = bm25_map.get(cid)
        v = vec_map.get(cid)
        ref = b or v or eq_map.get(cid)
        if not ref:
            continue

        results.append(
            HybridChunkHit(
                score=float(fused[cid]),
                chunk_id=int(cid),
                document_id=int(ref.document_id),
                filename=ref.filename,
                display_name=ref.display_name,
                doc_type=ref.doc_type,
                mp_id=ref.mp_id,
                section_id=getattr(ref, "section_id", None),
                heading=getattr(ref, "heading", None),
                page_start=int(getattr(ref, "page_start", 0)),
                page_end=int(getattr(ref, "page_end", 0)),
                snippet=ref.snippet,
                chunk_kind=getattr(ref, "chunk_kind", None),
                bm25_score=(b.score if b else None),
                vec_score=(v.score if v else None),
                table_uid=getattr(ref, "table_uid", None),
                table_row_index=getattr(ref, "table_row_index", None),
                table_label=getattr(ref, "table_label", None),
            )
        )

    # ---- section intent cleanup/boost (same logic, just runs on bigger pool) ----
    section_prefix = extract_section_prefix(query)
    exact_section = extract_section_dot(query)

    if is_section_intent(query):
        results = [h for h in results if h.chunk_kind not in ("toc", "front_matter")]

        cleaned: list[HybridChunkHit] = []
        for h in results:
            dom = _text_dominant_section(h.snippet)
            if h.section_id and dom and dom != h.section_id:
                continue
            cleaned.append(h)
        results = cleaned

        if exact_section:
            preferred = [h for h in results if h.section_id == exact_section]
            if preferred:
                results = preferred + [h for h in results if h not in preferred]
        elif section_prefix:
            preferred = [h for h in results if h.section_id and h.section_id.startswith(section_prefix)]
            if preferred:
                results = preferred + [h for h in results if h not in preferred]

    # ---- Equation intent: boost equation-tagged chunks ----
    if is_equation_query(query):
        for h in results:
            if h.chunk_kind == "equation":
                h.score = float(h.score) * 1.35
        results.sort(key=lambda x: x.score, reverse=True)

    # ---- NEW: if query looks like "Table 901.03-1", boost chunks that contain that exact table token ----
    qlow = (query or "").lower()
    table_token = None
    m = re.search(r"\btable\s*([0-9]{3}\.[0-9]{2}-[0-9]+)\b", qlow)
    if m:
        table_token = m.group(1)  # e.g. "901.03-1"

    if table_token:
        def _table_token_bonus(h: HybridChunkHit) -> float:
            s = (h.snippet or "").lower()
            # Prefer chunks that actually contain "table 901.03-1" AND look table-y (lots of numbers/sieve sizes)
            bonus = 0.0
            if f"table {table_token}" in s:
                bonus += 0.15
                if re.search(r"\b(percent|percentage|sieve|no\.\s*\d+)\b", s):
                    bonus += 0.08
                if sum(ch.isdigit() for ch in s) >= 25:
                    bonus += 0.05
            # Penalize "specified Table X" mention-only lines
            if (not h.table_uid) and f"specified table {table_token}" in s and sum(ch.isdigit() for ch in s) < 10:
                bonus -= 0.08
            return bonus

        for h in results:
            h.score = float(h.score + _table_token_bonus(h))
        results.sort(key=lambda x: x.score, reverse=True)

    # Table intent shaping (now meaningful because we still have the full pool)
    results = _table_group_boost(results, query)
    results = collapse_tables(results, k=max(pool_k, 120))
    if is_table_query(query):
        results = boost_table_hits_for_table_queries(query, results)
    results.sort(key=lambda x: getattr(x, "score", 0.0), reverse=True)

    # Confidence (use post-processed top hit if present)
    if results:
        overlap_top10 = len(set(bm25_keys[:10]) & set(vec_keys[:10]))
        conf = compute_confidence(results[0].score, overlap_top10)
    else:
        conf = "weak"

    return results[:k], conf



def _table_group_boost(results: list[HybridChunkHit], query: str) -> list[HybridChunkHit]:
    """
    If multiple rows from the same table appear, move that table up and keep a few rows.
    This makes table retrieval feel intentional (not random lines).
    """
    if not results:
        return results

    q = (query or "").lower()
    table_intent = (
        ("table" in q)
        or ("chart" in q)
        or ("row" in q)
        or ("values" in q)
        or ("limit" in q)
    )

    if not table_intent:
        return results

    by_uid: dict[str, list[HybridChunkHit]] = {}
    non_table: list[HybridChunkHit] = []

    for h in results:
        if h.table_uid:
            by_uid.setdefault(h.table_uid, []).append(h)
        else:
            non_table.append(h)

    # Only promote a table if we actually retrieved multiple rows from the same table
    eligible = {uid: rows for uid, rows in by_uid.items() if len(rows) >= 2}
    if not eligible:
        return results

    best_uid = max(
        eligible.keys(),
        key=lambda uid: (len(eligible[uid]), max(x.score for x in eligible[uid])),
    )

    best_rows = sorted(eligible[best_uid], key=lambda x: x.score, reverse=True)[:6]
    rest = [h for h in results if (not h.table_uid) or (h.table_uid != best_uid)]
    out = best_rows + rest
    out.sort(key=lambda x: x.score, reverse=True)
    return out


def collapse_tables(hits: list, k: int) -> list:
    """
    Group table rows by table_uid so the API returns "tables" not spam rows.
    Strategy:
      - if hit has table_uid, group it
      - keep the highest-scoring hit per table_uid
      - keep non-table hits as-is
    """
    best_by_table: dict[str, object] = {}
    non_table: list[object] = []

    for h in hits:
        tuid = getattr(h, "table_uid", None)
        if tuid:
            prev = best_by_table.get(tuid)
            if prev is None or getattr(h, "score", 0.0) > getattr(prev, "score", 0.0):
                best_by_table[tuid] = h
        else:
            non_table.append(h)

    merged = list(best_by_table.values()) + non_table
    merged.sort(key=lambda x: getattr(x, "score", 0.0), reverse=True)
    return merged[:k]
