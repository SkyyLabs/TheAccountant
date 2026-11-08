-- An uploaded file is read by the local LLM in the background; its row tracks the work.
ALTER TABLE statement_files ADD COLUMN status TEXT NOT NULL DEFAULT 'done'
    CHECK (status IN ('processing', 'done', 'failed'));
ALTER TABLE statement_files ADD COLUMN progress_done INTEGER NOT NULL DEFAULT 0;
ALTER TABLE statement_files ADD COLUMN progress_total INTEGER NOT NULL DEFAULT 0;
-- Plain-language reason when status = 'failed'; never statement contents.
ALTER TABLE statement_files ADD COLUMN error TEXT;
-- Transactions the LLM returned that could not be stored (no usable date).
ALTER TABLE statement_files ADD COLUMN rejected_count INTEGER NOT NULL DEFAULT 0;
