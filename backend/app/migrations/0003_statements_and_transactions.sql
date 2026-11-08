CREATE TABLE statement_files (
    id          INTEGER PRIMARY KEY,
    sha256      TEXT NOT NULL UNIQUE,
    filename    TEXT NOT NULL,
    mime        TEXT NOT NULL,
    bytes       BLOB NOT NULL,
    uploaded_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE statements (
    id                              INTEGER PRIMARY KEY,
    file_id                         INTEGER NOT NULL UNIQUE REFERENCES statement_files (id),
    account_id                      INTEGER NOT NULL REFERENCES accounts (id),
    currency                        TEXT NOT NULL CHECK (currency IN ('USD', 'INR')),
    period_start                    TEXT,
    period_end                      TEXT,
    opening_balance_minor           INTEGER,
    closing_balance_minor           INTEGER,
    reconciliation_status           TEXT NOT NULL
        CHECK (reconciliation_status IN ('reconciled', 'unreconciled', 'unverifiable')),
    reconciliation_difference_minor INTEGER,
    row_count                       INTEGER NOT NULL,  -- transactions parsed from the file
    imported_count                  INTEGER NOT NULL,  -- new transactions stored
    duplicate_count                 INTEGER NOT NULL,  -- already stored from another statement
    created_at                      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX statements_account ON statements (account_id);

CREATE TABLE transactions (
    id                     INTEGER PRIMARY KEY,
    statement_id           INTEGER NOT NULL REFERENCES statements (id),
    account_id             INTEGER NOT NULL REFERENCES accounts (id),
    row_index              INTEGER NOT NULL,           -- position within the statement
    date                   TEXT NOT NULL,              -- ISO YYYY-MM-DD
    amount_minor           INTEGER NOT NULL,           -- negative = money out
    currency               TEXT NOT NULL CHECK (currency IN ('USD', 'INR')),
    description            TEXT NOT NULL,
    normalized_description TEXT NOT NULL,
    raw_row                TEXT NOT NULL,              -- JSON of the source cells
    source                 TEXT NOT NULL DEFAULT 'parser' CHECK (source IN ('parser', 'llm')),
    needs_review           INTEGER NOT NULL DEFAULT 0 CHECK (needs_review IN (0, 1)),
    fingerprint            TEXT NOT NULL UNIQUE,
    created_at             TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX transactions_account_date ON transactions (account_id, date);
CREATE INDEX transactions_date ON transactions (date);
CREATE INDEX transactions_statement ON transactions (statement_id);
