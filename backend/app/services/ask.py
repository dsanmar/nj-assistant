from __future__ import annotations

import logging
import re
from urllib.parse import quote
from dataclasses import dataclass
from typing import Optional, Iterable

from rank_bm25 import BM25Okapi

from app.services.db import get_conn
from app.services.hybrid_chunks import hybrid_chunks_search
from app.services.llm import get_llm, LLMMessage, LLMError
from app.services.rerank import is_section_intent
from app.services.tables import get_table_meta, get_table_rows


SYSTEM_PROMPT = """You are NJDOT Knowledge Hub, a retrieval-first assistant.

You MUST use only the provided SOURCES to write the answer.

Rules:
- Do not introduce facts not present in SOURCES.
- Do not generalize beyond the scope of a source. If a source is limited to a specific subsection or context (e.g., bonding/grounding), do not apply it to the entire section unless the source explicitly does.
- Do not infer details from headings/titles alone. If a source only provides a heading without details, say the details are not present in the retrieved sources.
- If SOURCES do not contain the answer, say so clearly.
- Keep answers concise and user-friendly.
- Avoid listing many internal section cross-references (e.g., 903.03) in the main answer unless the user explicitly asks for them. Point the user to the citations panel for exact references.
- If a SOURCE contains a list/table-like set of items (multiple items separated by dot leaders, newlines, or obvious list formatting), reproduce the items verbatim as bullet points or short lines and keep a citation on the list.

Citations:
- Every sentence must end with at least one citation like [1] or [1][2] that maps to the SOURCES list.
- If a claim is not directly supported by a source, DO NOT include it.

Return ONLY valid JSON:
{
  "answer": "string"
}
"""

SYNTHESIS_PROMPT = """You are NJDOT Knowledge Hub, a retrieval-first assistant.

Use ONLY the provided SOURCES to answer the question.
Answer in 2–4 sentences. Paraphrase; do NOT quote long passages.
If the evidence is insufficient, respond exactly: "Insufficient Evidence."
Do not add citations or mention chunk IDs.
Do NOT include bracketed citations like [1] or [2].
Do NOT mention section numbers or page numbers unless the user explicitly asks for a section/page.
Avoid phrases like "as specified in Section..." unless the user asked for section/page.
Do NOT write "SOURCE 1", "SOURCE 2", or "SOURCE:" in the answer.
Do NOT say "according to the sources" or "the source states".
Do NOT leave incomplete clauses (no trailing "according to.").
If you mention an amount/time/percentage, state it directly.
"""
logger = logging.getLogger(__name__)


# -----------------------------
# Utilities
# -----------------------------

def _make_query_focused_snippet(text: str, query: str, *, window: int = 240, max_len: int = 450) -> str:
    """
    Build a snippet centered around the best match of query terms (or numbers).
    Falls back to start-of-text if no match.
    """
    t = (text or "").replace("\n", " ").strip()
    if not t:
        return ""

    q = (query or "").lower()

    patterns = []

    # exact phrases we commonly care about
    for ph in [" days", " day", " within ", " interest", " subcontractor", " supplier", " receipt", " prime rate"]:
        if ph.strip() in q:
            patterns.append(re.escape(ph.strip()))

    # statute patterns like "52:32-40"
    m_stat = re.findall(r"\b\d{1,3}:\d{1,3}-\d+\b", q)
    for s in m_stat:
        patterns.append(re.escape(s))

    # any plain numbers
    m_nums = re.findall(r"\b\d+\b", q)
    for n in m_nums:
        patterns.append(rf"\b{re.escape(n)}\b")

    # keywords
    q_terms = [w for w in re.findall(r"[a-z0-9]+", q) if len(w) >= 4]
    for w in q_terms[:12]:
        patterns.append(rf"\b{re.escape(w)}\b")

    # Find best match position (prefer proximity to receipt/payment language).
    anchors = ["receipt", "receiving", "payment", "paid", "interest", "prime rate"]
    anchor_positions = []
    for a in anchors:
        for m in re.finditer(rf"\b{re.escape(a)}\b", t, flags=re.I):
            anchor_positions.append(m.start())

    def _score(pos: int) -> tuple[int, int]:
        if anchor_positions:
            dist = min(abs(pos - a) for a in anchor_positions)
            # Higher score for closer to anchors; tie-breaker prefers later matches.
            return (-dist, pos)
        return (0, pos)

    best_pos = None
    best_score = None
    for pat in patterns:
        for m in re.finditer(pat, t, flags=re.I):
            pos = m.start()
            score = _score(pos)
            if best_score is None or score > best_score:
                best_score = score
                best_pos = pos

    if best_pos is None:
        snip = t[:max_len]
        return snip.rstrip() + ("…" if len(t) > max_len else "")

    start = max(0, best_pos - window)
    end = min(len(t), best_pos + window)

    snip = t[start:end].strip()
    if start > 0:
        snip = "…" + snip
    if end < len(t):
        snip = snip + "…"

    if len(snip) > max_len:
        snip = snip[:max_len].rstrip() + "…"
    return snip


def _is_time_limit_question(query: str) -> bool:
    q = (query or "").lower()
    return bool(
        re.search(r"\bwithin how many days\b|\bwithin \d+ days\b|\bdays after\b|\bwithin .* days\b", q)
    )


def _has_payment_days_phrase(text: str) -> bool:
    if not text:
        return False
    patterns = [
        r"\b(\d+)\s+days.{0,120}\b(receipt|receiv|payment|paid)\b",
        r"\b(receipt|receiv|payment|paid)\b.{0,120}\b(\d+)\s+days\b",
    ]
    return any(re.search(p, text, flags=re.I) for p in patterns)


def _hydrate_text_for_hits(hits) -> dict[int, str]:
    ids = [int(getattr(h, "chunk_id")) for h in hits if getattr(h, "chunk_id", None) is not None]
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT id, text FROM chunks WHERE id IN ({placeholders})",
            ids,
        ).fetchall()
    return {int(r["id"]): (r["text"] or "") for r in rows}

def _format_sources(hits) -> str:
    blocks = []
    for i, h in enumerate(hits, start=1):
        blocks.append(
            f"""[SOURCE {i}]
Document: {h.display_name}
Filename: {h.filename}
DocType: {h.doc_type}
MP_ID: {h.mp_id or ""}
Section: {h.section_id or ""}
Heading: {h.heading or ""}
Pages: {h.page_start}-{h.page_end}
Excerpt:
{h.snippet}
"""
        )
    return "\n".join(blocks)

def _format_sources_compact(hits) -> str:
    blocks = []
    for i, h in enumerate(hits, start=1):
        blocks.append(
            f"""[SOURCE {i}]
Section: {h.section_id or ""}
Pages: {h.page_start}-{h.page_end}
Excerpt:
{h.snippet}
"""
        )
    return "\n".join(blocks)


def _llm_error_code(err: Exception) -> str:
    cause = getattr(err, "__cause__", None)
    for obj in (err, cause):
        if obj is None:
            continue
        for attr in ("code", "status_code", "error_code"):
            val = getattr(obj, attr, None)
            if val:
                return str(val)
    return "unknown"


def _llm_fallback_answer(hits):
    if hits:
        snippet = (hits[0].snippet or "").strip()
        if snippet:
            answer = snippet if snippet.endswith("]") else f"{snippet} [1]"
        else:
            answer = "Insufficient Evidence in retrieved sources. [1]"
        return {"confidence": "medium", "answer": answer, "hits": hits[:1]}
    return {"confidence": "low", "answer": "Insufficient Evidence.", "hits": []}


