from __future__ import annotations

import argparse

from app.services.db import get_conn
from app.services.chunk_ingestion import link_table_uids_for_document


def main() -> None:
    parser = argparse.ArgumentParser(description="Link table_uids onto chunks by table token.")
    parser.add_argument("--doc", help="Filename to target (exact match)", default=None)
    parser.add_argument("--scope", help="doc_type filter (standspec/scheduling/mp)", default=None)
    args = parser.parse_args()

    with get_conn() as conn:
        where = []
        params: list[str] = []

        if args.doc:
            where.append("filename = ?")
            params.append(args.doc)
        if args.scope:
            where.append("doc_type = ?")
            params.append(args.scope)

        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        docs = conn.execute(f"SELECT id, filename FROM documents {where_sql} ORDER BY id", params).fetchall()

        total = 0
        for d in docs:
            updated = link_table_uids_for_document(conn, int(d["id"]))
            total += updated
            if updated:
                print(f"✅ {d['filename']}: linked {updated} chunks")

        conn.commit()
        print(f"✅ total linked chunks: {total}")


if __name__ == "__main__":
    main()
