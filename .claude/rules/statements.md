# Statement parsing, money and dates

Applies when touching `backend/app/statements/` - upload, fingerprinting, PDF unlock, parsing, reconciliation, dedupe. This is where silent correctness bugs live.

## Money

- Amounts are **integers in minor units** (cents, paise) plus an ISO currency code (`USD`, `INR`). Never `float`. Parse with `Decimal`, then convert.
- Sign convention everywhere after parsing: **negative = money out, positive = money in**. Bank statements and card statements use opposite conventions in their source columns (a card "charge" is positive in the file but money out). Normalize in the bank profile, once.
- **Never sum across currencies.** Aggregates group by currency. No FX conversion (it would need the internet).
- Indian formatting (`1,23,456.78`), `Cr`/`Dr` suffixes, parenthesized negatives and separate debit/credit columns are all parsed by the profile, not guessed downstream.

## Dates

- The date format is a property of the **bank profile** (US banks `MM/DD/YYYY`, Indian banks `DD/MM/YYYY` or `DD-Mon-YY`). Never infer it per row - `03/04` is valid both ways and a wrong guess silently swaps day and month.
- On the first upload for an account, `statements/layout.py` proposes one format for the **whole file**: the bank's default first, then formats with the same day/month order, keeping the first that parses every row. The user confirms it in the preview and it is saved on the account; later uploads use the saved format only.
- Store dates as ISO `YYYY-MM-DD`. Statement periods (start/end) are stored on the statement.

## Banks and profiles

- Default banks: **US** Chase, Discover, Capital One, SoFi · **India** ICICI, HDFC, SBI, Axis. Each has a profile: id, display name, country, currency, date format, account types (bank / credit card), and parsing rules for CSV and PDF layouts.
- Any other bank is supported through the generic path: the parser extracts candidate tables/rows, the LLM proposes a field mapping, the user confirms a preview, and the confirmed mapping is saved as a new profile. The next upload from that bank uses the saved profile with no LLM call.
- No bank or account is asked for: `statements/understand.py` reads them from the file (bank name and last 4 digits must appear in it) and `importer.py` creates or reuses the bank and account. Only an encrypted PDF can need input: its password (see `security.md`).
- One PDF can hold several accounts (checking and savings together): one statement per account, `UNIQUE (file_id, account_id)`.

## Extraction

- Deterministic first: PDF transaction lines (`lines.py`), CSV columns, PDF tables (pdfplumber, Docling, word positions). The LLM names columns, balance labels and the bank; it is never the source of an amount or date.
- Dates without a year (`12/08`) take the year from the statement period printed on the statement; if there is none, the line reader refuses rather than guessing.
- With a running balance, the sign of each amount comes from the balance change and each row is checked against it; a row that does not fit is marked `needs_review` and the statement `unreconciled`.
- Any value that came from the LLM is stored with `source = 'llm'` and `needs_review = 1` until the user confirms it.
- Keep the raw extracted row alongside the normalized transaction so re-parsing after a parser fix needs no re-upload.

## Reconciliation (every statement)

- Bank: `opening_balance + sum(transactions) == closing_balance`.
- Card: `previous_balance + charges − payments − credits == new_balance` (in the normalized sign convention).
- A mismatch marks the statement `unreconciled` with the difference shown in the UI. Never silently accept or "fix" a mismatch.
- If a statement has no balances, mark it `unverifiable`, not reconciled.

## Duplicates

- **File level:** SHA-256 of the uploaded bytes. A known hash is reported as already imported and not reprocessed.
- **Transaction level:** fingerprint of (account, date, amount, normalized description). Overlapping statements (monthly + quarterly) do not double count. Genuine same-day identical transactions are kept when they come from the **same** statement (use the row index within the statement as a tiebreaker).

## Tests

Every bank profile has a synthetic fixture statement and a test that parses it and reconciles. See `testing.md` for the mutation-check rule.
