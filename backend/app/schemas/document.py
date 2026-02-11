from pydantic import BaseModel, Field
from typing import List, Optional, Literal

ScopeType = Literal["all", "standspec", "scheduling", "mp", "mp_only"]


class DocumentSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    scope: ScopeType = "all"
    doc_type: Optional[str] = None
    mp_id: Optional[str] = None
    k: int = Field(20, ge=1, le=50)
    offset: int = Field(0, ge=0)


class DocumentSearchResult(BaseModel):
    chunk_id: int
    score: float
    snippet: str
    page_start: int
    page_end: int
    filename: str
    display_name: str
    doc_type: str
    mp_id: Optional[str] = None
    section_id: Optional[str] = None
    heading: Optional[str] = None
    chunk_kind: Optional[str] = None
    table_uid: Optional[str] = None
    table_label: Optional[str] = None
    open_url: str


class DocumentSearchResponse(BaseModel):
    query: str
    scope: ScopeType
    total: Optional[int] = None
    offset: int
    limit: int
    results: List[DocumentSearchResult]
