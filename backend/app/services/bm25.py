from __future__ import annotations

import pickle
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from rank_bm25 import BM25Okapi

from app.core.config import settings
from app.services.db import get_conn

# Keeps things like MP1-25, 701.01, A-709, etc.
_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:[.\-/][A-Za-z0-9]+)*")

# Section intent patterns
_SECTION_DOT_RE = re.compile(r"^\d{3}\.\d{2}$")  # 701.01
_SECTION_3_RE = re.compile(r"^\d{3}$")  # 701


def tokenize(text: str) -> list[str]:
    tokens = [m.group(0).lower() for m in _WORD_RE.finditer(text or "")]
    expanded: list[str] = []
    for t in tokens:
        expanded.append(t)
        # Normalize things like MP-1-25 -> mp125 for robustness
        if "-" in t or "/" in t:
            expanded.append(t.replace("-", "").replace("/", ""))
    return expanded


def looks_like_toc(text: str) -> bool:
    """
    Robust TOC detector for NJDOT Specs.

    Signals:
    1) Many dotted leader sequences (., ·, or spaced dots)
    2) Many lines ending in a page number (like "... 339" OR just " 339")
    3) Many section-like tokens (e.g., 701.01, 653.02) concentrated on the page
    """
    t = (text or "")
    if len(t) < 500:
        return False

    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    if len(lines) < 15:
        return False

    # --- Signal 1: dotted leaders in many lines ---
    # Catch: ".....", ". . . . .", "· · ·", etc.
    dotted_leader_lines = 0
    dotted_pattern = re.compile(r"(\.{3,}|(\.\s){6,}|(·\s){6,})")

    for ln in lines:
        if dotted_pattern.search(ln):
            dotted_leader_lines += 1

    # --- Signal 2: many lines end with a page number ---
    # TOC lines often end with a number (page)
    end_with_page_num = sum(1 for ln in lines if re.search(r"\s\d{1,4}$", ln))

    # --- Signal 3: high density of section refs like 653.02, 701.01 ---
    section_refs = len(re.findall(r"\b\d{3}\.\d{2}\b", t))

    # Decision rule (tuned to catch your page 22 style)
    if dotted_leader_lines >= 8 and end_with_page_num >= 8:
        return True

    if section_refs >= 12 and (dotted_leader_lines >= 6 or end_with_page_num >= 10):
        return True

    # fallback: very strong section+page-number pattern lines
    strong_toc_lines = 0
    for ln in lines:
        if re.search(r"\b\d{3}\.\d{2}\b.*\s\d{1,4}$", ln):
            strong_toc_lines += 1
            if strong_toc_lines >= 10:
                return True

    return False


def toc_entry_count(text: str) -> int:
    """
    Counts TOC-like entries such as:
      '701.01 Description .......... 339'
      'SECTION 701 - GENERAL ITEMS .......... 339'
    This is the most reliable signal for TOC pages.
    """
    t = text or ""
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]

    count = 0

    # 701.01 Description .... 339
    pat_sub = re.compile(r"\b\d{3}\.\d{2}\b.*?\.{2,}.*?\b\d{1,4}\b$")

    # SECTION 701 .... 339 (sometimes no dot-subsection)
    pat_sec = re.compile(r"\bSECTION\s+\d{3}\b.*?\.{2,}.*?\b\d{1,4}\b$")

    # DIVISION 700 .... 339
    pat_div = re.compile(r"\bDIVISION\s+\d{3}\b.*?\.{2,}.*?\b\d{1,4}\b$")

    for ln in lines:
        if pat_sub.search(ln) or pat_sec.search(ln) or pat_div.search(ln):
            count += 1

    return count


