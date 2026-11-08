# Database rules

Applies when touching `backend/app/db.py`, `backend/app/migrations/`, or any SQL.

- **SQLite at `DATABASE_PATH` (default `data/accountant.db`) is the only datastore.** No other store is authoritative; browser storage holds only UI preferences.
- **`db.py` is the single repository layer.** All SQL lives there. Routes, parsers and the categorizer call repository functions; they never open their own connection or write SQL.
- **Migrations:** numbered files `backend/app/migrations/NNNN_short_description.sql`, applied in order at startup, tracked with `PRAGMA user_version`. Never edit an applied migration; add a new one. No ORM, no Alembic.
- Connections enable `PRAGMA foreign_keys = ON` and `journal_mode = WAL`.
- **Money columns are `INTEGER` minor units** with a `currency TEXT` column beside them. Dates are ISO `TEXT` (`YYYY-MM-DD`). See `statements.md`.
- **Original uploads are stored as BLOBs** in `statement_files` with their SHA-256 (unique). Statements are small; this is a deliberate user decision.
- **Corrections are new rows**, never updates of the original (category overrides keep the LLM's result for audit).
- **No passwords in the database**: they live in the Keychain. See `security.md`.
- **Never modify the user's real database by hand.** Tests use a temporary database file per test. Ask before any migration that rewrites or deletes existing data.
- Index every filter the UI uses: `transactions(account_id, date)`, `transactions(category_id, date)`, `transactions(date)`, `transactions(fingerprint)` unique.

## Tables (planned in M1-M4; keep current)

- `banks`: profiles: id, name, country, currency, date format, parsing rules JSON, is_default
- `accounts`: bank_id, type (bank / credit_card), display name ("••1234", last 4 digits only, never a full number); `csv_mapping` is a legacy column, unused
- `statement_files`: one per upload (an "import"): sha256 (unique), filename, mime, bytes BLOB, uploaded_at, status (processing / done / failed), progress_done / progress_total, error, rejected_count
- `statements`: file_id, account_id (unique together: one PDF can hold several accounts), currency, period start/end, opening/closing balance, reconciliation status and difference, row/imported/duplicate counts, categorization_status (pending / done / llm_unavailable)
- `transactions`: statement_id, account_id, row_index, date, amount_minor, currency, description, normalized_description, merchant_key, raw_row JSON, source (parser / llm), needs_review, fingerprint (unique)
- `categories`: name (unique), region (US / IN / both), is_default, excluded_from_spending (Transfers and Card Payments by default, so a card payment is not counted as spending twice); `Uncategorized` cannot be renamed or deleted
- `category_assignments`: transaction_id, category_id, source (rule / cache / llm / user), needs_review, created_at - latest row wins
- `merchant_embeddings`: merchant_key, model (primary key together), vector (unit-length float32 BLOB) for chat's merchant search
- `rules`: match type, pattern, optional amount range, category_id, priority
