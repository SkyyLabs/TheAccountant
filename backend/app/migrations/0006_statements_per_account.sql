-- One PDF can hold several accounts (checking and savings together), so a file can now have
-- one statement per account. SQLite cannot drop a UNIQUE constraint in place: the table is
-- rebuilt and every row copied unchanged.
CREATE TABLE statements_new (
    id                              INTEGER PRIMARY KEY,
    file_id                         INTEGER NOT NULL REFERENCES statement_files (id),
    account_id                      INTEGER NOT NULL REFERENCES accounts (id),
    currency                        TEXT NOT NULL CHECK (currency IN ('USD', 'INR')),
    period_start                    TEXT,
    period_end                      TEXT,
    opening_balance_minor           INTEGER,
    closing_balance_minor           INTEGER,
    reconciliation_status           TEXT NOT NULL
        CHECK (reconciliation_status IN ('reconciled', 'unreconciled', 'unverifiable')),
    reconciliation_difference_minor INTEGER,
    row_count                       INTEGER NOT NULL,
    imported_count                  INTEGER NOT NULL,
    duplicate_count                 INTEGER NOT NULL,
    created_at                      TEXT NOT NULL DEFAULT (datetime('now')),
    categorization_status           TEXT NOT NULL DEFAULT 'pending'
        CHECK (categorization_status IN ('pending', 'done', 'llm_unavailable')),
    UNIQUE (file_id, account_id)
);

INSERT INTO statements_new SELECT
    id, file_id, account_id, currency, period_start, period_end, opening_balance_minor,
    closing_balance_minor, reconciliation_status, reconciliation_difference_minor, row_count,
    imported_count, duplicate_count, created_at, categorization_status
FROM statements;

DROP TABLE statements;
ALTER TABLE statements_new RENAME TO statements;
CREATE INDEX statements_account ON statements (account_id);
CREATE INDEX statements_file ON statements (file_id);
