CREATE TABLE categories (
    id         INTEGER PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    region     TEXT NOT NULL DEFAULT 'both' CHECK (region IN ('US', 'IN', 'both')),
    is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Every decision is a new row (the LLM's result stays for audit); the latest row wins.
CREATE TABLE category_assignments (
    id             INTEGER PRIMARY KEY,
    transaction_id INTEGER NOT NULL REFERENCES transactions (id),
    category_id    INTEGER NOT NULL REFERENCES categories (id),
    source         TEXT NOT NULL CHECK (source IN ('rule', 'cache', 'llm', 'user')),
    needs_review   INTEGER NOT NULL DEFAULT 0 CHECK (needs_review IN (0, 1)),
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX category_assignments_transaction ON category_assignments (transaction_id, id);

CREATE TABLE rules (
    id               INTEGER PRIMARY KEY,
    match_type       TEXT NOT NULL CHECK (match_type IN ('exact', 'contains')),
    pattern          TEXT NOT NULL,          -- compared with the transaction's merchant key
    amount_min_minor INTEGER,                -- optional signed range, negative = money out
    amount_max_minor INTEGER,
    category_id      INTEGER NOT NULL REFERENCES categories (id),
    priority         INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Description with reference numbers and punctuation removed, so "UPI/123/SHARMA STORE" and
-- "UPI/456/SHARMA STORE" share stored results and rules. Filled by the categorizer.
ALTER TABLE transactions ADD COLUMN merchant_key TEXT;
CREATE INDEX transactions_merchant_key ON transactions (merchant_key);

ALTER TABLE statements ADD COLUMN categorization_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (categorization_status IN ('pending', 'done', 'llm_unavailable'));

INSERT INTO categories (name, region, is_default) VALUES
    ('Uncategorized', 'both', 1),
    ('Groceries', 'both', 1),
    ('Dining', 'both', 1),
    ('Transport', 'both', 1),
    ('Fuel', 'both', 1),
    ('Shopping', 'both', 1),
    ('Utilities', 'both', 1),
    ('Rent and Housing', 'both', 1),
    ('Health', 'both', 1),
    ('Entertainment', 'both', 1),
    ('Travel', 'both', 1),
    ('Subscriptions', 'both', 1),
    ('Education', 'both', 1),
    ('Insurance', 'both', 1),
    ('Personal Care', 'both', 1),
    ('Gifts and Donations', 'both', 1),
    ('Fees and Charges', 'both', 1),
    ('Cash Withdrawal', 'both', 1),
    ('Income', 'both', 1),
    ('Transfers', 'both', 1),
    ('Card Payments', 'both', 1),
    ('Investments', 'both', 1),
    ('Mobile and DTH Recharge', 'IN', 1),
    ('Domestic Help', 'IN', 1);
