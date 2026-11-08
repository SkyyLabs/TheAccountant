# Project State

> Read this first at the start of every session, then inspect the code, the current branch, and any open PRs.
> Update it at the end of every meaningful session. **Never put secrets or real financial data in this file** - the repo is public.
> The code is authoritative. If this file and the code disagree, fix this file.

**Last updated:** 2026-11-07
**Current milestone:** M5 - Transactions and Overview (after the accuracy review)
**Next milestone:** M6 - Chat
**Default branch:** `dev`
**Agent instructions:** synced from LLMTemplates (sky1502/LLMTemplates) `c1ace50` on 2026-11-07

---

## What this project is

A private, offline personal-finance app for one user on one Mac. Upload bank and credit-card statements from any US or Indian bank; a local LLM categorizes transactions; a tabbed browser UI shows them with filters, charts and a chat. Everything - files, transactions, categories, LLM results - is stored in a local SQLite database. Nothing goes online.

Explicitly out of scope for now: taxes, bank-sync APIs (Plaid etc.), email parsing, budgets, multi-user, login, cloud.

---

## Completed work

### M0: Repository and workflow
- `dev`, `stage`, `prod` created from `main` and pushed; default branch set to `dev` (verified with `gh repo view`).
- `stage` and `prod` protected: PR required (0 approvals, solo developer), force pushes and deletions blocked. Admins not enforced, so the owner can still bypass in an emergency.
- `.claude/settings.json` wires the guard hook (placed by the user; agents cannot write their own permissions file).
- Agent instructions added from LLMTemplates: `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `.claude/` (rules, settings, destructive-command hook, `/verify`), PR template, `.gitignore`.
- Domain rules written for statements/money, LLM pipeline, SQLite, API and frontend.

---

### M1a - Backend skeleton
- `backend/` FastAPI app (`create_app()` factory), `config.py` (pydantic-settings, rejects a non-loopback `OLLAMA_URL` and unknown `LLM_PROVIDER` at startup), `errors.py` (one error shape), `db.py` (per-request SQLite connections, numbered `.sql` migrations via `PRAGMA user_version`, each in its own transaction), baseline migration `0001`.
- `Makefile`: `setup`, `run`, `dev`, `test`, `lint`, `verify` (backend only for now).
- Verified: `make verify` passes (ruff clean, 12 tests). Loopback test mutation-checked (removing the check fails 2 tests). `make run` serves `GET /api/health` on `127.0.0.1:8765` only and creates the gitignored `data/accountant.db`.

### M1b - Frontend shell
- `frontend/`: Vite 8, React 19, Tailwind 4, react-router 8. Five tabs (Overview, Transactions, Statements, Categories & Rules, Chat), backend status indicator, single API client `src/lib/api.ts`. Vitest + Testing Library.
- Verified: typecheck clean, 6 tests, production build; status test mutation-checked; bundle makes no external requests.

### M1c - Run, CI and lint
- `make run` builds the UI and serves it from the backend; client-side routes (`/statements` on reload) get the app shell, unknown `/api/*` keeps the JSON error, files outside `dist` are never served. 6 tests, both guards mutation-checked.
- `make setup`/`dev`/`verify` cover the frontend; ESLint (typescript-eslint, react-hooks) added; `.env.example` added.
- `.github/workflows/ci.yml` runs `make setup` + `make verify` on PRs into and pushes to `dev`/`stage`/`prod`.
- Verified: fresh `make setup` + `make verify` (ruff clean, 18 backend tests, frontend typecheck/lint/6 tests/build). `make run` checked with curl: `/`, `/statements`, `/chat` serve the shell; `/api/health` 200 JSON; `/api/nope` 404 JSON; built asset 200; listener on `127.0.0.1:8765` only. Not verified: visual check in a browser.

### M2a - Banks, accounts, money and dates
- Migration `0002`: `banks` (8 defaults seeded with country, currency, default date format) and `accounts` (bank, type bank/credit_card, name, CSV mapping slot).
- `statements/money.py`: `parse_amount(text, currency)` to integer minor units; Western and Indian grouping, `Dr`/`Cr`, parentheses, leading/trailing minus, `$`/`₹`/`Rs.`/code; rejects conflicting signs and extra decimals.
- `statements/dates.py`: `parse_date(text, date_format)` over 11 named formats, never guessed per row.
- API: `GET`/`POST /api/banks` ("Other" bank gets a slug id and its country's currency), `GET`/`POST /api/accounts`.
- Verified: `make verify` (ruff clean, 88 backend tests, frontend 6 tests and build). Mutation-checked: Dr/Cr swap, sign-conflict check, DD/MM vs MM/DD swap, unknown-bank check each fail a test.
- Not verified: the default date formats for the 8 banks are best guesses, not checked against real exports. The M2b mapping preview lets the user correct them.

### M2b - CSV upload and import
- Migration `0003`: `statement_files` (SHA-256 unique, original bytes), `statements` (period, reconciliation status, row/imported/duplicate counts), `transactions` (ISO date, signed minor units, raw row JSON, fingerprint unique).
- `statements/csv_import.py`: header-row and column suggestion from header names, `CsvMapping` (signed / inverted / debit_credit amounts, declared date format), strict row parsing (a bad row rejects the file; rows with no date or no amount are skipped and counted), fingerprints of account + date + amount + normalized description + occurrence within the statement.
- API: `POST /api/statements/preview`, `POST /api/statements` (409 `duplicate_statement`, 422 `csv_mapping_required` with rows and a suggestion, 415 for PDF, 413 over `MAX_UPLOAD_MB`), `GET /api/statements`, `GET /api/statements/{id}`. The mapping is saved per account only after an import with it succeeds. CSV statements are `unverifiable` (no balances).
- Dependency: `python-multipart` 0.0.33 (FastAPI needs it for file uploads).
- Verified: `make verify`; 8 mutation checks (occurrence index, card inversion, empty-amount skip, description normalization, SHA dedupe, mapping save, fingerprint conflict skip, PDF check) each fail a test.
- Not verified: the size limit has two layers (Content-Length middleware, read cap in the route); the test passes with either alone, so neither is checked separately. Fixture layouts are modelled on common bank exports, not checked against real ones.

### M2c - Upload UI and transactions table
- Statements tab: bank picker (defaults plus "Other bank or card" with name and country), account picker or new account (type, name with a last-4-digits hint), CSV upload. A `csv_mapping_required` reply opens the mapping form: first lines of the file with the header line highlighted, column selects, amount mode, date format, Preview, then Import (enabled only for the mapping just previewed). Duplicate files say so with the existing statement id. Statements list with status as text plus a hint.
- Transactions tab: all imported transactions newest first, amounts formatted per currency (`en-US` / `en-IN`), "Needs review" badge.
- Backend: `GET /api/transactions` (unfiltered until M5); statement and transaction rows include `bank_name`; `csv_mapping_required` details include the allowed `date_formats`.
- Verified: `make verify` (124 backend tests; frontend typecheck, lint, 16 tests, build). UI mutation checks (import without a fresh preview, INR grouping, duplicate message, status hint) each fail a test. Live smoke test on a throwaway database: mapping suggestion, import, 409 on re-upload, transactions listed, `/statements` served, listener on 127.0.0.1 only.
- Not verified: visual check in a browser (no browser tool in this session).

### M3a - PDF unlock and table extraction
- `statements/pdf.py`: reads the ruled tables of every page into rows (same shape as CSV rows), so the confirmed column mapping works for both. Header rows repeated on each page are ignored. Errors: `pdf_password_required`, `pdf_password_invalid`, `pdf_unreadable`, `pdf_no_tables`.
- `statements/passwords.py`: per-bank password in the macOS Keychain (`keyring`, service `TheAccountant`, account = bank id). Saved only after the password opened the file and `remember` is true; a wrong password never replaces the saved one; a saved password that stops working asks again. Never echoed in responses.
- UI: password prompt with "Remember for this bank (macOS Keychain)" on by default; the password lives in component state only; preview sends it but never asks to remember.
- Dependencies: `pdfplumber` 0.11.10, `keyring` 25.7.0; dev: `fpdf2` 2.9.0 builds synthetic (and encrypted) PDFs at test time, so no binary fixtures are committed. Tests use an in-memory keyring (autouse fixture), never the real Keychain.
- Verified: `make verify` (137 backend tests; frontend 20 tests, typecheck, lint, build). Mutation checks (never saves, saves before unlock, ignores remember, no saved-password fallback, no ask-again, repeated header kept, remember off by default, preview remembers) each fail a test.
- Not verified: against the real macOS Keychain (would write a real entry), or real bank PDFs. PDF statements are `unverifiable` until M3b extracts balances.

### M3b - Docling and word-position PDF reading
- `statements/pdf.py` reads PDFs with three readers in order: pdfplumber ruled tables, Docling tables (layout + TableFormer models), then word positions (lines grouped by height, words placed in the column whose header they sit under; words from the text layer, or macOS Vision OCR via `ocrmac` for scans). Lines outside the table become one-cell rows, so balance lines are kept for reconciliation. Encrypted PDFs are decrypted in memory with pypdfium2 before any reader.
- Without the models, digital text-only PDFs still work through word positions; `pdf_ocr_unavailable` is returned only when nothing found a table and Docling was missing.
- `make models` downloads the layout and table models (669 MB) once into gitignored `models/docling`; runtime is offline (`HF_HUB_OFFLINE=1`, telemetry off, explicit `artifacts_path`). `make setup` installs the `ocr` extra (`docling[ocrmac]` 2.148.0, pulls torch); CI installs `dev` only.
- Verified: `make verify` (default suite, no models); `make test-models` 5 Docling tests on synthetic text-only, encrypted and scanned statements, including full imports whose totals equal closing minus opening. Mutation checks (single column, no fallback past missing Docling, Vision y not flipped, column bounds at header starts) each fail a test.
- Found while probing: Docling's layout model sees no table in sparse synthetic layouts and flattens scans column by column, losing which amount is a debit; the word-position reader covers those. Docling's first run in a process takes about 5-15 s to load models; the converter is cached per process.
- Not verified: real bank PDFs; wrapped multi-line descriptions (continuation lines have no date, so they are skipped and counted, and the description is truncated).

### M3c - LLM layout proposal and reconciliation
- `llm/`: provider interface (`base.py`), Ollama provider (stdlib HTTP, JSON-schema `format`, temperature 0, errors normalized to `LlmUnavailable` / `LlmError`, timings logged, never prompts), scripted `MockProvider` for tests, `get_llm_provider()` from `LLM_PROVIDER`.
- `statements/layout.py`: on the first upload per account the local model names the header line, columns, amount mode and balance labels. Code settles what it can check against the file: header line (row holding the named columns), date format (bank default, then same day/month order, first that parses every row), card sign (most transactions money out), labels (kept only if a balance can be read after them, else known labels such as "Beginning/Ending Balance"). Invalid twice or Ollama down: header heuristics. `csv_mapping_required` details carry `suggestion_source`.
- `statements/reconciliation.py`: balances read by `parse_amount` after the confirmed labels (opening = first, closing = last, so per-page carried-forward lines work). Bank: opening + transactions = closing; card: previous - transactions = new. Stored on the statement with the difference; shown in the preview before import and in the list.
- Mapping gains `opening_balance_label` / `closing_balance_label`, saved per account with the columns.
- Model: `qwen2.5:7b` pulled (4.7 GB).
- Verified: `make verify` (default suite), `make test-models`. Real `qwen2.5:7b` on 5 synthetic layouts (HDFC with and without balances, Chase card, Discover card, a credit union with "Money Out/Money In" and "Beginning/Ending Balance"): all proposals accepted, 3-5 s each. End to end with real Docling + qwen: a text-only PDF statement proposed, previewed and **reconciled** to the paisa. Mutation checks (card sign, bank day/month order, header correction, label fallback, retry on unavailable, card formula, closing = last match, upload ignoring reconciliation) each fail a test.
- Found while testing the real model: alone it proposed `DD/MM/YYYY` for Chase dates, was off by one on header lines and usually returned no balance labels. Validation rejected those answers, which is why code now settles those fields.
- Known gaps: a card file with as many credits as charges keeps the proposed sign (the majority rule cannot decide); Indian card statements with a `Cr` closing balance (credit balance) would read as owed; layout proposal runs inside the upload request (a few seconds to tens of seconds on first upload).

### M4a - Categorization backend
- Migration `0004`: `categories` (24 defaults: 22 for both regions, `Mobile and DTH Recharge` and `Domestic Help` for India), `category_assignments` (new row per decision, latest wins), `rules`, `transactions.merchant_key`, `statements.categorization_status`.
- `categorize/categorizer.py`: rules, then stored result per merchant key, then the LLM in batches constrained to the region's categories; low confidence or invalid output becomes `Uncategorized` + needs review; Ollama down leaves transactions pending. Runs in a background task after upload; `POST /api/transactions/categorize` retries.
- API: categories (list, create, rename, delete; `Uncategorized` protected; in-use categories cannot be deleted), rules (list by priority, create with retroactive apply that never overrides the user's own choices, update, delete), `PATCH /api/transactions/{id}` (user correction, returns a suggested exact rule). Transactions carry category, source and review flag.
- Verified: `make verify` (default suite). Mutation checks (rules skipped, stored results skipped, confidence ignored, category list not enforced, region ignored, unavailable reported as done, amount minimum ignored, rules override user, earliest assignment wins, correction not marked user) each fail a test; "stored results skipped" survived at first and the test was rewritten. Real `qwen2.5:7b` on 14 synthetic US and Indian transactions: 12 sensible, 2 flagged for review (gibberish merchant, card payment), 16 s.
- Not done: no read of the assignment history (audit rows are stored but not exposed yet).

### M4b - Categories UI
- Transactions tab: category column (labelled select per row), "Check category" badge for low-confidence results, "Always categorize X as Y?" offer after a correction (creates the rule only on accept, reports how many other transactions moved), "Categorize now" retry when some are pending, light refresh every 3 s (up to 20 times) while categorization runs.
- Categories & Rules tab: rules (match, merchant text, category, priority; delete), categories (add with region, rename, delete with the server's reason shown; `Uncategorized` has no actions). Rule amount ranges are supported by the API but not exposed in the UI yet (it would need parsing typed money in the frontend).
- Verified: `make verify` (196 backend, 33 frontend tests, build). UI mutation checks (no rule offer, no check badge, Uncategorized editable) each fail a test. Live smoke on uvicorn with real Ollama and a throwaway database: upload returned `pending`, background categorization finished in about 6 s, `/categories` served.
- Not verified: visual check in a browser.

### M5a - Transaction filters and totals
- `db.TransactionFilters` and one WHERE builder shared by `GET /api/transactions` and the new `GET /api/summary` (totals, by month, by category; every row per currency; money in and out as positive totals; uncategorized grouped as `category_id: null`). Amount filters compare the size of the amount, typed text parsed by `parse_amount`; text search escapes `%` and `_`. Accounts list now carries `bank_name`.
- Transactions tab: filter bar (dates, description, currency, amount range, categories and accounts as checkbox groups, Clear filters) kept in the URL with the backend's parameter names; per-currency totals of the filtered set.
- Verified: `make verify` (211 backend, 36 frontend tests, build). Mutation checks (signed amount filter, exclusive end date, no LIKE escaping, totals not grouped by currency, summary ignoring filters, typed sign kept, only first category in the URL, totals ignoring filters) each fail a test; "typed sign kept" survived at first and a negative-amount test was added.
- Not done: the list has no paging (fine at personal scale); text inputs fetch on every keystroke.

---

## Architecture decisions

| Decision | Why | Rejected alternative |
|---|---|---|
| Browser app on localhost now; desktop wrapper later | Fastest to build and iterate; same code can be wrapped by Tauri/Electron | Desktop app from day one |
| FastAPI (Python 3.12) backend + Vite/React frontend, served by one process on `127.0.0.1` | Python has the best PDF/table tooling; one `make run` starts everything | Node backend; Next.js |
| SQLite single file (not Postgres: one user, offline, no server to run, one-file backup, bundles into a desktop app), original uploads stored as BLOBs | User wants documents in the DB so re-uploads are minimized; statements are small | Files on disk + metadata |
| Plain `sqlite3` + numbered `.sql` migrations via `PRAGMA user_version` | One user, one file; no ORM or migration framework needed | SQLAlchemy + Alembic |
| Local Ollama, default `qwen2.5:7b` or `llama3.1:8b`, JSON-schema constrained output | Offline; fits 18 GB M3 Pro; schema output makes categories reliable | Any cloud LLM |
| Parsers extract amounts/dates; LLM only maps unknown layouts and categorizes | A hallucinated amount is the worst bug a finance app can have | LLM reads the whole statement |
| Balance reconciliation on every statement | Catches parser and LLM extraction errors mechanically | Trusting extraction |
| Chat uses fixed query tools; code does the maths | Numbers stay exact; LLM only phrases answers | Text-to-SQL; LLM arithmetic |
| Money as integer minor units + currency; per-currency totals, no FX | Exact arithmetic; FX rates would need the internet | Floats; converting to one currency |
| Date format and currency per bank profile | `DD/MM` vs `MM/DD` guessed per row silently swaps day and month | Per-row date detection |
| PDF passwords remembered per bank in the macOS Keychain (`keyring`) | User asked to remember per bank; Keychain keeps them out of the plaintext DB at no UX cost | Storing in SQLite |
| No shadcn/ui yet; plain semantic tables and inline forms | M2c needed no dialog, popover or combobox; avoids Radix, clsx and tailwind-merge until a screen does | Adding shadcn with the first table |
| TypeScript pinned to 5.9.3 | `typescript-eslint` supports `<6.1`; TS 7 returns when lint tooling supports it | TypeScript 7 without type-aware lint |
| No database encryption for MVP | Local only; FileVault encrypts the disk | SQLCipher now (see Future work) |
| Branches: `dev` development, `stage` testing, `prod` release | User's workflow; no hosted deploy, so `prod` = tagged release run day to day | - |

---

## Known issues and accepted technical debt

1. `fsevents` (optional macOS file watcher pulled in by Vite) has its install script blocked by npm's default policy. It ships prebuilt and works without it; leave it blocked.
2. The repository is **public** - real statements, the DB, and exported data must never be committed. `.gitignore` covers `/data/`, `*.db`, `/statements/`, `/exports/` (anchored to the repo root so the `backend/app/statements/` module is tracked) and `fixtures/real/`; fixtures in git are synthetic only.

---

## Next tasks

- **Accuracy review of financial readings (user request, 2026-11-08, after M4):** measure how accurate extraction, layout proposals and reconciliation are, and decide how to handle the gaps listed under M3b and M3c (wrapped descriptions, card sign ties, `Cr` card balances, layout proposal latency). Synthetic test layouts only so far; real-statement checks need the user.
- **When development is done (user request, 2026-11-08):** add a Read deny rule for real statements back to `.claude/settings.json`. It was removed because `Read(./statements/**)` also matched `backend/app/statements/` and blocked the parser code. Re-add it in a form that only covers a root-level folder and confirm `backend/app/statements/` stays readable.

1. **M5 - Transactions and Overview:** filters (date range, category, amount range, account, currency), editable categories, charts by month and category.
2. **M6 - Chat:** fixed query tools over transactions; answers cite the filters used.
3. **M7 - Receipt photos:** `llama3.2-vision` (scanned statements are already handled by Docling + Vision OCR in M3b).

## Future work

- Encrypt the database (SQLCipher) - deferred by user decision.
- Desktop app (Tauri or Electron wrapper around the same frontend/backend).
- Taxes (US and India), budgets, recurring-payment detection, FX conversion with user-entered rates.

---

## Open questions for the user

- None.