def section_content_bonus(query: str, text: str) -> float:
    """
    Boost real section pages when query is section intent:
    - Rewards '701.01 DESCRIPTION' followed by prose
    - Penalizes '701.01 Description .... 339' TOC line patterns
    """
    sec3, secdot = parse_section_intent(query)
    if not sec3:
        return 1.0

    t = (text or "").upper()
    bonus = 1.0

    # Real section header tends to have uppercase DESCRIPTION and then prose (not dot leaders)
    if secdot:
        # Content pattern: "701.01  DESCRIPTION" (no dot leaders right after)
        if re.search(rf"\b{re.escape(secdot)}\b\s+DESCRIPTION\b", t):
            bonus *= 3.0

        # TOC pattern: "701.01 Description .... 339" (dot leaders + page #)
        if re.search(rf"\b{re.escape(secdot)}\b.*\.{{2,}}.*\b\d{{1,4}}\b", t):
            bonus *= 0.15

    # "SECTION 701" present on both TOC and content, so only mild
    if f"SECTION {sec3}" in t:
        bonus *= 1.2

    # Prose signals (more likely content than TOC)
    if "THIS SECTION" in t or "SHALL" in t:
        bonus *= 1.2

    return bonus


def toc_penalty_multiplier(text: str) -> float:
    """
    Multiply score down if likely TOC.
    """
    if looks_like_toc(text):
        return 0.35  # Aggressive: 65% score cut
    return 1.0


def parse_section_intent(query: str) -> tuple[Optional[str], Optional[str]]:
    """
    Returns (section_3, section_dot) if query indicates section intent.

    Examples:
    - "701.01" -> ("701", "701.01")
    - "SECTION 701" -> ("701", None)
    - "701" -> ("701", None)
    """
    q = (query or "").strip().upper()

    # direct token forms
    raw = q.replace("SECTION", "").strip()
    raw = raw.replace("SEC.", "").strip()

    # If user typed exactly 701.01
    if _SECTION_DOT_RE.match(raw):
        return raw.split(".")[0], raw

    # If user typed exactly 701
    if _SECTION_3_RE.match(raw):
        return raw, None

    # Search inside query for patterns
    m_dot = re.search(r"\b(\d{3}\.\d{2})\b", q)
    if m_dot:
        secdot = m_dot.group(1)
        return secdot.split(".")[0], secdot

    m_sec = re.search(r"\bSECTION\s+(\d{3})\b", q)
    if m_sec:
        return m_sec.group(1), None

    m_3 = re.search(r"\b(\d{3})\b", q)
    if m_3:
        return m_3.group(1), None

    return None, None


def section_boost_multiplier(query: str, text: str) -> float:
    """
    For section-intent queries, strongly boost real section pages.
    """
    sec3, secdot = parse_section_intent(query)
    if not sec3:
        return 1.0

    t = (text or "").upper()

    boost = 1.0

    # Real section header
    if f"SECTION {sec3}" in t:
        boost *= 2.0

    # Direct subsection hit (701.01)
    if secdot and secdot in t:
        boost *= 2.2

    # Looks like actual section content vs TOC listing
    if secdot and f"{secdot}  DESCRIPTION" in t:
        boost *= 1.4

    return boost


@dataclass
class BM25Hit:
    # final_score is the ranking score (bm25 * penalties/boosts)
    score: float
    bm25_score: float

    document_id: int
    filename: str
    display_name: str
    doc_type: str
    mp_id: str | None
    page_number: int
    snippet: str


class BM25Index:
    """
    Stores:
    - bm25 model over page texts
    - metadata list aligned with corpus order
    """

    def __init__(self, bm25: BM25Okapi, meta: list[dict[str, Any]]):
        self.bm25 = bm25
        self.meta = meta

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            pickle.dump({"bm25": self.bm25, "meta": self.meta}, f)

    @staticmethod
    def load(path: Path) -> "BM25Index":
        with path.open("rb") as f:
            obj = pickle.load(f)
        return BM25Index(obj["bm25"], obj["meta"])


