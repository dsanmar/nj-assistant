from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class TableRow(BaseModel):
    # row_index is the source/extraction index and is not contiguous.
    row_index: int
    row_text: str


class TableCellsResponse(BaseModel):
    table_uid: str
    row_count: int
    col_count: int
    grid: List[List[str]]


class TableRowsResponse(BaseModel):
    """Offset is the count of rows already fetched, not a row_index value."""

    table_uid: str
    offset: int = Field(..., ge=0, description="Count of rows already fetched.")
    limit: int = Field(..., ge=1, le=2000)
    total: int
    rows: List[TableRow]
    next_offset: Optional[int] = None
    cells: Optional[TableCellsResponse] = None
