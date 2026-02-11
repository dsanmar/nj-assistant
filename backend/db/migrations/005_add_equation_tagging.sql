-- Add equation tagging metadata for chunks
ALTER TABLE chunks ADD COLUMN equation_score REAL NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_chunks_equation_score ON chunks(equation_score);