def build_bm25_index(output_path: Path | None = None) -> Path:
    """
    Builds BM25 over ALL pages in SQLite.
    """
    output_path = output_path or settings.BM25_PATH

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
                p.document_id,
                d.filename,
                d.display_name,
                d.doc_type,
                d.mp_id,
                p.page_number,
                p.text
            FROM pages p
            JOIN documents d ON d.id = p.document_id
            ORDER BY p.document_id, p.page_number
            """
        ).fetchall()

    corpus_tokens: list[list[str]] = []
    meta: list[dict[str, Any]] = []

    for r in rows:
        text = r["text"] or ""
        corpus_tokens.append(tokenize(text))
        meta.append(
            {
                "document_id": int(r["document_id"]),
                "filename": r["filename"],
                "display_name": r["display_name"],
                "doc_type": r["doc_type"],
                "mp_id": r["mp_id"],
                "page_number": int(r["page_number"]),
                "text": text,  # stored for snippets + heuristics (ok for dataset size)
            }
        )

    bm25 = BM25Okapi(corpus_tokens)
    index = BM25Index(bm25=bm25, meta=meta)
    index.save(output_path)
    return output_path


def bm25_search_filtered(
    query: str,
    k: int = 8,
    scope: str = "all",
    mp_ids: list[str] | None = None,
    index_path: Path | None = None,
) -> list[BM25Hit]:
    index_path = index_path or settings.BM25_PATH
    index = BM25Index.load(index_path)

    q_tokens = tokenize(query)
    bm25_scores = index.bm25.get_scores(q_tokens)

    mp_ids_norm = [m.upper() for m in (mp_ids or [])]

    def allowed(i: int) -> bool:
        m = index.meta[i]
        doc_type = (m.get("doc_type") or "").lower()
        mp_id = (m.get("mp_id") or "")
        if scope == "all":
            return True
        if scope == "standspec":
            return doc_type == "standspec"
        if scope == "scheduling":
            return doc_type == "scheduling"
        if scope == "mp":
            return doc_type == "mp"
        if scope == "mp_only":
            return doc_type == "mp" and mp_id.upper() in mp_ids_norm
        return True

    def final_score(i: int) -> float:
        if not allowed(i):
            return float("-inf")

        m = index.meta[i]
        text = m.get("text") or ""
        raw = float(bm25_scores[i])

        if raw <= 0:
            return 0.0

        sec3, secdot = parse_section_intent(query)
        section_intent = bool(sec3 or secdot)

        # Continuous TOC penalty: TOC pages will have many entries, content pages near 0.
        toc_n = toc_entry_count(text)

        # If query is section intent, apply much stronger penalty to TOC-y pages
        if section_intent:
            # Example: toc_n=30 => divide by (1 + 3*30)=91 (massive penalty)
            toc_penalty = 1.0 / (1.0 + 3.0 * toc_n)
        else:
            # Softer penalty for general queries
            toc_penalty = 1.0 / (1.0 + 0.5 * toc_n)

        bonus = section_content_bonus(query, text)

        return raw * toc_penalty * bonus

    # IMPORTANT: rank only within allowed set AND skip -inf
    candidates = [i for i in range(len(bm25_scores)) if allowed(i)]
    ranked_all = sorted(candidates, key=final_score, reverse=True)

    # Prefer strictly positive bm25 scores
    ranked = [i for i in ranked_all if bm25_scores[i] > 0][:k]

    # Fallback (rare)
    if not ranked:
        ranked = ranked_all[:k]

    hits: list[BM25Hit] = []
    for i in ranked:
        m = index.meta[i]
        text = m["text"] or ""
        snippet = text[:350].replace("\n", " ").strip() + ("…" if len(text) > 350 else "")

        hits.append(
            BM25Hit(
                score=float(final_score(i)),
                bm25_score=float(bm25_scores[i]),
                document_id=int(m["document_id"]),
                filename=m["filename"],
                display_name=m["display_name"],
                doc_type=m["doc_type"],
                mp_id=m["mp_id"],
                page_number=int(m["page_number"]),
                snippet=snippet,
            )
        )

    return hits


def bm25_search(
    query: str,
    k: int = 8,
    index_path: Path | None = None,
) -> list[BM25Hit]:
    """
    Backwards-compatible simple search: all documents, no scope filter.
    """
    return bm25_search_filtered(
        query=query,
        k=k,
        scope="all",
        mp_ids=None,
        index_path=index_path,
    )
