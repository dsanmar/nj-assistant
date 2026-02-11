-- 002_add_chunk_kind.sql
ALTER TABLE chunks ADD COLUMN chunk_kind TEXT NOT NULL DEFAULT 'content';

CREATE INDEX IF NOT EXISTS idx_chunks_kind ON chunks(chunk_kind);
