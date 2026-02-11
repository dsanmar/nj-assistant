from __future__ import annotations

from typing import List, Optional, Literal
from pydantic import BaseModel, Field

ScopeType = Literal["all", "standspec", "scheduling", "mp", "mp_only"]
AskMode = Literal["answer", "sources_only"]


class AskRequest(BaseModel):
    query: str = Field(..., min_length=1)
    scope: ScopeType = "all"
    mp_ids: Optional[List[str]] = None
    k: int = Field(6, ge=1, le=12)
    mode: AskMode = "answer"


class AskCitation(BaseModel):
    chunk_id: int
    display_name: str
    filename: str
    doc_type: str
    mp_id: Optional[str] = None
    section_id: Optional[str] = None
    heading: Optional[str] = None
    page_start: int
    page_end: int
    snippet: str
    open_url: str
    chunk_kind: Optional[str] = None
    table_uid: Optional[str] = None
    table_label: Optional[str] = None
    table_row_index: Optional[int] = None


class AskTableRow(BaseModel):
    row_index: int
    row_text: str


class AskTableBlock(BaseModel):
    table_uid: str
    table_label: str
    page_number: int
    open_url: str
    rows: List[AskTableRow]
    truncated: bool = True
    total: Optional[int] = None
    next_offset: Optional[int] = None
    filename: Optional[str] = None
    display_name: Optional[str] = None


class AskResponse(BaseModel):
    query: str
    scope: ScopeType
    mp_ids: Optional[List[str]] = None
    confidence: Literal["strong", "medium", "weak"]
    answer: str
    citations: List[AskCitation]
    table: Optional[AskTableBlock] = None
