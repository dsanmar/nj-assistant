from __future__ import annotations

import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response

from app.core.deps import require_user
from app.schemas.tables import TableCellsResponse, TableRowsResponse
from app.services.db import get_conn
from app.services.tables import get_table_cells

router = APIRouter(prefix="/tables", tags=["tables"], dependencies=[Depends(require_user)])


@router.get("/meta")
async def table_meta(table_uid: str = Query(..., min_length=5)):
    with get_conn() as conn:
        t = conn.execute(
            "SELECT * FROM tables WHERE table_uid = ?",
            (table_uid,),
        ).fetchone()
    if not t:
        raise HTTPException(status_code=404, detail="Table not found")
    return dict(t)


@router.get("/rows", response_model=TableRowsResponse)
async def table_rows(
    table_uid: str = Query(..., min_length=5),
    limit: int = Query(80, ge=1, le=80),
    offset: int = Query(0, ge=0),
    include_cells: bool = Query(False),
):
    """Offset is the count of rows already fetched; row_index is not contiguous."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT row_index, row_text
            FROM table_rows
            WHERE table_uid = ?
            ORDER BY row_index ASC
            LIMIT ? OFFSET ?
            """,
            (table_uid, limit, offset),
        ).fetchall()

        total = conn.execute(
            "SELECT COUNT(1) AS n FROM table_rows WHERE table_uid = ?",
            (table_uid,),
        ).fetchone()

    total_n = int(total["n"]) if total else 0
    next_offset = (offset + len(rows)) if (offset + len(rows) < total_n) else None

    payload = {
        "table_uid": table_uid,
        "offset": offset,
        "limit": limit,
        "total": total_n,
        "rows": [{"row_index": int(r["row_index"]), "row_text": (r["row_text"] or "")} for r in rows],
        "next_offset": next_offset,
    }

    if include_cells:
        cells = get_table_cells(table_uid)
        if cells:
            row_count = max(c.row_num for c in cells) + 1
            col_count = max(c.col_num for c in cells) + 1
            grid = [["" for _ in range(col_count)] for _ in range(row_count)]
            for c in cells:
                grid[c.row_num][c.col_num] = c.cell_text or ""
            payload["cells"] = {
                "table_uid": table_uid,
                "row_count": row_count,
                "col_count": col_count,
                "grid": grid,
            }

    return payload


@router.get("/cells", response_model=TableCellsResponse)
async def table_cells(table_uid: str = Query(..., min_length=5)):
    cells = get_table_cells(table_uid)
    if not cells:
        raise HTTPException(status_code=404, detail="Table cells not found")

    row_count = max(c.row_num for c in cells) + 1
    col_count = max(c.col_num for c in cells) + 1
    grid = [["" for _ in range(col_count)] for _ in range(row_count)]
    for c in cells:
        grid[c.row_num][c.col_num] = c.cell_text or ""

    return {
        "table_uid": table_uid,
        "row_count": row_count,
        "col_count": col_count,
        "grid": grid,
    }


@router.get("/csv")
async def table_csv(table_uid: str = Query(..., min_length=5)):
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT row_index, row_text
            FROM table_rows
            WHERE table_uid = ?
            ORDER BY row_index ASC
            """,
            (table_uid,),
        ).fetchall()

        t = conn.execute(
            "SELECT table_label, filename, page_number FROM tables WHERE table_uid = ?",
            (table_uid,),
        ).fetchone()

    if not rows or not t:
        raise HTTPException(status_code=404, detail="Table not found")

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["table_uid", table_uid])
    w.writerow(["table_label", t["table_label"]])
    w.writerow(["filename", t["filename"]])
    w.writerow(["page_number", t["page_number"]])
    w.writerow([])
    w.writerow(["row_index", "row_text"])

    for r in rows:
        w.writerow([int(r["row_index"]), r["row_text"]])

    csv_bytes = buf.getvalue().encode("utf-8")
    return Response(content=csv_bytes, media_type="text/csv")
