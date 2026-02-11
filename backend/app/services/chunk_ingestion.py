from __future__ import annotations

import re
import hashlib
from dataclasses import dataclass
from typing import Optional

from app.services.db import get_conn
from app.services.chunking import chunk_document_pages

_MULTI_SPACE = re.compile(r"\S+\s{2,}\S+")
_HAS_NUMBER = re.compile(r"\d")
_TABLE_TOKEN_RE = re.compile(r"\b(?:table|tab\.)\s*(\d{3}\.\d{2}(?:\.\d{2})?-\d+)\b", re.I)
_TABLE_HEADER_RE = re.compile(r"^\s*(?:table|tab\.)\s+\d{3}\.\d{2}", re.I)
_SECTION_HEADER_RE = re.compile(r"^\s*\d{3}\.\d{2}\b")
_EQUATION_VAR_RE = re.compile(r"\b[A-Za-z]{1,4}\d{0,2}\b")
_EQUATION_FUNC_RE = re.compile(r"\b(?:log|ln|sin|cos|tan)\b", re.I)
_EQUATION_SYMBOLS = set("=≤≥≠±×÷∑√^_")
_EQUATION_OPS_RE = re.compile(r"[=<>±×÷∑√^_]")
_FRACTION_RE = re.compile(r"\b[A-Za-z0-9]+\s*/\s*[A-Za-z0-9]+\b")


def looks_like_toc_block(text: str) -> bool:
    t = text or ""
    if "TABLE OF CONTENTS" in t.upper():
        return True
    toc_line_re = re.compile(r"\b\d{3}\.\d{2}(?:\.\d{2})?\b.*?\.{2,}.*?\b\d{1,4}\b")
    if toc_line_re.search(t):
        return True
    if len(t) < 300:
        return False
    hits = len(toc_line_re.findall(t))
    return hits >= 6


def classify_chunk(section_id: str | None, text: str) -> str:
    if looks_like_toc_block(text):
        return "toc"
    if section_id is None:
        return "front_matter"
    return "content"


def equation_score(text: str) -> float:
    """
    Lightweight heuristic for equation-like content. Returns 0..1.
    """
    if not text:
        return 0.0

    best = 0.0
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if len(line) < 8 or len(line) > 200:
            continue

        score = 0.0
        symbols = sum(1 for ch in line if ch in _EQUATION_SYMBOLS)
        if symbols:
            score += 0.25
        if _EQUATION_OPS_RE.search(line):
            score += 0.2
        if len(_EQUATION_VAR_RE.findall(line)) >= 2:
            score += 0.2
        if _EQUATION_FUNC_RE.search(line):
            score += 0.1
        if _FRACTION_RE.search(line):
            score += 0.1
        digits = sum(ch.isdigit() for ch in line)
        if digits >= 4:
            score += 0.1

        non_letters = sum(not ch.isalpha() and not ch.isspace() for ch in line)
        if len(line) > 0 and (non_letters / len(line)) > 0.3:
            score += 0.1

        if score > best:
            best = score

    return min(best, 1.0)


def is_table_line(line: str) -> bool:
    line = (line or "").rstrip()
    if len(line) < 8:
        return False
    if not _HAS_NUMBER.search(line):
        return False

    # reject normal section header lines like "901.03  COARSE AGGREGATE"
    if re.match(r"^\s*\d{3}\.\d{2}(?:\.\d{2})?\b", line):
        return False

    low = line.lower()

    # strong table separators
    if "|" in line:
        return True
    if line.count("...") >= 2:
        return True
    if _MULTI_SPACE.search(line):
        return True

    nums = re.findall(r"\d+(?:\.\d+)?", line)
    ranges = re.findall(r"\b\d+\s*-\s*\d+\b", line)  # e.g., 90-100, 0-15

    # ✅ NEW: numeric/range-heavy rows (common in PDF tables with lots of spaces)
    # Examples: "100 90-100 25-60 0-15 0-5"
    if len(ranges) >= 2:
        return True
    if len(nums) >= 6:
        return True

    # existing “keyword help” (keep it, but make it a weaker fallback)
    if len(nums) >= 4 and any(k in low for k in ["percent", "percentage", "sieve", "nominal", "no.", '"']):
        return True

    return False


@dataclass
class TableBlock:
    lines: list[str]
    start_line: int
    end_line: int  # inclusive


