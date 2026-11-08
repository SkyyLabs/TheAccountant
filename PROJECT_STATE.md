# Project State

> Read this first at the start of every session, then inspect the code, the current branch, and any open PRs.
> Update it at the end of every meaningful session. **Never put secrets or real financial data in this file** — the repo is public.
> The code is authoritative. If this file and the code disagree, fix this file.

**Last updated:** 2026-11-07
**Current milestone:** M0 — Repository and workflow
**Next milestone:** M1 — App skeleton
**Default branch:** `dev`
**Agent instructions:** synced from LLMTemplates (sky1502/LLMTemplates) `8b7ced0` on 2026-11-07

---

## What this project is

A private, offline personal-finance app for one user on one Mac. Upload bank and credit-card statements from any US or Indian bank; a local LLM categorizes transactions; a tabbed browser UI shows them with filters, charts and a chat. Everything — files, transactions, categories, LLM results — is stored in a local SQLite database. Nothing goes online.

Explicitly out of scope for now: taxes, bank-sync APIs (Plaid etc.), email parsing, budgets, multi-user, login, cloud.

---

## Completed work

### M0 — Repository and workflow
- `dev`, `stage`, `prod` created from `main` and pushed; default branch set to `dev` (verified with `gh repo view`).
- `stage` and `prod` protected: PR required (0 approvals, solo developer), force pushes and deletions blocked. Admins not enforced, so the owner can still bypass in an emergency.
- `.claude/settings.json` wires the guard hook (placed by the user; agents cannot write their own permissions file).
- Agent instructions added from LLMTemplates: `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, `.claude/` (rules, settings, destructive-command hook, `/verify`), PR template, `.gitignore`.
- Domain rules written for statements/money, LLM pipeline, SQLite, API and frontend.

---

## Architecture decisions

| Decision | Why | Rejected alternative |
|---|---|---|
| Browser app on localhost now; desktop wrapper later | Fastest to build and iterate; same code can be wrapped by Tauri/Electron | Desktop app from day one |
| FastAPI (Python 3.12) backend + Vite/React frontend, served by one process on `127.0.0.1` | Python has the best PDF/table tooling; one `make run` starts everything | Node backend; Next.js |
| SQLite single file, original uploads stored as BLOBs | User wants documents in the DB so re-uploads are minimized; statements are small | Files on disk + metadata |
| Plain `sqlite3` + numbered `.sql` migrations via `PRAGMA user_version` | One user, one file; no ORM or migration framework needed | SQLAlchemy + Alembic |
| Local Ollama, default `qwen2.5:7b` or `llama3.1:8b`, JSON-schema constrained output | Offline; fits 18 GB M3 Pro; schema output makes categories reliable | Any cloud LLM |
| Parsers extract amounts/dates; LLM only maps unknown layouts and categorizes | A hallucinated amount is the worst bug a finance app can have | LLM reads the whole statement |
| Balance reconciliation on every statement | Catches parser and LLM extraction errors mechanically | Trusting extraction |
| Chat uses fixed query tools; code does the maths | Numbers stay exact; LLM only phrases answers | Text-to-SQL; LLM arithmetic |
| Money as integer minor units + currency; per-currency totals, no FX | Exact arithmetic; FX rates would need the internet | Floats; converting to one currency |
| Date format and currency per bank profile | `DD/MM` vs `MM/DD` guessed per row silently swaps day and month | Per-row date detection |
| PDF passwords remembered per bank in the macOS Keychain (`keyring`) | User asked to remember per bank; Keychain keeps them out of the plaintext DB at no UX cost | Storing in SQLite |
| No database encryption for MVP | Local only; FileVault encrypts the disk | SQLCipher now (see Future work) |
| Branches: `dev` development, `stage` testing, `prod` release | User's workflow; no hosted deploy, so `prod` = tagged release run day to day | — |

---

## Known issues and accepted technical debt

1. Nothing is built yet beyond instructions; `make` targets and CI land in M1.
2. The repository is **public** — real statements, the DB, and exported data must never be committed. `.gitignore` covers `data/`, `*.db`, `statements/`, and `fixtures/real/`; fixtures in git are synthetic only.

---

## Next tasks

1. **M0 finish:** merge PR #1 into `dev`. Decide whether to delete the now-unused `main` branch.
2. **M1 — App skeleton:** `Makefile` (`setup`, `run`, `dev`, `test`, `verify`), FastAPI app + config + SQLite migrations, Vite app with the five tabs (Overview, Transactions, Statements, Categories & Rules, Chat), `.env.example`, CI workflow running `make verify` on `dev`/`stage`/`prod`.
3. **M2 — Upload and CSV import:** file fingerprint dedupe; bank picker on first upload (defaults: Chase, Discover, Capital One, SoFi, ICICI, HDFC, SBI, Axis, plus "Other"); per-bank currency/date format/account type; CSV import with column mapping saved per bank.
4. **M3 — PDF statements:** Keychain-backed password per bank, PDF text/table extraction, per-bank profiles for the defaults, LLM-proposed mapping for unknown layouts with user-confirmed preview, reconciliation, transaction-level dedupe.
5. **M4 — Categorization:** default US and India category sets, rules → stored result → LLM, corrections offered as rules.
6. **M5 — Transactions and Overview:** filters (date range, category, amount range, account, currency), editable categories, charts by month and category.
7. **M6 — Chat:** fixed query tools over transactions; answers cite the filters used.
8. **M7 — Scanned statements and receipt photos:** OCR (Docling) or `llama3.2-vision`.

## Future work

- Encrypt the database (SQLCipher) — deferred by user decision.
- Desktop app (Tauri or Electron wrapper around the same frontend/backend).
- Taxes (US and India), budgets, recurring-payment detection, FX conversion with user-entered rates.

---

## Open questions for the user

- None.
