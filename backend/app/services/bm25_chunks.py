from __future__ import annotations

import pickle
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from rank_bm25 import BM25Okapi

from app.core.config import settings
from app.services.db import get_conn

_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:[.\-/:][A-Za-z0-9]+)*")


def tokenize(text: str) -> list[str]:
    tokens = [m.group(0).lower() for m in _WORD_RE.finditer(text or "")]
    expanded: list[str] = []
    for t in tokens:
        expanded.append(t)
        if "-" in t or "/" in t:
            expanded.append(t.replace("-", "").replace("/", ""))
    return expanded


@dataclass
class BM25ChunkHit:
    score: float
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

    # ✅ table metadata (may be None for non-table chunks)
    table_uid: Optional[str] = None
    table_label: Optional[str] = None
    table_row_index: Optional[int] = None


class BM25ChunksIndex:
    def __init__(self, bm25: BM25Okapi, meta: list[dict[str, Any]]):
        self.bm25 = bm25
        self.meta = meta

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as f:
            pickle.dump({"bm25": self.bm25, "meta": self.meta}, f)

    @staticmethod
    def load(path: Path) -> "BM25ChunksIndex":
        with path.open("rb") as f:
            obj = pickle.load(f)
        return BM25ChunksIndex(obj["bm25"], obj["meta"])


def build_bm25_chunks_index(output_path: Path | None = None) -> Path:
    output_path = output_path or (settings.INDEX_DIR / "bm25_chunks.pkl")

    with get_conn() as conn:
        rows = conn.execute(
            """
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
                c.equation_score,
                c.table_uid,
                c.table_label,
                c.table_row_index,
                c.text
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            ORDER BY c.document_id, c.chunk_index
            """
        ).fetchall()

    corpus_tokens: list[list[str]] = []
    meta: list[dict[str, Any]] = []

    for r in rows:
        text = r["text"] or ""
        corpus_tokens.append(tokenize(text))
        meta.append(
            {
                "chunk_id": int(r["chunk_id"]),
                "document_id": int(r["document_id"]),
                "filename": r["filename"],
                "display_name": r["display_name"],
                "doc_type": r["doc_type"],
                "mp_id": r["mp_id"],
                "section_id": r["section_id"],
                "heading": r["heading"],
                "page_start": int(r["page_start"]),
                "page_end": int(r["page_end"]),
                "chunk_kind": r["chunk_kind"],
                "equation_score": float(r["equation_score"] or 0),

                # ✅ store table metadata
                "table_uid": r["table_uid"],
                "table_label": r["table_label"],
                "table_row_index": (int(r["table_row_index"]) if r["table_row_index"] is not None else None),

                "text": text,
            }
        )

    bm25 = BM25Okapi(corpus_tokens)
    idx = BM25ChunksIndex(bm25=bm25, meta=meta)
    idx.save(output_path)
    return output_path


def bm25_chunks_search_filtered(
    query: str,
    k: int = 8,
    scope: str = "all",
    mp_ids: list[str] | None = None,
    index_path: Path | None = None,
    min_equation_score: float | None = None,
) -> list[BM25ChunkHit]:
    index_path = index_path or (settings.INDEX_DIR / "bm25_chunks.pkl")
    index = BM25ChunksIndex.load(index_path)

    scores = index.bm25.get_scores(tokenize(query))
    mp_ids_norm = [m.upper() for m in (mp_ids or [])]

    def allowed(i: int) -> bool:
        m = index.meta[i]
        doc_type = (m.get("doc_type") or "").lower()
        mp_id = (m.get("mp_id") or "")
        eq_score = float(m.get("equation_score") or 0)
        if min_equation_score is not None and eq_score < min_equation_score:
            return False
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

    ranked_all = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    ranked = [i for i in ranked_all if allowed(i) and scores[i] > 0][:k]
    if not ranked:
        ranked = [i for i in ranked_all if allowed(i)][:k]

    hits: list[BM25ChunkHit] = []
    for i in ranked:
        m = index.meta[i]
        text = m["text"] or ""
        snippet = text[:350].replace("\n", " ").strip() + ("…" if len(text) > 350 else "")

        hits.append(
            BM25ChunkHit(
                score=float(scores[i]),
                chunk_id=int(m["chunk_id"]),
                document_id=int(m["document_id"]),
                filename=m["filename"],
                display_name=m["display_name"],
                doc_type=m["doc_type"],
                mp_id=m["mp_id"],
                section_id=m["section_id"],
                heading=m["heading"],
                page_start=int(m["page_start"]),
                page_end=int(m["page_end"]),
                snippet=snippet,
                chunk_kind=m.get("chunk_kind"),

                # ✅ hydrate table metadata
                table_uid=m.get("table_uid"),
                table_label=m.get("table_label"),
                table_row_index=m.get("table_row_index"),
            )
        )
    return hits
