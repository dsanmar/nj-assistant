from pathlib import Path
from app.services.db import get_conn

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "db" / "migrations"

def main():
    with get_conn() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT NOT NULL UNIQUE,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """)
        conn.commit()

        files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        for f in files:
            already = conn.execute("SELECT 1 FROM migrations WHERE filename = ?", (f.name,)).fetchone()
            if already:
                continue
            sql = f.read_text(encoding="utf-8")
            conn.executescript(sql)
            conn.execute("INSERT INTO migrations(filename) VALUES(?)", (f.name,))
            conn.commit()
            print("✅ applied", f.name)

if __name__ == "__main__":
    main()
