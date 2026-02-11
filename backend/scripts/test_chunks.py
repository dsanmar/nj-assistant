from app.services.db import get_conn

def main():
    with get_conn() as conn:
        row = conn.execute("""
            SELECT c.section_id, c.heading, c.page_start, c.page_end, LENGTH(c.text) AS n
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE d.doc_type = 'standspec'
            ORDER BY c.page_start
            LIMIT 15
        """).fetchall()

        standspec_hits = conn.execute("""
            SELECT c.section_id, c.page_start, c.page_end
            FROM chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE d.filename = 'StandSpecRoadBridge.pdf'
              AND c.section_id IN ('701.01', '701.02')
              AND c.page_start = 373
            ORDER BY c.section_id
        """).fetchall()

    for r in row:
        print(r["section_id"], r["page_start"], "-", r["page_end"], "|", (r["heading"] or "")[:80], "| chars:", r["n"])

    print("\nStandSpecRoadBridge page 373 checks:")
    if not standspec_hits:
        print("No 701.01/701.02 chunks found on page 373.")
    else:
        for r in standspec_hits:
            print("section", r["section_id"], "page", r["page_start"])

if __name__ == "__main__":
    main()
