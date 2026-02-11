-- 001_add_chunks.sql
CREATE TABLE IF NOT EXISTS chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id INTEGER NOT NULL,
  chunk_index INTEGER NOT NULL,               -- per document (0,1,2...)
  section_id TEXT,                            -- e.g., "701" or "701.01"
  heading TEXT,                               -- e.g., "SECTION 701 – GENERAL ITEMS"
  page_start INTEGER NOT NULL,
  page_end INTEGER NOT NULL,
  text TEXT NOT NULL,

  -- PRD flags (we’ll fill more later)
  is_table INTEGER NOT NULL DEFAULT 0,
  is_definition INTEGER NOT NULL DEFAULT 0,
  is_procedure INTEGER NOT NULL DEFAULT 0,

  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (document_id) REFERENCES documents(id)
);

CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_chunks_section ON chunks(section_id);