def _log_path(path: str, *, scope: str, mp_ids: list[str] | None, k: int, mode: str, conf: str) -> None:
    logger.info(
        "ask.path=%s scope=%s mp_ids=%s k=%s mode=%s confidence=%s",
        path,
        scope,
        mp_ids or [],
        k,
        mode,
        conf,
    )


def _extract_cited_source_nums(answer: str) -> set[int]:
    nums = set()
    for m in re.finditer(r"\[(\d+)\]", answer or ""):
        try:
            nums.add(int(m.group(1)))
        except Exception:
            pass
    return nums


_STRONG_HEADER_AT_LINE_START = re.compile(r"^\s*(\d{3}\.\d{2}(?:\.\d{2})?)\b", re.M)


def _looks_like_true_section_start(text: str, section_id: str) -> bool:
    """
    True section start signal:
    - any line starts with the exact section id
    OR
    - the text starts with it after whitespace
    """
    if not text or not section_id:
        return False
    head = text[:400]
    if re.match(rf"^\s*{re.escape(section_id)}\b", head):
        return True
    for m in _STRONG_HEADER_AT_LINE_START.finditer(head):
        if m.group(1) == section_id:
            return True
    return False


def _dominant_section_in_text(text: str) -> str | None:
    """
    Returns the first strong-looking section at start of a line within the first ~600 chars.
    This catches cases where snippet clearly starts a different section than metadata.
    """
    if not text:
        return None
    head = text[:600]
    m = re.search(r"(?m)^\s*(\d{3}\.\d{2}(?:\.\d{2})?)\b", head)
    return m.group(1) if m else None


# Exact section IDs like:
# 701.02
# 701.02.01
# 105.01.02
def _extract_exact_section_id(query: str) -> str | None:
    q = (query or "").strip()
    if re.fullmatch(r"\d{3}\.\d{2}(?:\.\d{2})?", q):
        return q
    m = re.match(r"^\s*(\d{3}\.\d{2}(?:\.\d{2})?)\b", q)
    return m.group(1) if m else None


# Section prefix ONLY when user explicitly signals it:
# "Section 701" or "§701"
# (NOT any random 3 digits in the sentence)
def _extract_section_prefix(query: str) -> str | None:
    q = query or ""
    m = re.search(r"\bsection\s*(\d{3})\b", q, re.I)
    if m:
        return m.group(1)
    m = re.search(r"\b§\s*(\d{3})\b", q)
    if m:
        return m.group(1)

    # Allow bare "701" ONLY if the query is basically just that token
    # (prevents accidental prefix extraction in normal sentences)
    if re.fullmatch(r"\s*\d{3}\s*", q.strip()):
        return q.strip()

    return None


def _select_section_hits(hits: list, min_hits: int = 4, max_hits: int = 6) -> list:
    if not hits:
        return []
    n = min(max_hits, max(min_hits, len(hits)))
    return hits[:n]


def _trim_snippet(text: str, max_len: int = 600) -> str:
    s = (text or "").strip()
    if len(s) > max_len:
        s = s[:max_len].rstrip() + "..."
    return s


def _build_section_excerpt(section_id: str | None, hits: list) -> str:
    section_label = section_id or (getattr(hits[0], "section_id", None) if hits else None) or "Section"
    lines = [f"{section_label} — Relevant excerpts from NJDOT manuals:"]
    for idx, h in enumerate(hits, start=1):
        heading = (getattr(h, "heading", "") or "").strip()
        page_start = int(getattr(h, "page_start", 0) or 0)
        page_end = int(getattr(h, "page_end", 0) or 0)
        if page_end and page_end != page_start:
            pages = f"pp. {page_start}-{page_end}"
        else:
            pages = f"p. {page_start}"
        snippet = _trim_snippet(getattr(h, "snippet", "") or "")
        if heading:
            lines.append(f"[{idx}] {heading} ({pages}): {snippet}")
        else:
            lines.append(f"[{idx}] ({pages}): {snippet}")
    return "\n".join(lines).strip()


# -----------------------------
# DB fallback hits
# -----------------------------

@dataclass
class _DBHit:
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
    chunk_kind: Optional[str]
    text: str

    # for compatibility with other code
    table_uid: Optional[str] = None
    table_label: Optional[str] = None
    score: float = 0.0


_STOPWORDS = {
    "what", "requirement",
    "section", "sections", "the", "a", "an", "for", "of", "is", "are",
    "in", "to", "and", "does", "say", "about",
}

def _tokenize_bm25(text: str) -> list[str]:
    tokens = [t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if t not in _STOPWORDS]
    return tokens or ["_"]


def _tokenize_relevance(text: str) -> set[str]:
    return {
        t
        for t in re.findall(r"[a-z0-9]+", (text or "").lower())
        if t not in _STOPWORDS and len(t) >= 3
    }


def _extract_section_pattern(query: str) -> str | None:
    m = re.search(r"\b\d{3}\.\d{2}(?:\.\d{2})?\b", query or "")
    return m.group(0) if m else None


def _is_relevant_hit(query: str, hit) -> bool:
    q = query or ""
    section_pat = _extract_section_pattern(q)
    if section_pat:
        section_id = getattr(hit, "section_id", None) or ""
        if section_id.startswith(section_pat):
            return True

    q_tokens = _tokenize_relevance(q)
    if not q_tokens:
        return False
    snippet = (getattr(hit, "snippet", "") or "").lower()
    if any(tok in snippet for tok in q_tokens):
        return True
    s_tokens = _tokenize_relevance(snippet)
    overlap = q_tokens & s_tokens
    return len(overlap) >= 2


def _weak_response(hits, query: str) -> dict:
    msg = (
        "Insufficient Evidence. I couldn’t find a reliable answer in the provided NJDOT manuals for that question. "
        "Try rephrasing using a section number, exact term, or MP ID, or switch to Sources Only."
    )
    if not hits:
        return {"confidence": "weak", "answer": msg, "hits": []}
    top = hits[0]
    if not _is_relevant_hit(query, top):
        return {"confidence": "weak", "answer": msg, "hits": []}
    snippet = (getattr(top, "snippet", "") or "").strip()
    if not snippet:
        return {"confidence": "weak", "answer": msg, "hits": []}
    answer = f"Closest match from NJDOT manuals: {snippet} [1]"
    return {"confidence": "weak", "answer": answer, "hits": hits[:1]}


def _bm25_rerank(query: str, hits: list[_DBHit], k: int) -> list[_DBHit]:
    corpus = [_tokenize_bm25(h.text) for h in hits]
    bm25 = BM25Okapi(corpus)
    scores = bm25.get_scores(_tokenize_bm25(query))
    ranked = sorted(range(len(hits)), key=lambda i: scores[i], reverse=True)[:k]
    out = []
    for i in ranked:
        h = hits[i]
        h.score = float(scores[i])
        out.append(h)
    return out


def _apply_scope_filters(where: list[str], params: list[object], scope: str, mp_ids: list[str] | None) -> None:
    if scope != "all":
        if scope == "mp_only":
            where.append("d.doc_type = 'mp'")
        else:
            where.append("d.doc_type = ?")
            params.append(scope)

    # only applies when scoping to specific MPs
    if scope in ("mp_only", "mp") and mp_ids:
        placeholders = ",".join("?" for _ in mp_ids)
        where.append(f"UPPER(d.mp_id) IN ({placeholders})")
        params.extend([m.upper() for m in mp_ids])


