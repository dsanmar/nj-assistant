from typing import Optional, List

from app.schemas.retrieval import RetrievalRequest, RetrievalResponse, Citation
from app.services.ask import ask_question
from app.services.bm25 import bm25_search_filtered

def retrieve(req: RetrievalRequest) -> RetrievalResponse:
    """
    Lightweight lexical retrieval used by /chat/retrieve for quick lookup.
    """
    hits = bm25_search_filtered(
        query=req.query,
        k=req.k,
        scope=req.scope,
        mp_ids=req.mp_ids,
    )

    results = [
        Citation(
            display_name=h.display_name,
            filename=h.filename,
            doc_type=h.doc_type,
            mp_id=h.mp_id,
            page_number=h.page_number,
            score=h.score,
            snippet=h.snippet,
        )
        for h in hits
    ]

    return RetrievalResponse(
        query=req.query,
        k=req.k,
        scope=req.scope,
        mp_ids=req.mp_ids,
        results=results,
    )


def chat_retrieve(
    query: str,
    scope: str,
    mp_ids: Optional[List[str]] = None,
    k: int = 5,
    mode: str = "answer",
) -> dict:
    """
    Chat retrieval+answer path used by /chat/ask.
    """
    return ask_question(
        query=query,
        scope=scope,
        mp_ids=mp_ids,
        k=k,
        mode=mode,
    )
