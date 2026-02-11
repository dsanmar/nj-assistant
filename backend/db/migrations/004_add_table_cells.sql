-- Add structured table cells for grid rendering
CREATE TABLE IF NOT EXISTS table_cells (
    table_uid TEXT NOT NULL,
    row_num INTEGER NOT NULL,
    col_num INTEGER NOT NULL,
    cell_text TEXT NOT NULL,
    row_index_min INTEGER NULL,
    row_index_max INTEGER NULL,
    PRIMARY KEY (table_uid, row_num, col_num)
);

CREATE INDEX IF NOT EXISTS idx_table_cells_table_uid
    ON table_cells(table_uid);

CREATE INDEX IF NOT EXISTS idx_table_cells_table_uid_row_num
    ON table_cells(table_uid, row_num);
