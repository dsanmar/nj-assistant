import sqlite3
from contextlib import contextmanager
from pathlib import Path

from app.core.config import settings

def _ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

@contextmanager
def get_conn():
    _ensure_parent_dir(settings.DB_PATH)
    conn = sqlite3.connect(settings.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()