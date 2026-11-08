CREATE TABLE banks (
    id                  TEXT PRIMARY KEY,           -- slug, e.g. 'hdfc'
    name                TEXT NOT NULL UNIQUE,
    country             TEXT NOT NULL CHECK (country IN ('US', 'IN')),
    currency            TEXT NOT NULL CHECK (currency IN ('USD', 'INR')),
    default_date_format TEXT NOT NULL,              -- a key of app.statements.dates.FORMATS
    is_default          INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE accounts (
    id          INTEGER PRIMARY KEY,
    bank_id     TEXT NOT NULL REFERENCES banks (id),
    type        TEXT NOT NULL CHECK (type IN ('bank', 'credit_card')),
    name        TEXT NOT NULL,
    csv_mapping TEXT,                               -- JSON, saved after the user confirms a preview
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (bank_id, name)
);

CREATE INDEX accounts_bank ON accounts (bank_id);

INSERT INTO banks (id, name, country, currency, default_date_format, is_default) VALUES
    ('chase',       'Chase',       'US', 'USD', 'MM/DD/YYYY', 1),
    ('discover',    'Discover',    'US', 'USD', 'MM/DD/YYYY', 1),
    ('capital_one', 'Capital One', 'US', 'USD', 'YYYY-MM-DD', 1),
    ('sofi',        'SoFi',        'US', 'USD', 'YYYY-MM-DD', 1),
    ('icici',       'ICICI Bank',  'IN', 'INR', 'DD/MM/YYYY', 1),
    ('hdfc',        'HDFC Bank',   'IN', 'INR', 'DD/MM/YY',   1),
    ('sbi',         'SBI',         'IN', 'INR', 'DD Mon YYYY', 1),
    ('axis',        'Axis Bank',   'IN', 'INR', 'DD-MM-YYYY', 1);
