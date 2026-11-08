# Project State

> Read this first at the start of every session, then inspect the code, the current branch, and any open PRs.
> Update it at the end of every meaningful session. **Never put secrets or real financial data in this file** - the repo is public.
> The code is authoritative. If this file and the code disagree, fix this file.

**Last updated:** 2026-11-07
**Current milestone:** M2 - Upload and CSV import
**Next milestone:** M3 - PDF statements
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
| TypeScript pinned to 5.9.3 | `typescript-eslint` supports `<6.1`; TS 7 returns when lint tooling supports it | TypeScript 7 without type-aware lint |
| No database encryption for MVP | Local only; FileVault encrypts the disk | SQLCipher now (see Future work) |
| Branches: `dev` development, `stage` testing, `prod` release | User's workflow; no hosted deploy, so `prod` = tagged release run day to day | - |

---

## Known issues and accepted technical debt

1. `fsevents` (optional macOS file watcher pulled in by Vite) has its install script blocked by npm's default policy. It ships prebuilt and works without it; leave it blocked.
2. The repository is **public** - real statements, the DB, and exported data must never be committed. `.gitignore` covers `/data/`, `*.db`, `/statements/`, `/exports/` (anchored to the repo root so the `backend/app/statements/` module is tracked) and `fixtures/real/`; fixtures in git are synthetic only.

---

## Next tasks

- **When development is done (user request, 2026-11-08):** add a Read deny rule for real statements back to `.claude/settings.json`. It was removed because `Read(./statements/**)` also matched `backend/app/statements/` and blocked the parser code. Re-add it in a form that only covers a root-level folder and confirm `backend/app/statements/` stays readable.
- M2b: upload and CSV import (statement files, statements, transactions; mapping preview saved per account).
- M2c: upload dialog, mapping preview, statements list, basic transactions table.

1. **M2 - Upload and CSV import:** file fingerprint dedupe; bank picker on first upload (defaults: Chase, Discover, Capital One, SoFi, ICICI, HDFC, SBI, Axis, plus "Other"); per-bank currency/date format/account type; CSV import with column mapping saved per bank.
2. **M3 - PDF statements:** Keychain-backed password per bank, PDF text/table extraction, per-bank profiles for the defaults, LLM-proposed mapping for unknown layouts with user-confirmed preview, reconciliation, transaction-level dedupe.
3. **M4 - Categorization:** default US and India category sets, rules → stored result → LLM, corrections offered as rules.
4. **M5 - Transactions and Overview:** filters (date range, category, amount range, account, currency), editable categories, charts by month and category.
5. **M6 - Chat:** fixed query tools over transactions; answers cite the filters used.
6. **M7 - Scanned statements and receipt photos:** OCR (Docling) or `llama3.2-vision`.

## Future work

- Encrypt the database (SQLCipher) - deferred by user decision.
- Desktop app (Tauri or Electron wrapper around the same frontend/backend).
- Taxes (US and India), budgets, recurring-payment detection, FX conversion with user-entered rates.

---

## Open questions for the user

- None.
