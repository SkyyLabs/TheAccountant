# Statement parsing, money and dates

Applies when touching `backend/app/statements/` — upload, fingerprinting, PDF unlock, parsing, reconciliation, dedupe. This is where silent correctness bugs live.

## Money

- Amounts are **integers in minor units** (cents, paise) plus an ISO currency code (`USD`, `INR`). Never `float`. Parse with `Decimal`, then convert.
- Sign convention everywhere after parsing: **negative = money out, positive = money in**. Bank statements and card statements use opposite conventions in their source columns (a card "charge" is positive in the file but money out). Normalize in the bank profile, once.
- **Never sum across currencies.** Aggregates group by currency. No FX conversion (it would need the internet).
- Indian formatting (`1,23,456.78`), `Cr`/`Dr` suffixes, parenthesized negatives and separate debit/credit columns are all parsed by the profile, not guessed downstream.

## Dates

- The date format is a property of the **bank profile** (US banks `MM/DD/YYYY`, Indian banks `DD/MM/YYYY` or `DD-Mon-YY`). Never infer it per row — `03/04` is valid both ways and a wrong guess silently swaps day and month.
- Store dates as ISO `YYYY-MM-DD`. Statement periods (start/end) are stored on the statement.

## Banks and profiles

- Default banks: **US** Chase, Discover, Capital One, SoFi · **India** ICICI, HDFC, SBI, Axis. Each has a profile: id, display name, country, currency, date format, account types (bank / credit card), and parsing rules for CSV and PDF layouts.
- Any other bank is supported through the generic path: the parser extracts candidate tables/rows, the LLM proposes a field mapping, the user confirms a preview, and the confirmed mapping is saved as a new profile. The next upload from that bank uses the saved profile with no LLM call.
- The first upload for a bank asks which bank it is and, if the PDF is encrypted, the password (see `security.md`).

## Extraction

- Deterministic first: CSV columns, PDF text and tables (`pdfplumber`/`pypdf`). The LLM is used only to map an unknown layout, never as the source of an amount or date when a parser can read it.
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
