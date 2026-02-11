from pydantic import BaseModel, Field
from typing import List, Optional, Literal

ScopeType = Literal["all", "standspec", "scheduling", "mp", "mp_only"]

class HybridRetrieveRequest(BaseModel):
    query: str = Field(..., min_length=1)
    k: int = Field(8, ge=1, le=25)
    scope: ScopeType = "all"
    mp_ids: Optional[List[str]] = None

class HybridCitation(BaseModel):
    display_name: str
    filename: str
    doc_type: str
    mp_id: Optional[str] = None
    page_number: int
    score: float
    snippet: str
    bm25_score: Optional[float] = None
    vec_score: Optional[float] = None

class HybridRetrieveResponse(BaseModel):
    query: str
    k: int
    scope: ScopeType
    mp_ids: Optional[List[str]] = None
    confidence: Literal["strong", "medium", "weak"]
    results: List[HybridCitation]
