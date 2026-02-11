from pydantic import BaseModel, Field
from typing import List, Optional, Literal

ScopeType = Literal["all", "standspec", "scheduling", "mp", "mp_only"]

class HybridChunksRequest(BaseModel):
    query: str = Field(..., min_length=1)
    k: int = Field(8, ge=1, le=25)
    scope: ScopeType = "all"
    mp_ids: Optional[List[str]] = None

class HybridChunkCitation(BaseModel):
    chunk_id: int
    display_name: str
    filename: str
    doc_type: str
    mp_id: Optional[str] = None

    section_id: Optional[str] = None
    heading: Optional[str] = None
    page_start: int
    page_end: int

    score: float
    snippet: str
    open_url: str
    bm25_score: Optional[float] = None
    vec_score: Optional[float] = None
    chunk_kind: Optional[str] = None
    table_uid: Optional[str] = None
    table_label: Optional[str] = None
    table_row_index: Optional[int] = None

class HybridChunksResponse(BaseModel):
    query: str
    k: int
    scope: ScopeType
    mp_ids: Optional[List[str]] = None
    confidence: Literal["strong", "medium", "weak"]
    results: List[HybridChunkCitation]
