from __future__ import annotations

from app.services.db import get_conn
from app.services.chunk_ingestion import extract_table_blocks, is_table_line


def main() -> None:
    filename = "StandSpecRoadBridge.pdf"
    page_number = 427

    with get_conn() as conn:
        doc = conn.execute(
            "SELECT id FROM documents WHERE filename = ? LIMIT 1",
            (filename,),
        ).fetchone()

        if not doc:
            print(f"Document not found: {filename}")
            return

        doc_id = int(doc["id"])
        row = conn.execute(
            """
            SELECT text
            FROM pages
            WHERE document_id = ? AND page_number = ?
            LIMIT 1
            """,
            (doc_id, page_number),
        ).fetchone()

    if not row:
        print(f"No page text found for page {page_number}")
        return

    page_text = row["text"] or ""
    lines = page_text.splitlines()

    print(f"Document ID: {doc_id}")
    print(f"Page: {page_number}")
    print(f"Total lines: {len(lines)}")
    print("\nFirst 140 lines:")
    for idx, line in enumerate(lines[:140], start=1):
        print(f"{idx:03d}: {line}")

    print("\nTable line matches:")
    for idx, line in enumerate(lines, start=1):
        if is_table_line(line):
            print(f"{idx:03d}: {line}")

    blocks = extract_table_blocks(page_text)
    print(f"\nTable blocks found: {len(blocks)}")
    for b_idx, blk in enumerate(blocks, start=1):
        print(f"\nBlock {b_idx}: lines {blk.start_line + 1}-{blk.end_line + 1} (len={len(blk.lines)})")
        for line_no in range(blk.start_line, min(blk.start_line + 8, len(lines))):
            print(f"{line_no + 1:03d}: {lines[line_no]}")


if __name__ == "__main__":
    main()
