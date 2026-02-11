CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    display_name TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    mp_id TEXT,
    file_path TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    page_count INTEGER NOT NULL,
    ingested_at TEXT NOT NULL,
    UNIQUE(file_path)
);

CREATE TABLE IF NOT EXISTS pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    page_number INTEGER NOT NULL,
    text TEXT NOT NULL,
    char_count INTEGER NOT NULL,
    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE,
    UNIQUE(document_id, page_number)
);

CREATE INDEX IF NOT EXISTS idx_pages_document_id ON pages(document_id);
