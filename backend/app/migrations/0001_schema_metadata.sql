-- Baseline. Domain tables (banks, accounts, statements, transactions, categories, rules)
-- arrive with the milestones that use them, starting in M2.
CREATE TABLE app_metadata (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT INTO app_metadata (key, value) VALUES ('created_at', datetime('now'));
