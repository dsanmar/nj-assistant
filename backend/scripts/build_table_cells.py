from app.services.db import get_conn
from app.services.tables import (
    get_all_table_rows,
    get_table_uids,
    insert_table_cells,
    parse_table_rows_to_cells,
)


def main() -> int:
    table_uids = get_table_uids()
    total = len(table_uids)
    built = 0
    skipped = 0

    for idx, table_uid in enumerate(table_uids, start=1):
        rows = get_all_table_rows(table_uid)
        cells = parse_table_rows_to_cells(rows)
        if not cells:
            skipped += 1
            print(f"[{idx}/{total}] skip {table_uid} (no cells)")
            continue

        with get_conn() as conn:
            conn.execute("DELETE FROM table_cells WHERE table_uid = ?", (table_uid,))
            insert_table_cells(conn, cells)

        built += 1
        print(f"[{idx}/{total}] built {table_uid} ({len(cells)} cells)")

    print(f"Done. tables={total} built={built} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