def extract_table_blocks(page_text: str) -> list[TableBlock]:
    lines = [ln.rstrip("\n") for ln in (page_text or "").splitlines()]
    blocks: list[TableBlock] = []

    buf: list[str] = []
    buf_start: Optional[int] = None

    def flush(end_i: int) -> None:
        nonlocal buf, buf_start
        if buf_start is not None and buf:
            non_empty = [ln for ln in buf if ln.strip()]
            if len(non_empty) >= 5:
                blocks.append(TableBlock(lines=buf[:], start_line=buf_start, end_line=end_i))
        buf = []
        buf_start = None

    for i, ln in enumerate(lines):
        if _TABLE_HEADER_RE.search(ln):
            if buf_start is not None:
                flush(i - 1)
            buf_start = i
            buf.append(ln)
            continue

        if buf_start is not None:
            if _TABLE_HEADER_RE.search(ln):
                flush(i - 1)
                buf_start = i
                buf.append(ln)
                continue
            if _SECTION_HEADER_RE.search(ln):
                flush(i - 1)
                continue
            buf.append(ln)

    if buf_start is not None:
        flush(len(lines) - 1)

    return blocks


def _stable_table_uid(
    document_id: int,
    filename: str,
    page_number: int,
    table_index_on_page: int,
    lines: list[str],
) -> str:
    """
    Stable-ish table identifier:
    - derived from doc + page + index + a hash of content
    - rebuilds may reorder chunks, but table_uid remains stable if the table text is stable.
    """
    content = "\n".join(lines[:25])  # cap to avoid huge hashing
    raw = f"{document_id}|{filename}|{page_number}|{table_index_on_page}|{content}".encode("utf-8", errors="ignore")
    h = hashlib.sha1(raw).hexdigest()
    return f"tbl_{h}"


def _resolve_table_uid(conn, document_id: int, page_no: int, token: str) -> tuple[str, str] | None:
    for offset in (0, -1, 1):
        page = page_no + offset
        candidates = conn.execute(
            """
            SELECT table_uid, table_label, table_index_on_page
            FROM tables
            WHERE document_id = ? AND page_number = ?
            ORDER BY table_index_on_page ASC
            """,
            (document_id, page),
        ).fetchall()

        if not candidates:
            continue

        if len(candidates) == 1:
            return candidates[0]["table_uid"], candidates[0]["table_label"]

        table_uids = [c["table_uid"] for c in candidates]
        placeholders = ",".join("?" for _ in table_uids)
        match_rows = conn.execute(
            f"""
            SELECT DISTINCT table_uid
            FROM table_rows
            WHERE table_uid IN ({placeholders})
              AND row_text LIKE ?
            """,
            (*table_uids, f"%{token}%"),
        ).fetchall()

        if len(match_rows) == 1:
            uid = match_rows[0]["table_uid"]
            label = next((c["table_label"] for c in candidates if c["table_uid"] == uid), "")
            return uid, label

        if match_rows:
            matched = {r["table_uid"] for r in match_rows}
            for c in candidates:
                if c["table_uid"] in matched:
                    return c["table_uid"], c["table_label"]

        # Multiple tables, no row-text match: skip to avoid wrong linking
        return None

    return None


def link_table_uids_for_document(conn, document_id: int) -> int:
    rows = conn.execute(
        """
        SELECT id, page_start, text
        FROM chunks
        WHERE document_id = ?
          AND (chunk_kind IS NULL OR chunk_kind NOT IN ('toc', 'front_matter'))
          AND table_uid IS NULL
        """,
        (document_id,),
    ).fetchall()

    updated = 0
    for r in rows:
        text = r["text"] or ""
        m = _TABLE_TOKEN_RE.search(text)
        if not m:
            continue
        token = m.group(1)
        resolved = _resolve_table_uid(conn, document_id, int(r["page_start"]), token)
        if not resolved:
            continue
        table_uid, table_label = resolved
        conn.execute(
            """
            UPDATE chunks
            SET table_uid = ?, table_label = ?
            WHERE id = ?
            """,
            (table_uid, table_label, int(r["id"])),
        )
        updated += 1

    return updated