def _make_snippet(text: str, n: int = 450) -> str:
    t = (text or "").replace("\n", " ").strip()
    if len(t) <= n:
        return t
    return t[:n].rstrip() + "…"


def _db_fetch_exact_section(
    section_id: str,
    *,
    scope: str,
    mp_ids: list[str] | None,
    limit: int,
) -> list[_DBHit]:
    where = [
        "c.section_id IS NOT NULL",
        "c.section_id = ?",
        "(c.chunk_kind IS NULL OR c.chunk_kind NOT IN ('toc','front_matter'))",
    ]
    params: list[object] = [section_id]
    _apply_scope_filters(where, params, scope, mp_ids)

    sql = f"""
        SELECT
            c.id AS chunk_id,
            c.document_id,
            d.filename,
            d.display_name,
            d.doc_type,
            d.mp_id,
            c.section_id,
            c.heading,
            c.page_start,
            c.page_end,
            c.chunk_kind,
            c.text
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE {" AND ".join(where)}
        ORDER BY c.page_start ASC, c.id ASC
        LIMIT ?
    """
    params.append(limit)

    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()

    hits: list[_DBHit] = []
    for r in rows:
        text = r["text"] or ""
        hits.append(
            _DBHit(
                chunk_id=int(r["chunk_id"]),
                document_id=int(r["document_id"]),
                filename=r["filename"],
                display_name=r["display_name"],
                doc_type=r["doc_type"],
                mp_id=r["mp_id"],
                section_id=r["section_id"],
                heading=r["heading"],
                page_start=int(r["page_start"]),
                page_end=int(r["page_end"]),
                snippet=_make_snippet(text),
                chunk_kind=r["chunk_kind"],
                text=text,
            )
        )
    return hits


def _db_fetch_exact_or_children(
    section_id: str,
    *,
    scope: str,
    mp_ids: list[str] | None,
    limit: int,
) -> list[_DBHit]:
    where = [
        "c.section_id IS NOT NULL",
        "(c.section_id = ? OR c.section_id LIKE ?)",
        "(c.chunk_kind IS NULL OR c.chunk_kind NOT IN ('toc','front_matter'))",
    ]
    params: list[object] = [section_id, f"{section_id}.%"]
    _apply_scope_filters(where, params, scope, mp_ids)

    sql = f"""
        SELECT
            c.id AS chunk_id,
            c.document_id,
            d.filename,
            d.display_name,
            d.doc_type,
            d.mp_id,
            c.section_id,
            c.heading,
            c.page_start,
            c.page_end,
            c.chunk_kind,
            c.text
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE {" AND ".join(where)}
        ORDER BY c.page_start ASC, c.id ASC
        LIMIT ?
    """
    params.append(limit)

    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()

    hits: list[_DBHit] = []
    for r in rows:
        text = r["text"] or ""
        hits.append(
            _DBHit(
                chunk_id=int(r["chunk_id"]),
                document_id=int(r["document_id"]),
                filename=r["filename"],
                display_name=r["display_name"],
                doc_type=r["doc_type"],
                mp_id=r["mp_id"],
                section_id=r["section_id"],
                heading=r["heading"],
                page_start=int(r["page_start"]),
                page_end=int(r["page_end"]),
                snippet=_make_snippet(text),
                chunk_kind=r["chunk_kind"],
                text=text,
            )
        )
    return hits


def _db_fetch_prefix_sections(
    prefix3: str,
    *,
    scope: str,
    mp_ids: list[str] | None,
    limit: int,
) -> list[_DBHit]:
    # matches 701, 701.*, etc.
    where = [
        "c.section_id IS NOT NULL",
        "(c.section_id = ? OR c.section_id LIKE ?)",
        "(c.chunk_kind IS NULL OR c.chunk_kind NOT IN ('toc','front_matter'))",
    ]
    params: list[object] = [prefix3, f"{prefix3}.%"]
    _apply_scope_filters(where, params, scope, mp_ids)

    sql = f"""
        SELECT
            c.id AS chunk_id,
            c.document_id,
            d.filename,
            d.display_name,
            d.doc_type,
            d.mp_id,
            c.section_id,
            c.heading,
            c.page_start,
            c.page_end,
            c.chunk_kind,
            c.text
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE {" AND ".join(where)}
        ORDER BY c.page_start ASC, c.id ASC
        LIMIT ?
    """
    params.append(limit)

    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()

    hits: list[_DBHit] = []
    for r in rows:
        text = r["text"] or ""
        hits.append(
            _DBHit(
                chunk_id=int(r["chunk_id"]),
                document_id=int(r["document_id"]),
                filename=r["filename"],
                display_name=r["display_name"],
                doc_type=r["doc_type"],
                mp_id=r["mp_id"],
                section_id=r["section_id"],
                heading=r["heading"],
                page_start=int(r["page_start"]),
                page_end=int(r["page_end"]),
                snippet=_make_snippet(text),
                chunk_kind=r["chunk_kind"],
                text=text,
            )
        )
    return hits


def _db_fetch_table_token_hits(
    table_token: str,
    *,
    scope: str,
    mp_ids: list[str] | None,
    limit: int,
) -> list[_DBHit]:
    normalized = _normalize_table_text(table_token)
    like = f"%{normalized}%"
    where = [
        "c.chunk_kind = 'table_row'",
        "c.table_uid IS NOT NULL",
        "("
        "lower(replace(replace(COALESCE(c.text,''),'–','-'),'—','-')) LIKE ? OR "
        "lower(replace(replace(COALESCE(c.heading,''),'–','-'),'—','-')) LIKE ? OR "
        "lower(replace(replace(COALESCE(c.table_label,''),'–','-'),'—','-')) LIKE ?"
        ")",
    ]
    params: list[object] = [like, like, like]
    _apply_scope_filters(where, params, scope, mp_ids)

    sql = f"""
        SELECT
            c.id AS chunk_id,
            c.document_id,
            d.filename,
            d.display_name,
            d.doc_type,
            d.mp_id,
            c.section_id,
            c.heading,
            c.page_start,
            c.page_end,
            c.chunk_kind,
            c.text,
            c.table_uid,
            c.table_label
        FROM chunks c
        JOIN documents d ON d.id = c.document_id
        WHERE {" AND ".join(where)}
        ORDER BY c.page_start ASC, c.id ASC
        LIMIT ?
    """
    params.append(limit)

    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()

    hits: list[_DBHit] = []
    for r in rows:
        text = r["text"] or ""
        hits.append(
            _DBHit(
                chunk_id=int(r["chunk_id"]),
                document_id=int(r["document_id"]),
                filename=r["filename"],
                display_name=r["display_name"],
                doc_type=r["doc_type"],
                mp_id=r["mp_id"],
                section_id=r["section_id"],
                heading=r["heading"],
                page_start=int(r["page_start"]),
                page_end=int(r["page_end"]),
                snippet=_make_snippet(text),
                chunk_kind=r["chunk_kind"],
                text=text,
                table_uid=r["table_uid"],
                table_label=r["table_label"],
            )
        )
    return hits


