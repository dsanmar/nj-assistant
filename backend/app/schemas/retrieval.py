from pydantic import BaseModel, Field
from typing import List, Optional, Literal

ScopeType = Literal["all", "standspec", "scheduling", "mp", "mp_only"]  # mp_only means only the selected mp_ids

class RetrievalRequest(BaseModel):
    query: str = Field(..., min_length=1)
    k: int = Field(8, ge=1, le=25)
    scope: ScopeType = "all"
    mp_ids: Optional[List[str]] = None  # e.g. ["MP10-25", "MP1-25"]

class Citation(BaseModel):
    display_name: str
    filename: str
    doc_type: str
    mp_id: Optional[str] = None
    page_number: int
    score: float
    snippet: str

class RetrievalResponse(BaseModel):
    query: str
    k: int
    scope: ScopeType
    mp_ids: Optional[List[str]] = None
    results: List[Citation]