def rebuild_chunks() -> dict[str, int]:
    """
    Rebuild chunks from pages for all documents.
    Safe to run multiple times (it deletes and recreates).
    Also rebuilds structured tables (tables + table_rows).
    """
    with get_conn() as conn:
        # wipe dependent artifacts first
        conn.execute("DELETE FROM table_rows")
        conn.execute("DELETE FROM tables")
        conn.execute("DELETE FROM chunks")
        conn.commit()

        docs = conn.execute("SELECT id, filename, display_name, doc_type, mp_id FROM documents ORDER BY id").fetchall()

        total_chunks = 0
        total_tables = 0
        total_table_rows = 0

        for d in docs:
            doc_id = int(d["id"])
            filename = d["filename"]
            display_name = d["display_name"]
            doc_type = d["doc_type"]
            mp_id = d["mp_id"]

            rows = conn.execute(
                "SELECT page_number, text FROM pages WHERE document_id = ? ORDER BY page_number",
                (doc_id,),
            ).fetchall()

            pages = [(int(r["page_number"]), r["text"] or "") for r in rows]

            # --- normal content chunks ---
            chunks = chunk_document_pages(pages)
            chunks_sorted = sorted(chunks, key=lambda c: (c.page_start, c.page_end))

            # section context by page for table tagging
            section_context_by_page: dict[int, tuple[str | None, str | None]] = {}
            current_section_id = None
            current_heading = None
            chunk_idx = 0
            for page_no, _text in pages:
                while chunk_idx < len(chunks_sorted) and chunks_sorted[chunk_idx].page_start <= page_no:
                    ch = chunks_sorted[chunk_idx]
                    if ch.section_id:
                        current_section_id = ch.section_id
                        current_heading = ch.heading
                    chunk_idx += 1
                section_context_by_page[page_no] = (current_section_id, current_heading)

            chunk_index = 0

            for ch in chunks:
                eq_score = equation_score(ch.text)
                kind = "equation" if eq_score >= 0.45 else classify_chunk(ch.section_id, ch.text)
                conn.execute(
                    """
                    INSERT INTO chunks (
                        document_id, chunk_index, section_id, heading,
                        page_start, page_end, text,
                        is_table, is_definition, is_procedure,
                        chunk_kind, equation_score,
                        table_uid, table_row_index, table_label
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?, ?, NULL, NULL, NULL)
                    """,
                    (
                        doc_id,
                        chunk_index,
                        ch.section_id,
                        ch.heading,
                        ch.page_start,
                        ch.page_end,
                        ch.text,
                        kind,
                        float(eq_score),
                    ),
                )
                chunk_index += 1
                total_chunks += 1

            # --- structured tables + table-row chunks ---
            for page_no, page_text in pages:
                blocks = extract_table_blocks(page_text)
                if not blocks:
                    continue

                section_id, heading = section_context_by_page.get(page_no, (None, None))

                for t_idx, blk in enumerate(blocks, start=1):
                    table_uid = _stable_table_uid(doc_id, filename, page_no, t_idx, blk.lines)
                    table_label = f"Table (p. {page_no}) #{t_idx}"

                    # insert table metadata
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO tables (
                            table_uid, document_id, filename, display_name, doc_type, mp_id,
                            section_id, page_number, table_index_on_page, table_label, title
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                        """,
                        (
                            table_uid,
                            doc_id,
                            filename,
                            display_name,
                            doc_type,
                            mp_id,
                            section_id,
                            page_no,
                            t_idx,
                            table_label,
                        ),
                    )
                    total_tables += 1

                    # insert rows + also insert as searchable chunks
                    for r_idx, row_text in enumerate(blk.lines):
                        row_text = (row_text or "").strip()
                        if not row_text:
                            continue

                        conn.execute(
                            """
                            INSERT INTO table_rows (table_uid, row_index, row_text)
                            VALUES (?, ?, ?)
                            """,
                            (table_uid, r_idx, row_text),
                        )
                        total_table_rows += 1

                        conn.execute(
                            """
                            INSERT INTO chunks (
                                document_id, chunk_index, section_id, heading,
                                page_start, page_end, text,
                                is_table, is_definition, is_procedure,
                                chunk_kind, equation_score,
                                table_uid, table_row_index, table_label
                            )
                            VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0, 0, 'table_row', 0, ?, ?, ?)
                            """,
                            (
                                doc_id,
                                chunk_index,
                                section_id,
                                heading,
                                page_no,
                                page_no,
                                row_text,
                                table_uid,
                                r_idx,
                                table_label,
                            ),
                        )
                        chunk_index += 1
                        total_chunks += 1

            link_table_uids_for_document(conn, doc_id)

        conn.commit()

    return {
        "documents": len(docs),
        "chunks": total_chunks,
        "tables": total_tables,
        "table_rows": total_table_rows,
    }