def _sanitize_exact_section_hits(section_id: str, hits: list[_DBHit]) -> list[_DBHit]:
    """
    Prefer chunks that actually look like the section starts there.
    Fallback to original ordering if none match.
    """
    strong: list[_DBHit] = []
    weak: list[_DBHit] = []
    for h in hits:
        heading_ok = bool(h.heading) and h.heading.strip().startswith(section_id)
        text_ok = _looks_like_true_section_start(h.text, section_id)
        if heading_ok or text_ok:
            strong.append(h)
        else:
            weak.append(h)
    return strong + weak


def _filter_mismatched_section_hits(
    hits: list[_DBHit],
    expected_prefix: str | None = None,
) -> list[_DBHit]:
    """
    For section-intent queries, drop chunks whose text starts with a different section_id
    that conflicts with their metadata or the expected prefix.
    """
    out: list[_DBHit] = []
    for h in hits:
        dom = _dominant_section_in_text(h.text)
        if expected_prefix and dom and not dom.startswith(expected_prefix):
            continue
        if h.section_id and dom and dom != h.section_id:
            continue
        out.append(h)
    return out


def _safe_confidence(conf: str, answer: str) -> str:
    a = (answer or "").lower()
    if (
        "couldn’t find" in a
        or "could not find" in a
        or "not present in sources" in a
        or "not contained in sources" in a
        or "insufficient evidence" in a
    ):
        return "weak"
    return conf


def _looks_like_list_table_snippet(snippet: str) -> bool:
    s = snippet or ""
    if "Provide materials as specified in" in s:
        return True
    # dot leaders often show up as "....." in extracted text
    if s.count("...") >= 3:
        return True
    # lots of newline-separated short items
    lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
    if len(lines) >= 4 and sum(len(ln) <= 80 for ln in lines) >= 3:
        return True
    return False


def _is_materials_heading(h) -> bool:
    heading = (getattr(h, "heading", None) or "")
    return "materials" in heading.lower()


def _make_answer_user_friendly(answer: str) -> str:
    """
    UI-friendly cleanup:
    - removes phrases like "specified in 701.02.01" from the chat bubble
    - keeps citations like [1]
    """
    if not answer:
        return answer
    # Strip leading section ids and all-caps headings when the answer is a raw excerpt.
    answer = re.sub(r"^\s*\d{3}(?:\.\d{2}){0,2}\s+", "", answer)
    answer = re.sub(r"^\s*[A-Z][A-Z0-9\s\-/]{6,}:\s*", "", answer)
    answer = re.sub(r"^\s*[A-Z][A-Z0-9\s\-/]{6,}\s+-\s*", "", answer)

    answer = re.sub(
        r"\bspecified in\s+\d{3}\.\d{2}(?:\.\d{2})?\b",
        "specified in the NJDOT manual",
        answer,
        flags=re.I,
    )
    answer = re.sub(
        r"\bin\s+\d{3}\.\d{2}(?:\.\d{2})?\b",
        "in the NJDOT manual",
        answer,
        flags=re.I,
    )
        # Optional: make phrasing smoother
    answer = re.sub(r"\bspecified in the NJDOT manual as:\s*", "", answer, flags=re.I)

    return answer


def _question_asks_for_section_or_page(query: str) -> bool:
    q = (query or "").lower()
    triggers = [
        "which section",
        "what section",
        "section number",
        "section id",
        "what page",
        "which page",
        "page number",
        "where in the manual",
        "where in the spec",
        "where can i find",
        "cite",
        "citation",
        "reference",
    ]
    if any(t in q for t in triggers):
        return True
    return bool(re.search(r"\b\d{3}\.\d{2}(?:\.\d{2})?\b", q, re.I))


def _is_bare_section_id_query(query: str) -> bool:
    return bool(re.fullmatch(r"\s*\d{3}\.\d{2}(?:\.\d{2})?\s*", query or ""))


def _strip_answer_metadata(answer: str, query: str) -> str:
    if not answer:
        return answer
    # Always remove bracketed citation markers.
    answer = re.sub(r"\s*\[\d+\]\s*", " ", answer).strip()
    # Remove SOURCE markers without dropping content.
    answer = re.sub(r"\s*[\(\[]?\s*source\s*\d+\s*[\)\]]?\s*", " ", answer, flags=re.I)
    answer = re.sub(r"\bsource\s*:\s*", "", answer, flags=re.I)

    if _question_asks_for_section_or_page(query):
        answer = re.sub(r"\s{2,}", " ", answer).strip(" ,.;:")
        return answer

    # Remove section/page callouts without deleting the surrounding sentence.
    answer = re.sub(
        r"\b(as specified in|per|in|see)\s+section\s+\d{3}(?:\.\d{2}){0,2}\b",
        "",
        answer,
        flags=re.I,
    )
    answer = re.sub(r"\bsection\s+\d{3}(?:\.\d{2}){0,2}\b", "", answer, flags=re.I)
    answer = re.sub(r"\bpages?\s+\d+\s*[-–]\s*\d+\b", "", answer, flags=re.I)
    answer = re.sub(r"\bpage\s+\d+\b", "", answer, flags=re.I)
    # Clean up dangling punctuation/spaces after removals.
    answer = re.sub(r"\s+([,.;:])", r"\1", answer)
    answer = re.sub(r"([,.;:])\s*,", r"\1", answer)
    answer = re.sub(r"\s{2,}", " ", answer).strip(" ,.;:")
    return answer


def _polish_answer_text(answer: str) -> str:
    if not answer:
        return answer
    # Remove meta phrasing without dropping the rest of the sentence.
    answer = re.sub(r"\b(according to|as stated in|as specified in)\b(?:\s+the)?\s+(sources?|source)\b", "", answer, flags=re.I)
    answer = re.sub(r"\b(stated in the source|provided sources|the sources say)\b", "", answer, flags=re.I)
    # Remove dangling trailing fragments.
    answer = re.sub(r"\baccording to(?: the provided sources)?\.?$", "", answer.strip(), flags=re.I)
    answer = re.sub(r"\bthis is specified(?: in)?\.?$", "", answer.strip(), flags=re.I)
    answer = re.sub(r"\bthis is stated(?: in)?\.?$", "", answer.strip(), flags=re.I)
    answer = re.sub(r"\bas stated in\.?$", "", answer.strip(), flags=re.I)
    answer = re.sub(r"\bthis is specified in\b$", "", answer.strip(), flags=re.I)
    answer = re.sub(
        r"\bthis requirement is specified(?: in| by)?\b[\.!\s]*$",
        "",
        answer.strip(),
        flags=re.I,
    )
    answer = re.sub(r"\bthis requirement is stated\b[\.!\s]*$", "", answer.strip(), flags=re.I)
    # Cleanup punctuation/spacing.
    answer = re.sub(r"\s+([,.;:])", r"\1", answer)
    answer = re.sub(r"([,.;:])\s*,", r"\1", answer)
    answer = re.sub(r"\s{2,}", " ", answer).strip()
    if answer and re.search(r"[A-Za-z0-9]$", answer):
        answer += "."
    return answer


