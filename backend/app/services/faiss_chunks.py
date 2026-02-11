from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import faiss
import numpy as np

from app.core.config import settings
from app.services.db import get_conn
from app.services.embeddings import embed_texts


@dataclass
class FaissChunkHit:
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
    chunk_kind: str

    # ✅ table metadata (may be None for non-table chunks)
    table_uid: Optional[str] = None
    table_label: Optional[str] = None
    table_row_index: Optional[int] = None


def build_faiss_chunks_index(
    index_path: Path | None = None,
    meta_path: Path | None = None,
) -> tuple[Path, Path]:
    index_path = index_path or (settings.INDEX_DIR / "faiss_chunks.index")
    meta_path = meta_path or (settings.INDEX_DIR / "faiss_chunks_meta.pkl")
    index_path.parent.mkdir(parents=True, exist_ok=True)

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

    texts = [(r["text"] or "").strip() for r in rows]
    vecs = embed_texts(texts)  # normalized float32

    dim = vecs.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(vecs)

    meta: list[dict[str, Any]] = []
    for r, txt in zip(rows, texts):
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

                "text": txt,
            }
        )

    faiss.write_index(index, str(index_path))
    with meta_path.open("wb") as f:
        pickle.dump(meta, f)

    return index_path, meta_path


def _load(index_path: Path, meta_path: Path) -> tuple[faiss.Index, list[dict[str, Any]]]:
    index = faiss.read_index(str(index_path))
    with meta_path.open("rb") as f:
        meta = pickle.load(f)
    return index, meta


def faiss_chunks_search_filtered(
    query: str,
    k: int = 8,
    scope: str = "all",
    mp_ids: list[str] | None = None,
    index_path: Path | None = None,
    meta_path: Path | None = None,
    min_equation_score: float | None = None,
) -> list[FaissChunkHit]:
    index_path = index_path or (settings.INDEX_DIR / "faiss_chunks.index")
    meta_path = meta_path or (settings.INDEX_DIR / "faiss_chunks_meta.pkl")

    index, meta = _load(index_path, meta_path)

    mp_ids_norm = [m.upper() for m in (mp_ids or [])]

    def allowed(m: dict[str, Any]) -> bool:
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

    qv = embed_texts([query])
    D, I = index.search(qv, min(len(meta), max(k * 8, 50)))

    hits: list[FaissChunkHit] = []
    for score, idx in zip(D[0].tolist(), I[0].tolist()):
        if idx < 0:
            continue
        m = meta[idx]
        if not allowed(m):
            continue

        txt = m["text"] or ""
        snippet = txt[:350].replace("\n", " ").strip() + ("…" if len(txt) > 350 else "")

        hits.append(
            FaissChunkHit(
                score=float(score),
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
                chunk_kind=m["chunk_kind"],

                # ✅ hydrate table metadata
                table_uid=m.get("table_uid"),
                table_label=m.get("table_label"),
                table_row_index=m.get("table_row_index"),
            )
        )
        if len(hits) >= k:
            break

    return hits
