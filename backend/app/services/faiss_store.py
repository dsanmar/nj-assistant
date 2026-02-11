from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import faiss
import numpy as np

from app.core.config import settings
from app.services.db import get_conn
from app.services.embeddings import embed_texts
from app.services.rerank import toc_entry_count


@dataclass
class FaissHit:
    score: float  # cosine sim since we normalize
    document_id: int
    filename: str
    display_name: str
    doc_type: str
    mp_id: str | None
    page_number: int
    snippet: str
    toc_entries: int = 0


def build_faiss_index(index_path: Path | None = None, meta_path: Path | None = None) -> tuple[Path, Path]:
    index_path = index_path or settings.FAISS_INDEX_PATH
    meta_path = meta_path or settings.FAISS_META_PATH
    index_path.parent.mkdir(parents=True, exist_ok=True)

    with get_conn() as conn:
        rows = conn.execute("""
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
        """).fetchall()

    texts = [(r["text"] or "").strip() for r in rows]
    vecs = embed_texts(texts)  # (N, D), normalized float32

    # Inner product == cosine sim if normalized
    dim = vecs.shape[1]
    index = faiss.IndexFlatIP(dim)
    index.add(vecs)

    meta: list[dict[str, Any]] = []
    for r, txt in zip(rows, texts):
        meta.append({
            "document_id": int(r["document_id"]),
            "filename": r["filename"],
            "display_name": r["display_name"],
            "doc_type": r["doc_type"],
            "mp_id": r["mp_id"],
            "page_number": int(r["page_number"]),
            "text": txt,
        })

    faiss.write_index(index, str(index_path))
    with meta_path.open("wb") as f:
        pickle.dump(meta, f)

    return index_path, meta_path


def _load_index() -> tuple[faiss.Index, list[dict[str, Any]]]:
    index = faiss.read_index(str(settings.FAISS_INDEX_PATH))
    with settings.FAISS_META_PATH.open("rb") as f:
        meta = pickle.load(f)
    return index, meta


def faiss_search_filtered(
    query: str,
    k: int = 8,
    scope: str = "all",
    mp_ids: list[str] | None = None,
) -> list[FaissHit]:
    index, meta = _load_index()

    mp_ids_norm = [m.upper() for m in (mp_ids or [])]

    def allowed(m: dict[str, Any]) -> bool:
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

    qv = embed_texts([query])  # (1, D)
    # Pull more than k so we can filter by scope
    D, I = index.search(qv, min(len(meta), max(k * 8, 50)))

    hits: list[FaissHit] = []
    for score, idx in zip(D[0].tolist(), I[0].tolist()):
        if idx < 0:
            continue
        m = meta[idx]
        if not allowed(m):
            continue
        txt = m["text"] or ""
        snippet = (txt[:350].replace("\n", " ").strip() + ("…" if len(txt) > 350 else ""))
        toc_n = toc_entry_count(txt)

        hits.append(FaissHit(
            score=float(score),
            document_id=int(m["document_id"]),
            filename=m["filename"],
            display_name=m["display_name"],
            doc_type=m["doc_type"],
            mp_id=m["mp_id"],
            page_number=int(m["page_number"]),
            snippet=snippet,
            toc_entries=toc_n,
        ))
        if len(hits) >= k:
            break

    return hits
