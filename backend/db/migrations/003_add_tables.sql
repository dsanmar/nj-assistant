-- 003_add_tables.sql
-- Adds structured tables + links from chunks (table rows) to stable table_uid

CREATE TABLE IF NOT EXISTS tables (
  table_uid TEXT PRIMARY KEY,
  document_id INTEGER NOT NULL,
  filename TEXT NOT NULL,
  display_name TEXT NOT NULL,
  doc_type TEXT NOT NULL,
  mp_id TEXT,
  section_id TEXT,
  page_number INTEGER NOT NULL,
  table_index_on_page INTEGER NOT NULL,
  table_label TEXT NOT NULL,
  title TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS table_rows (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  table_uid TEXT NOT NULL,
  row_index INTEGER NOT NULL,
  row_text TEXT NOT NULL,
  FOREIGN KEY (table_uid) REFERENCES tables(table_uid)
);

CREATE INDEX IF NOT EXISTS idx_tables_doc_page ON tables(document_id, page_number);
CREATE INDEX IF NOT EXISTS idx_tables_section ON tables(section_id);
CREATE INDEX IF NOT EXISTS idx_table_rows_uid ON table_rows(table_uid);

-- Add link columns onto chunks (safe in SQLite by ALTER TABLE ADD COLUMN)
ALTER TABLE chunks ADD COLUMN table_uid TEXT;
ALTER TABLE chunks ADD COLUMN table_row_index INTEGER;
ALTER TABLE chunks ADD COLUMN table_label TEXT;
