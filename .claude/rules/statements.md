# Statements: reading, money and checks

Applies when touching `backend/app/statements/` - import flow, text extraction, LLM reading and its checks, money, reconciliation, dedupe. This is where silent correctness bugs live.

## Reading: the LLM extracts, code verifies (user decision, 2026-11-08)

- No per-bank, per-layout or per-format code. Any bank or card works the same way: file -> text (`pdf.py`) -> LLM extraction (`extract.py`) -> checks -> storage (`importer.py`).
- `pdf.py` keeps the text layer's column gaps (` | `) so the model can tell debit from credit columns; scans go through Docling with macOS Vision OCR (local models only, see `security.md`).
- `extract.py` asks for the accounts and period first, then the transactions chunk by chunk (`CHUNK_CHARS`). Amounts come back as printed text and are parsed by `parse_amount`; direction (`in` / `out`) sets the sign.
- Checks, all against the source text, never the model's word:
  - an amount must be a money value that appears in the chunk it came from;
  - a date must be a real ISO date within the statement period (31 days slack) when a period is known;
  - a bank name and last 4 digits must appear in the statement, otherwise they are dropped ("Unknown bank", "Account");
  - an opening or closing balance must appear in the statement, otherwise it is ignored.
  - a running balance printed on a row must equal the previous printed balance (or the opening balance) plus the rows since (a card's balance owed goes up with a charge); the rows that break it are flagged, which catches a flipped sign or a row put on the wrong account. A running balance not printed in the text is ignored.
- A transaction failing a check is stored with `needs_review = 1`. One without a usable date or amount cannot be stored and is counted in the import's `rejected_count`.

## Money

- Amounts are **integers in minor units** (cents, paise) plus an ISO currency code (`USD`, `INR`). Never `float`. Parse with `parse_amount` (Decimal), never by hand.
- Sign convention everywhere after reading: **negative = money out, positive = money in**.
- **Never sum across currencies.** Aggregates group by currency. No FX conversion.

## Reconciliation (every statement, per account)

- Bank: `opening + sum(transactions) == closing`. Card: `previous - sum(transactions) == new` (charges are money out and raise what is owed).
- A mismatch marks the statement `unreconciled` with the difference. Never silently accept or "fix" a mismatch.
- No balances (or balances not found in the text): `unverifiable`.

## Duplicates

- **File level:** SHA-256 of the uploaded bytes; a known file returns 409 with its import id. A failed import can be uploaded again.
- **Transaction level:** fingerprint of (account, date, amount, normalized description, occurrence within the statement), so overlapping statements do not double count and genuine identical rows in one statement are kept.
- One PDF can hold several accounts: one statement per account, `UNIQUE (file_id, account_id)`.

## Tests

Synthetic statements only (`tests/fixtures/`, `conftest.py`). Integration tests script the mock LLM's answers (`upload` fixture) and assert what the checks do with them: made-up amounts, dates, banks and balances must be flagged or dropped. Real-model checks run outside the suite (tests never call Ollama).