def _keyword_overlap_score(query: str, hit) -> int:
    tokens = _tokenize_relevance(query)
    if not tokens:
        return 0
    text = f"{getattr(hit, 'heading', '') or ''} {getattr(hit, 'snippet', '') or ''}".lower()
    score = sum(1 for t in tokens if t in text)
    numeric_intent = any(
        t in query.lower()
        for t in ["minimum", "limit", "limits", "percent", "percentage", "days", "day", "$", "per occurrence"]
    ) or bool(re.search(r"\d", query))
    if numeric_intent and re.search(r"(\$?\d[\d,]*(?:\.\d+)?|\b\d+%\b|percent)", text):
        score += 2
    if ("liability" in query.lower() or "insurance" in query.lower()) and (
        "comprehensive general liability" in text or "general liability" in text
    ):
        score += 3
    return score


def _is_prompt_payment_interest_intent(q: str) -> bool:
    s = (q or "").lower()
    triggers = [
        "52:32-40",
        "52:32-41",
        "interest",
        "prime rate",
        "plus 1 percent",
        "accrue",
        "tenth day",
        "withholding payment",
    ]
    if any(t in s for t in triggers):
        return True
    return bool(re.search(r"\b52\s*:\s*32-4(0|1)\b", s))


def _statute_hit_score(h) -> int:
    text = (
        (getattr(h, "heading", "") or "")
        + " "
        + (getattr(h, "snippet", "") or "")
        + " "
        + (getattr(h, "text", "") or "")
    ).lower()
    keys = [
        "52:32-40",
        "52:32-41",
        "prime rate",
        "plus 1 percent",
        "tenth day",
        "interest begins to accrue",
    ]
    return sum(1 for k in keys if k in text)


def _extract_prompt_payment_days(text: str) -> str | None:
    if not text:
        return None
    patterns = [
        r"not paid within\s+(\d+)\s+days",
        r"within\s+(\d+)\s+days after receipt",
        r"within\s+(\d+)\s+days of receipt",
    ]
    for pat in patterns:
        m = re.search(pat, text, flags=re.I)
        if m:
            return m.group(1)
    return None


def _looks_like_table_query(q: str) -> bool:
    s = (q or "").lower()
    return any(w in s for w in ["table", "tab.", "chart", "tbl", "requirements table"])


def _looks_like_table_intent(query: str, hits) -> bool:
    if _looks_like_table_query(query):
        return True
    if not hits:
        return False
    top = hits[0]
    if not (getattr(top, "table_uid", None) or getattr(top, "chunk_kind", None) == "table_row"):
        return False
    q_tokens = _tokenize_relevance(query)
    if not q_tokens:
        return False
    text = f"{getattr(top, 'heading', '') or ''} {getattr(top, 'snippet', '') or ''}"
    h_tokens = _tokenize_relevance(text)
    return len(q_tokens & h_tokens) >= 2


def _extract_table_token(query: str) -> str | None:
    m = re.search(
        r"\btable\s*(\d{3}\.\d{2}\.\d{2}-\d+|\d{3}\.\d{2}-\d+)\b",
        query or "",
        re.I,
    )
    return m.group(1) if m else None


def _normalize_table_text(text: str) -> str:
    s = (text or "").lower()
    s = s.replace("–", "-").replace("—", "-")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _table_has_enough_rows(table_uid: str, min_rows: int = 4) -> bool:
    with get_conn() as conn:
        r = conn.execute(
            "SELECT COUNT(1) AS n FROM table_rows WHERE table_uid = ?",
            (table_uid,),
        ).fetchone()
    return bool(r and int(r["n"] or 0) >= min_rows)


_TABLE_DATA_UNITS = (
    "ft",
    "feet",
    "foot",
    "in",
    "inch",
    "inches",
    "mm",
    "cm",
    "psi",
    "mph",
    "day",
    "days",
    "month",
    "months",
    "year",
    "years",
    "lb",
    "lbs",
    "pound",
    "pounds",
    "%",
    "percent",
    "$",
)
_TABLE_INSTRUCTION_STARTS = (
    "secure",
    "install",
    "test",
    "after",
    "before",
    "provide",
    "submit",
    "remove",
    "ensure",
    "place",
    "set",
    "clean",
    "protect",
    "maintain",
    "apply",
    "perform",
    "furnish",
)


