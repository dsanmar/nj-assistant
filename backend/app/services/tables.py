from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Optional, Iterable

from app.services.db import get_conn


@dataclass
class TableRow:
    table_uid: str
    row_index: int
    row_text: str


@dataclass
class TableMeta:
    table_uid: str
    document_id: int
    filename: str
    display_name: str
    doc_type: str
    mp_id: Optional[str]
    section_id: Optional[str]
    page_number: int
    table_index_on_page: int
    table_label: str


@dataclass
class TableCell:
    table_uid: str
    row_num: int
    col_num: int
    cell_text: str
    row_index_min: Optional[int]
    row_index_max: Optional[int]


def get_table_meta(table_uid: str) -> TableMeta | None:
    with get_conn() as conn:
        r = conn.execute(
            """
            SELECT
                t.table_uid,
                t.document_id,
                d.filename,
                d.display_name,
                d.doc_type,
                d.mp_id,
                t.section_id,
                t.page_number,
                t.table_index_on_page,
                t.table_label
            FROM tables t
            JOIN documents d ON d.id = t.document_id
            WHERE t.table_uid = ?
            LIMIT 1
            """,
            (table_uid,),
        ).fetchone()

    if not r:
        return None

    return TableMeta(
        table_uid=r["table_uid"],
        document_id=int(r["document_id"]),
        filename=r["filename"],
        display_name=r["display_name"],
        doc_type=r["doc_type"],
        mp_id=r["mp_id"],
        section_id=r["section_id"],
        page_number=int(r["page_number"]),
        table_index_on_page=int(r["table_index_on_page"]),
        table_label=r["table_label"] or "",
    )


def get_table_uids() -> list[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT table_uid FROM tables ORDER BY table_uid ASC",
        ).fetchall()
    return [r["table_uid"] for r in rows]


def get_table_rows(table_uid: str, limit: int = 200) -> list[TableRow]:
    limit = min(int(limit), 80)
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT table_uid, row_index, row_text
            FROM table_rows
            WHERE table_uid = ?
            ORDER BY row_index ASC
            LIMIT ?
            """,
            (table_uid, limit),
        ).fetchall()

    return [
        TableRow(
            table_uid=r["table_uid"],
            row_index=int(r["row_index"]),
            row_text=r["row_text"] or "",
        )
        for r in rows
    ]


def get_all_table_rows(table_uid: str) -> list[TableRow]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT table_uid, row_index, row_text
            FROM table_rows
            WHERE table_uid = ?
            ORDER BY row_index ASC
            """,
            (table_uid,),
        ).fetchall()

    return [
        TableRow(
            table_uid=r["table_uid"],
            row_index=int(r["row_index"]),
            row_text=r["row_text"] or "",
        )
        for r in rows
    ]


def get_table_cells(table_uid: str) -> list[TableCell]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT table_uid, row_num, col_num, cell_text, row_index_min, row_index_max
            FROM table_cells
            WHERE table_uid = ?
            ORDER BY row_num ASC, col_num ASC
            """,
            (table_uid,),
        ).fetchall()

    return [
        TableCell(
            table_uid=r["table_uid"],
            row_num=int(r["row_num"]),
            col_num=int(r["col_num"]),
            cell_text=r["cell_text"] or "",
            row_index_min=int(r["row_index_min"]) if r["row_index_min"] is not None else None,
            row_index_max=int(r["row_index_max"]) if r["row_index_max"] is not None else None,
        )
        for r in rows
    ]


_MULTISPACE_RE = re.compile(r"\s{2,}")
_DATA_ROW_START = re.compile(r"^\s*(\d+|no\.|no\b|size|nominal|\d+/\d+|[0-9]+\"|[0-9]+')", re.IGNORECASE)


def _split_cells(text: str) -> list[str]:
    if "|" in text:
        parts = [p.strip() for p in text.split("|")]
    else:
        parts = [p.strip() for p in _MULTISPACE_RE.split(text.strip())]
    return [p for p in parts if p]


def _is_data_row(text: str) -> bool:
    return bool(_DATA_ROW_START.search(text))


def parse_table_rows_to_cells(rows: Iterable[TableRow]) -> list[TableCell]:
    """
    Heuristic parser: splits row_text into cells for a usable grid.
    Returns empty list when parsing is not confident enough.
    """
    rows_list = list(rows)
    if not rows_list:
        return []

    parsed_rows: list[tuple[int, int, list[str]]] = []
    current_row_cells: list[str] = []
    current_row_index_min: Optional[int] = None
    current_row_index_max: Optional[int] = None

    for row in rows_list:
        text = (row.row_text or "").strip()
        if not text:
            continue

        cells = _split_cells(text)
        if not cells:
            continue

        starts_new = _is_data_row(text)
        if starts_new and current_row_cells:
            parsed_rows.append(
                (
                    current_row_index_min or 0,
                    current_row_index_max or current_row_index_min or 0,
                    current_row_cells,
                )
            )
            current_row_cells = []
            current_row_index_min = None
            current_row_index_max = None

        if current_row_index_min is None:
            current_row_index_min = row.row_index
        current_row_index_max = row.row_index
        current_row_cells.extend(cells)

    if current_row_cells:
        parsed_rows.append(
            (
                current_row_index_min or 0,
                current_row_index_max or current_row_index_min or 0,
                current_row_cells,
            )
        )

    if len(parsed_rows) < 2:
        return []

    col_count = max(len(cells) for _min, _max, cells in parsed_rows)
    if col_count < 2:
        return []

    table_uid = rows_list[0].table_uid

    cells_out: list[TableCell] = []
    for row_num, (row_index_min, row_index_max, cells) in enumerate(parsed_rows):
        for col_num in range(col_count):
            cell_text = cells[col_num] if col_num < len(cells) else ""
            cells_out.append(
                TableCell(
                    table_uid=table_uid,
                    row_num=row_num,
                    col_num=col_num,
                    cell_text=cell_text,
                    row_index_min=row_index_min,
                    row_index_max=row_index_max,
                )
            )

    return cells_out


def insert_table_cells(conn, cells: list[TableCell]) -> None:
    if not cells:
        return
    conn.executemany(
        """
        INSERT OR REPLACE INTO table_cells
            (table_uid, row_num, col_num, cell_text, row_index_min, row_index_max)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (
                c.table_uid,
                c.row_num,
                c.col_num,
                c.cell_text,
                c.row_index_min,
                c.row_index_max,
            )
            for c in cells
        ],
    )