def _is_instruction_row(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if re.match(r"^\d+\.\s+", t):
        return True
    lower = t.lower()
    if any(lower.startswith(v + " ") for v in _TABLE_INSTRUCTION_STARTS):
        return True
    # Full sentence heuristic: ends with punctuation and has multiple words.
    if re.search(r"[.!?]\s*$", t) and len(t.split()) >= 6:
        return True
    return False


def _is_data_row(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    lower = t.lower()
    if re.search(r"\d", lower) and any(u in lower for u in _TABLE_DATA_UNITS):
        return True
    if re.search(r"\b\d+(\.\d+)?\s*%|\$\s*\d", lower):
        return True
    return False


def _build_table_rows_for_render(rows, preview_limit: int) -> list[dict]:
    def _is_header_row(text: str) -> bool:
        lower = text.lower().strip()
        if not lower or re.search(r"\d", lower):
            return False
        header_terms = {
            "item",
            "items",
            "description",
            "length",
            "length of slack",
            "slack",
            "minimum",
            "maximum",
            "min",
            "max",
            "percent passing",
            "% passing",
            "passing",
            "gradation",
            "size",
            "sizes",
            "unit",
            "units",
            "requirements",
        }
        if any(term in lower for term in header_terms) and len(lower.split()) <= 6:
            return True
        return False

    structured: list[dict] = []
    cleaned: list[tuple[int, str]] = []
    for r in rows:
        text = (r.row_text or "").strip()
        if not text:
            continue
        if _is_instruction_row(text):
            break
        if _is_header_row(text):
            continue
        cleaned.append((int(r.row_index), text))

    i = 0
    while i < len(cleaned) and len(structured) < preview_limit:
        idx, text = cleaned[i]
        if _is_data_row(text):
            structured.append({"row_index": idx, "row_text": text})
            i += 1
            continue
        next_text = cleaned[i + 1][1] if i + 1 < len(cleaned) else ""
        if next_text and _is_data_row(next_text):
            merged = f"{text} — {next_text}"
            structured.append({"row_index": idx, "row_text": merged})
            i += 2
            continue
        if len(text) <= 120 and not re.search(r"[.!?]\s*$", text):
            structured.append({"row_index": idx, "row_text": text})
        i += 1
    return structured


def _build_table_link_answer(label: str) -> str:
    return f"{label}\n"


def _is_junk_table_label(label: str) -> bool:
    s = (label or "").strip().lower()
    return bool(re.match(r"^table\s*\(p\.\s*\d+\)\s*#\d+$", s))


def _extract_table_number_and_title(text: str) -> tuple[str | None, str | None]:
    if not text:
        return None, None
    m = re.search(
        r"\btable\s*(\d{3}\.\d{2}(?:\.\d{2})?-\d+)\b(?:\s*[-—–:]\s*([^\n\r]+))?",
        text,
        re.I,
    )
    if not m:
        return None, None
    number = m.group(1)
    title = (m.group(2) or "").strip()
    if title:
        title = re.sub(r"\s*\(p\.\s*\d+\)\s*#\d+\s*$", "", title, flags=re.I).strip()
    return number, title or None


def _build_table_display_title(
    *,
    table_token: str | None,
    meta_label: str | None,
    text_candidates: Iterable[str],
) -> str:
    number = None
    title = None

    if meta_label and not _is_junk_table_label(meta_label):
        number, title = _extract_table_number_and_title(meta_label)
        if not number:
            number = None

    if table_token:
        number = table_token

    if not number or not title:
        for text in text_candidates:
            n, t = _extract_table_number_and_title(text or "")
            if not number and n:
                number = n
            if not title and t:
                title = t
            if number and title:
                break

    if number and title:
        return f"Table {number} — {title}"
    if number:
        return f"Table {number}"
    if meta_label and not _is_junk_table_label(meta_label):
        return meta_label.strip()
    return "Table"


def _top_table_block(hits) -> tuple[str | None, str | None, list]:
    """
    Returns (table_uid, table_label, rows_hits) for the dominant table in hits.
    """
    table_hits = [h for h in hits if getattr(h, "table_uid", None)]
    if not table_hits:
        return None, None, []
    by_uid: dict[str, list] = {}
    for h in table_hits:
        by_uid.setdefault(h.table_uid, []).append(h)
    best_uid = max(by_uid.keys(), key=lambda uid: len(by_uid[uid]))
    rows = by_uid[best_uid][:8]
    label = getattr(rows[0], "table_label", None) or "Table"
    return best_uid, label, rows


# -----------------------------
# Main entry
# -----------------------------

def _ask_question_inner(
    query: str,
    *,
    scope: str = "all",
    mp_ids: list[str] | None = None,
    k: int = 6,
    mode: str = "answer",
) -> dict:
    q = query or ""

    exact = _extract_exact_section_id(q)
    prefix = _extract_section_prefix(q)
    table_token = _extract_table_token(q)
    explicit_table = bool(table_token and re.fullmatch(r"\d{3}\.\d{2}\.\d{2}-\d+", table_token))

    # Deterministic table lookup for explicit table tokens (e.g., 701.03.15-1).
    if explicit_table and mode == "answer":
        token_hits = _db_fetch_table_token_hits(table_token, scope=scope, mp_ids=mp_ids, limit=25)
        logger.debug("explicit_table_token=%s prelookup_hits=%d", table_token, len(token_hits))
        if token_hits:
            table_uid = next((h.table_uid for h in token_hits if getattr(h, "table_uid", None)), None)
            if table_uid and _table_has_enough_rows(table_uid, min_rows=2):
                meta = get_table_meta(table_uid)
                if meta:
                    page = int(meta.page_number)
                    label = _build_table_display_title(
                        table_token=table_token,
                        meta_label=meta.table_label,
                        text_candidates=[
                            meta.table_label,
                            token_hits[0].heading,
                            token_hits[0].snippet,
                            token_hits[0].text,
                        ],
                    )
                    filename = meta.filename or token_hits[0].filename
                    open_url = f"/documents/file?filename={quote(filename)}#page={page}"
                    ans = _build_table_link_answer(label)

                    _log_path("table_prelookup", scope=scope, mp_ids=mp_ids, k=k, mode=mode, conf="strong")
                    return {
                        "confidence": "strong",
                        "answer": ans,
                        "hits": [token_hits[0]],
                        "table": {
                            "table_uid": table_uid,
                            "table_label": label,
                            "page_number": page,
                            "open_url": open_url,
                            "rows": [],
                            "truncated": False,
                            "total": None,
                            "next_offset": None,
                            "filename": filename,
                            "display_name": meta.display_name,
                        },
                    }

    # ✅ 1) EXACT SECTION DB FALLBACK (deterministic)
    # If user asked for 701.03.01, fetch it directly from DB first.
    if exact:
        exact_hits = _db_fetch_exact_section(exact, scope=scope, mp_ids=mp_ids, limit=max(k, 12))
        if exact_hits:
            text_map = _hydrate_text_for_hits(exact_hits)
            for h in exact_hits:
                cid = int(getattr(h, "chunk_id", 0) or 0)
                full_text = text_map.get(cid, "")
                if full_text:
                    h.snippet = _make_query_focused_snippet(full_text, q, window=260, max_len=520)
            exact_hits = _sanitize_exact_section_hits(exact, exact_hits)
            if len(exact_hits) < 4:
                # Expand to child subsections to avoid single-excerpt section responses.
                expanded_hits = _db_fetch_exact_or_children(
                    exact,
                    scope=scope,
                    mp_ids=mp_ids,
                    limit=max(k, 40),
                )
                merged: list[_DBHit] = []
                seen = set()
                for h in exact_hits + expanded_hits:
                    if h.chunk_id in seen:
                        continue
                    merged.append(h)
                    seen.add(h.chunk_id)
                merged.sort(key=lambda h: (h.page_start, h.chunk_id))
                exact_hits = merged
            conf = "strong"
            hits = _select_section_hits(exact_hits)

            if mode == "sources_only":
                _log_path("section_exact", scope=scope, mp_ids=mp_ids, k=k, mode=mode, conf=conf)
                return {
                    "confidence": conf,
                    "answer": "Sources only: see citations on the right.",
                    "hits": hits,
                }

            if mode == "answer" and _is_bare_section_id_query(q):
                answer = f"See the citations panel for Section {exact}."
                _log_path("section_exact_bare", scope=scope, mp_ids=mp_ids, k=k, mode=mode, conf=conf)
                return {"confidence": conf, "answer": answer, "hits": hits}

            # Merge multiple excerpts for section-intent queries to avoid single-snippet UX.
            answer = _build_section_excerpt(exact, hits)
            _log_path("section_exact", scope=scope, mp_ids=mp_ids, k=k, mode=mode, conf=conf)
            return {"confidence": conf, "answer": answer, "hits": hits}

    # ✅ 2) SECTION PREFIX DB FALLBACK (deterministic set, then rerank)
    used_prefix_fallback = False
    if prefix and not exact and is_section_intent(q):
        db_hits = _db_fetch_prefix_sections(prefix, scope=scope, mp_ids=mp_ids, limit=max(300, k * 40))
        if db_hits:
            text_map = _hydrate_text_for_hits(db_hits)
            for h in db_hits:
                cid = int(getattr(h, "chunk_id", 0) or 0)
                full_text = text_map.get(cid, "")
                if full_text:
                    h.snippet = _make_query_focused_snippet(full_text, q, window=260, max_len=520)
            db_hits = _filter_mismatched_section_hits(db_hits, expected_prefix=prefix)
            hits = _bm25_rerank(q, db_hits, k=k)
            # Deterministically ensure key subsection headings are included for prefix queries
            # (e.g., 701.01, 701.02) so summaries don't miss the obvious anchors.
            must_sections = []
            m = re.search(r"\bsection\s*(\d{3})\b", q, re.I)
            if m:
                p = m.group(1)
                for sid in (f"{p}.01", f"{p}.02"):
                    must_sections.append(sid)

            if must_sections:
                extra = [h for h in db_hits if h.section_id in must_sections]
                ordered = []
                seen = set()
                for h in extra + hits:
                    if h.chunk_id in seen:
                        continue
                    ordered.append(h)
                    seen.add(h.chunk_id)
                hits = ordered[:k]
            if len(hits) < 4:
                # Pad section-intent results with broader section chunks for UX.
                target = max(k, 4)
                ordered = []
                seen = set()
                for h in hits + db_hits:
                    if h.chunk_id in seen:
                        continue
                    ordered.append(h)
                    seen.add(h.chunk_id)
                    if len(ordered) >= target:
                        break
                hits = ordered
            conf = "strong" if hits and hits[0].section_id and hits[0].section_id.startswith(prefix) else "medium"
            used_prefix_fallback = True
        else:
            hits, conf = hybrid_chunks_search(query=q, k=k, scope=scope, mp_ids=mp_ids)
    else:
        hits, conf = hybrid_chunks_search(query=q, k=k, scope=scope, mp_ids=mp_ids)

    # Hydrate full text and rebuild snippets around the query
    text_map = _hydrate_text_for_hits(hits)
    for h in hits:
        cid = int(getattr(h, "chunk_id", 0) or 0)
        full_text = text_map.get(cid, "")
        if full_text:
            h.snippet = _make_query_focused_snippet(full_text, q, window=260, max_len=520)

    # sources-only mode: no LLM call
    if mode == "sources_only":
        _log_path("sources_only", scope=scope, mp_ids=mp_ids, k=k, mode=mode, conf=conf)
        return {
            "confidence": conf,
            "answer": "Sources only: see citations on the right.",
            "hits": hits,
        }

    if mode == "answer" and _is_bare_section_id_query(q):
        section_id = q.strip()
        answer = f"See the citations panel for Section {section_id}."
        _log_path("section_lookup", scope=scope, mp_ids=mp_ids, k=k, mode=mode, conf=conf)
        return {"confidence": conf, "answer": answer, "hits": hits}

    # Location/section/page questions should not synthesize; defer to citations panel.
    if mode == "answer" and _question_asks_for_section_or_page(q) and not _is_bare_section_id_query(q):
        _log_path("section_lookup", scope=scope, mp_ids=mp_ids, k=k, mode=mode, conf=conf)
        return {
            "confidence": conf,
            "answer": "See the citations panel",
            "hits": hits,
        }

    table_intent = _looks_like_table_query(q)
    if not table_intent:
        # For non-table queries, drop table_row chunks entirely.
        hits = [h for h in hits if getattr(h, "chunk_kind", None) != "table_row"]

    # For non-table queries, prefer real content chunks over low-value rows/TOC in answer mode.
    if mode == "answer" and not table_intent and not is_section_intent(q):
        low_value_kinds = {"table_row", "toc", "front_matter"}
        preferred = [h for h in hits if getattr(h, "chunk_kind", None) not in low_value_kinds]
        low_value = [h for h in hits if getattr(h, "chunk_kind", None) in low_value_kinds]
        if preferred:
            if len(preferred) >= k:
                hits = preferred[:k] + low_value
            else:
                allowed_low_value = min(1, max(0, k - len(preferred)))
                hits = preferred + low_value[:allowed_low_value] + low_value[allowed_low_value:]

    # Section-intent queries should return deterministic merged excerpts (no LLM).
    if is_section_intent(q) and not _looks_like_table_query(q) and not _question_asks_for_section_or_page(q):
        if not hits:
            _log_path("section_intent_empty", scope=scope, mp_ids=mp_ids, k=k, mode=mode, conf="weak")
            return {
                "confidence": "weak",
                "answer": "Insufficient Evidence. I couldn’t find that section in the provided manuals.",
                "hits": [],
            }
        section_label = exact or prefix
        merged_hits = _select_section_hits(hits)
        path = "section_prefix" if used_prefix_fallback else "section_hybrid"
        _log_path(path, scope=scope, mp_ids=mp_ids, k=k, mode=mode, conf=conf)
        return {
            "confidence": conf,
            "answer": _build_section_excerpt(section_label, merged_hits),
            "hits": merged_hits,
        }

    # If a specific table id is requested, enforce targeting to that exact table.
    if table_token:
        token_text = _normalize_table_text(f"table {table_token}")
        token_only = _normalize_table_text(table_token)
        token_regex = re.compile(rf"\btable\s*{re.escape(token_only)}\b", re.I)
        matches = [
            h
            for h in hits
            if (
                token_only in _normalize_table_text(
                    (getattr(h, "heading", "") or "")
                    + " "
                    + (getattr(h, "snippet", "") or "")
                    + " "
                    + (getattr(h, "text", "") or "")
                )
                or token_regex.search(
                    _normalize_table_text(
                        (getattr(h, "heading", "") or "")
                        + " "
                        + (getattr(h, "snippet", "") or "")
                        + " "
                        + (getattr(h, "text", "") or "")
                    )
                )
            )
        ]
        logger.debug("table_token=%s matches=%d", table_token, len(matches))
        if matches:
            logger.info("Table token matched; token=%s hits=%d", table_token, len(matches))
            seen = set()
            ordered = []
            for h in matches + hits:
                cid = getattr(h, "chunk_id", None)
                key = cid if cid is not None else id(h)
                if key in seen:
                    continue
                ordered.append(h)
                seen.add(key)
            hits = ordered
            table_uid = next((h.table_uid for h in matches if getattr(h, "table_uid", None)), None)
            if table_uid and _table_has_enough_rows(table_uid, min_rows=2):
                meta = get_table_meta(table_uid)
                if meta:
                    page = int(meta.page_number)
                    label = _build_table_display_title(
                        table_token=table_token,
                        meta_label=meta.table_label,
                        text_candidates=[
                            meta.table_label,
                            matches[0].heading,
                            matches[0].snippet,
                            matches[0].text,
                        ],
                    )
                    filename = meta.filename or matches[0].filename
                    open_url = f"/documents/file?filename={quote(filename)}#page={page}"
                    ans = _build_table_link_answer(label)

                    _log_path("table_intent", scope=scope, mp_ids=mp_ids, k=k, mode=mode, conf=conf)
                    return {
                        "confidence": conf,
                        "answer": ans,
                        "hits": [matches[0]],
                        "table": {
                            "table_uid": table_uid,
                            "table_label": label,
                            "page_number": page,
                            "open_url": open_url,
                            "rows": [],
                            "truncated": False,
                            "total": None,
                            "next_offset": None,
                            "filename": filename,
                            "display_name": meta.display_name,
                        },
                    }
            snippet = (matches[0].snippet or "").strip()
            if snippet:
                if token_only not in _normalize_table_text(snippet):
                    snippet = f"Table {table_token}: {snippet}"
                ans = snippet if snippet.endswith("]") else f"{snippet} [1]"
                _log_path("table_intent", scope=scope, mp_ids=mp_ids, k=k, mode=mode, conf=conf)
                return {"confidence": conf, "answer": ans, "hits": [matches[0]]}
        return _weak_response([], q)

    # Weak retrieval: do not synthesize
    if conf == "weak" or not hits:
        # Weak retrieval should avoid irrelevant citations.
        _log_path("weak", scope=scope, mp_ids=mp_ids, k=k, mode=mode, conf="weak")
        return _weak_response(hits, q)

    # ✅ Deterministic table answering:
    # If the top hit is table-backed AND the user is asking about a table, return rows verbatim.
    if hits and getattr(hits[0], "table_uid", None) and table_intent:
        table_uid = hits[0].table_uid

        # keep min_rows=4 if you want, but this is fine too
        if _table_has_enough_rows(table_uid, min_rows=2):
            meta = get_table_meta(table_uid)
            if meta:
                page = int(meta.page_number)
                label = _build_table_display_title(
                    table_token=table_token,
                    meta_label=meta.table_label,
                    text_candidates=[
                        meta.table_label,
                        hits[0].heading,
                        hits[0].snippet,
                        hits[0].text,
                    ],
                )
                filename = meta.filename or hits[0].filename
                open_url = f"/documents/file?filename={quote(filename)}#page={page}"
                ans = _build_table_link_answer(label)

                _log_path("table_intent", scope=scope, mp_ids=mp_ids, k=k, mode=mode, conf="strong")
                return {
                    "confidence": "strong",
                    "answer": ans,
                    "hits": hits[:1],
                    "table": {
                        "table_uid": table_uid,
                        "table_label": label,
                        "page_number": page,
                        "open_url": open_url,
                        "rows": [],
                        "truncated": False,
                        "total": None,
                        "next_offset": None,
                        "filename": filename,
                        "display_name": meta.display_name,
                    },
                }

    # If we reach here, we are not in section-intent handling or table-specific logic.

    # Prefer the chunk that actually contains the requested "Table XXX.XX-N" header text
    m = re.search(r"\btable\s*(\d{3}\.\d{2}-\d+)\b", (q or "").lower())
    if m and hits:
        token = m.group(1)  # e.g. 901.03-1

        def looks_like_real_table_chunk(h) -> bool:
            s = (getattr(h, "snippet", "") or "").lower()
            if f"table {token}" not in s:
                return False
            digit_count = sum(ch.isdigit() for ch in s)
            return digit_count >= 25

        best = next((h for h in hits if looks_like_real_table_chunk(h)), None)
        if best:
            ans = best.snippet.strip()
            if not ans.endswith("]"):
                ans = f"{ans} [1]"
            return {"confidence": conf, "answer": ans, "hits": [best]}

    # Deterministic passthrough for list/table-like "Materials" chunks
    # (prevents subtle LLM inference and preserves the official listing)
    if hits and _is_materials_heading(hits[0]) and _looks_like_list_table_snippet(hits[0].snippet):
        ans = hits[0].snippet.strip()
        if not ans.endswith("]"):
            ans = f"{ans} [1]"
        return {"confidence": conf, "answer": ans, "hits": hits[:1]}

    # Deterministic passthrough for table answers (prevents hallucination)
    table_uid, table_label, table_rows = _top_table_block(hits)
    if table_rows and table_intent:
        meta = get_table_meta(table_uid) if table_uid else None
        if meta:
            page = int(meta.page_number)
            label = _build_table_display_title(
                table_token=table_token,
                meta_label=meta.table_label or table_label,
                text_candidates=[
                    meta.table_label,
                    table_label,
                    table_rows[0].heading,
                    table_rows[0].snippet,
                    table_rows[0].text,
                ],
            )
            filename = meta.filename or table_rows[0].filename
            open_url = f"/documents/file?filename={quote(filename)}#page={page}"
            ans = _build_table_link_answer(label)
            _log_path("table_intent", scope=scope, mp_ids=mp_ids, k=k, mode=mode, conf=conf)
            return {
                "confidence": conf,
                "answer": ans,
                "hits": table_rows,
                "table": {
                    "table_uid": table_uid,
                    "table_label": label,
                    "page_number": page,
                    "open_url": open_url,
                    "rows": [],
                    "truncated": False,
                    "total": None,
                    "next_offset": None,
                    "filename": filename,
                    "display_name": meta.display_name,
                },
            }

    # LLM synthesis for answer mode (non-table, non-section queries).
    low_value_kinds = {"table_row", "toc", "front_matter"}
    preferred = [h for h in hits if getattr(h, "chunk_kind", None) not in low_value_kinds]
    if not preferred:
        return _weak_response(hits, q)

    scored = [(idx, _keyword_overlap_score(q, h), h) for idx, h in enumerate(preferred)]
    scored.sort(key=lambda t: (-t[1], t[0]))
    ranked = [h for _, _, h in scored]
    if _is_prompt_payment_interest_intent(q):
        statute_ranked = sorted(ranked, key=lambda h: _statute_hit_score(h), reverse=True)
        statute_strong = [h for h in statute_ranked if _statute_hit_score(h) >= 2]
        if statute_strong:
            ranked = statute_strong + [h for h in ranked if h not in statute_strong]
    top_hits = ranked[: min(6, len(ranked))]
    if len(top_hits) < 4:
        for h in hits:
            if h in top_hits:
                continue
            top_hits.append(h)
            if len(top_hits) >= 4:
                break
    sources_text = _format_sources_compact(top_hits)
    user_prompt = f"""QUESTION:
{q}

SOURCES:
{sources_text}
"""

    _log_path("hybrid", scope=scope, mp_ids=mp_ids, k=k, mode=mode, conf=conf)
    llm = None
    try:
        llm = get_llm()
        if _is_time_limit_question(q):
            has_days = _has_payment_days_phrase(sources_text)
            logger.info("time_limit_gate match=%s", has_days)
            logger.debug("time_limit_gate sources_text=%s", sources_text)
            if not has_days:
                return {"confidence": "weak", "answer": "Insufficient Evidence.", "hits": hits}
        if _is_prompt_payment_interest_intent(q):
            statute_best = next((h for h in top_hits if _statute_hit_score(h) >= 2), None)
            if statute_best:
                statute_text = (
                    (getattr(statute_best, "text", "") or "")
                    + " "
                    + (getattr(statute_best, "snippet", "") or "")
                )
                days = _extract_prompt_payment_days(statute_text)
                if days:
                    answer = (
                        f"Interest begins to accrue if the subcontractor is not paid within {days} days after receipt of payment."
                    )
                else:
                    answer = ""
            else:
                answer = ""
        else:
            answer = ""

        if not answer:
            answer = llm.chat(
                [
                    LLMMessage(role="system", content=SYNTHESIS_PROMPT),
                    LLMMessage(role="user", content=user_prompt),
                ]
            ).strip()
        # Prevent numeric hallucination for time-based questions.
        if re.search(r"\bhow many days\b|\bwithin \d+ days\b|\bdays\b", q.lower()):
            src_blob = sources_text.lower()
            nums_in_answer = set(re.findall(r"\b\d+\b", answer))
            if nums_in_answer and not any(n in src_blob for n in nums_in_answer):
                return _llm_fallback_answer(hits)
    except LLMError as e:
        provider = getattr(llm, "provider", "unknown")
        error_code = _llm_error_code(e)
        logger.warning("LLM call failed; provider=%s error_code=%s", provider, error_code)
        # LLM provider may be unavailable/restricted; fall back to deterministic excerpt.
        return _llm_fallback_answer(hits)
    except Exception as e:
        provider = getattr(llm, "provider", "unknown")
        error_code = _llm_error_code(e)
        logger.warning("LLM call failed; provider=%s error_code=%s", provider, error_code)
        # LLM provider may be unavailable/restricted; fall back to deterministic excerpt.
        return _llm_fallback_answer(hits)

    conf = _safe_confidence(conf, answer)
    answer = _make_answer_user_friendly(answer)
    answer = _strip_answer_metadata(answer, q)
    answer = _polish_answer_text(answer)

    return {"confidence": conf, "answer": answer, "hits": hits}


def ask_question(
    query: str,
    *,
    scope: str = "all",
    mp_ids: list[str] | None = None,
    k: int = 6,
    mode: str = "answer",
) -> dict:
    try:
        return _ask_question_inner(query, scope=scope, mp_ids=mp_ids, k=k, mode=mode)
    except Exception:
        logger.exception(
            "ask_question failed; scope=%s mp_ids=%s k=%s mode=%s",
            scope,
            mp_ids or [],
            k,
            mode,
        )
        return _weak_response([], query)
