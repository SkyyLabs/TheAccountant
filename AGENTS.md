# TheAccountant

A private, offline personal-finance app that runs only on the owner's Mac. The user uploads statements from any bank or card (PDF, scan or CSV, US or India; several at once) and nothing else: a **local** LLM (Ollama) reads them, code verifies what it read against the statement text, the LLM sorts transactions into categories, and a dashboard shows charts, filters and the categorized transactions (a chat for questions like "how much did I spend on food in March?" comes later). Statements and all results are stored in a local SQLite database so re-uploads are detected and skipped. **Nothing leaves the machine** - no cloud, no login, no telemetry, no network calls except to the local Ollama server.

Out of scope for now: taxes, bank-sync APIs, email parsing, receipt photos (user decision, 2026-11-08), budgets, multi-user, cloud anything. Future work is listed in `PROJECT_STATE.md`.

## Start and end of every session

1. **Start:** read [PROJECT_STATE.md](PROJECT_STATE.md), then `.memory/CONTEXT.md` if it exists, then check the current branch, `git status` and open PRs. The code is authoritative: if a doc and the code disagree, the code wins and the doc is stale - fix the doc.
2. **End of any meaningful session:** update `PROJECT_STATE.md` (completed work, decisions, known issues, next tasks). Put machine-specific notes and in-flight experiments in `.memory/CONTEXT.md`. Never put secrets or real financial data in either.

## How to work here

Bias toward caution over speed. For trivial tasks, use judgment.

- **Think before coding.** State assumptions. When a request has several readings, name them instead of picking one silently. The invariants below are easy to break without noticing - confirm rather than guess.
- **Do not ask what you can decide.** Recommend, give the reasoning, proceed. Ask only when the answer is genuinely the user's: spend, credentials, external services, irreversible actions, product direction.
- **Goal-driven execution.** Turn each task into a check you can run ("parse HDFC PDFs" → a sample statement parses and its balance reconciles, and a test shows it). State a short plan for multi-step work; verify each step with real output.
- **Minimum code that solves the problem.** No speculative features, layers or abstractions. Every changed line should trace to the request. Full rules: [.claude/rules/coding-practices.md](.claude/rules/coding-practices.md) - read before writing code.
- **Report faithfully.** Say what was verified and how, and what was not. A review finding you merged past becomes an issue, never silence.

## Commands


```bash
make setup     # venv on Python 3.12 + backend deps (with Docling OCR on macOS) + frontend deps
make models    # one-time download of the Docling layout/table models into models/ (the only internet use)
make run       # build the UI and serve app + API on http://127.0.0.1:8765
make dev       # backend with reload on :8765 + Vite dev server on :5173 (proxies /api)
make build     # build the UI into frontend/dist
make test      # backend pytest (no Docling models needed)
make test-models # backend tests that run Docling; needs make models
make verify    # full check sequence - run before claiming any task done
```

`make verify` is the single source of truth for the check sequence and is what CI runs. Do not restate its steps anywhere else.

Backend is pinned to **Python 3.12** (`/opt/homebrew/bin/python3.12`). Ollama must be running locally (`ollama serve`; check with `curl -s localhost:11434/api/version`).

## Architecture (skeleton built in M1; modules below `db.py` arrive in M2+)

```text
backend/                 FastAPI app, Python 3.12, bound to 127.0.0.1 only
  app/main.py            app factory; serves the built frontend and /api/*
  app/config.py          env-driven settings (.env), fails fast on bad config
  app/db.py              the single SQLite repository layer
  app/migrations/        numbered .sql files, applied at startup via PRAGMA user_version
  app/statements/        importer (upload flow), pdf (text and OCR), extract (LLM reading + checks),
                         fingerprints (dedupe), reconciliation, money, passwords (Keychain)
  app/categorize/        rules → cached result → LLM
  app/llm/               provider interface, Ollama provider, deterministic mock
  app/chat/              question → fixed query tools → answer
  tests/
frontend/                Vite + React + TypeScript 5.9 + Tailwind 4 + Recharts + lucide-react; Geist font bundled
data/                    gitignored: accountant.db (the only datastore)
```

### Upload flow (load-bearing path)

The LLM is a helping hand in the core of the app, not a last resort (user decision, 2026-11-08): there is no per-bank or per-layout code. `POST /api/imports` -> `statements/importer.py`.

1. In the request: SHA-256 duplicate check (409), and for an encrypted PDF its password (tried with every saved Keychain password first). The file is stored as an import in progress.
2. In the background: the file becomes text (`statements/pdf.py`: text layer with column gaps kept, Docling + macOS Vision OCR for scans; CSV as is).
3. The local LLM extracts the accounts (bank, last 4, bank or card, currency, balances, period) and every transaction (date, description, amount, in or out), chunk by chunk (`statements/extract.py`).
4. Code verifies every answer against the text: amounts must appear in it, dates must fall in the statement period, bank names, account numbers and balances must appear in it, and opening + transactions must equal closing. What fails is kept but flagged (`needs_review`, `unreconciled`), never silently trusted or "fixed".
5. One statement per account found; banks and accounts are created or reused; overlapping statements are de-duplicated by fingerprint.
6. Categorization: rules, stored results, then the LLM constrained to the category list. The import is done once categorized.

UI: welcome screen, then upload (one or more files, live progress), then the dashboard (metrics per currency, spending donut, monthly bars, filters, editable transactions table, "upload more"). Categories & rules is the secondary screen.

## Specialist rules (`.claude/rules/`)

Domain detail lives in focused files. **Read the relevant one before editing that area.**

| File | Read when touching |
| --- | --- |
| [.claude/rules/coding-practices.md](.claude/rules/coding-practices.md) | any code change |
| [.claude/rules/testing.md](.claude/rules/testing.md) | writing or changing tests, fixing bugs |
| [.claude/rules/security.md](.claude/rules/security.md) | privacy, passwords, logging, anything that could touch the network |
| [.claude/rules/statements.md](.claude/rules/statements.md) | `backend/app/statements/` - text extraction, LLM reading and its checks, money, reconciliation, dedupe |
| [.claude/rules/llm-pipeline.md](.claude/rules/llm-pipeline.md) | `backend/app/llm/`, `categorize/`, `chat/` |
| [.claude/rules/database.md](.claude/rules/database.md) | `backend/app/db.py`, `migrations/`, any SQL |
| [.claude/rules/api.md](.claude/rules/api.md) | `backend/app/main.py` and routes |
| [.claude/rules/frontend.md](.claude/rules/frontend.md) | `frontend/` |

## Critical invariants (never break)

- **Nothing leaves the machine.** No outbound network calls except `localhost:11434` (Ollama). The one exception is `make models`, run once by the user to download the Docling models; at runtime Docling runs with `HF_HUB_OFFLINE=1` and a local models path. No cloud LLMs, analytics, CDNs at runtime, or update checks. Server binds `127.0.0.1` only. See `security.md`.
- **The LLM extracts, code verifies against the source text** (changed by user decision on 2026-11-08; before, parsers were the only source of amounts and dates). Every amount the LLM returns must appear in the statement text, every date must fall in the statement period, and balances must reconcile; anything that fails is flagged `needs_review` / `unreconciled`, never silently trusted. Totals and aggregates are always computed in code: the chat's LLM only phrases answers. See `statements.md` / `llm-pipeline.md`.
- **Money is integer minor units (cents/paise) plus a currency code - never floats.** Currencies are never summed together. See `statements.md`.
- **Dates come out of the LLM as ISO `YYYY-MM-DD`** and are checked against the statement period; a yearless or ambiguous date is resolved by the model reading the whole statement, and a date outside the period is flagged. See `statements.md`.
- **Statement passwords live in the macOS Keychain only**: never in SQLite, logs, `.env`, or git. See `security.md`.
- **No real financial data in git**: the repo is public. Test fixtures are synthetic. See `security.md`.

## Git workflow

`feature/*` → `dev` (development) → `stage` (testing) → `prod` (release). Branch from `dev`; never commit directly to `stage` or `prod`; promote only through PRs. Small PRs split at natural seams; do not stack branches on unmerged PRs. Full rules: [CONTRIBUTING.md](CONTRIBUTING.md).

- **Commits:** conventional, lowercase type, imperative, first line under 72 chars. Types: `feat` `fix` `refactor` `docs` `test` `chore` `style` `perf` `build` `ci`.
- **No AI attribution:** never add a `Co-Authored-By` trailer to commits, and never add a "🤖 Generated with Claude Code" line (or any AI attribution line) to PR descriptions, issues or comments.
- **No em dashes** in anything written: commits, PRs, docs, code comments, UI copy. Use a colon, comma, parentheses or a plain hyphen.
- **Merging into `stage` or `prod`** happens only when the user explicitly asks.

## Conventions

- **Scope discipline:** small reviewable changes, preserve behavior unless asked, no new dependencies without a stated reason, delete no files unless clearly unused or requested.
- **Logging:** Python `logging` with ids and timings (statement id, row counts, durations). Never log transaction descriptions, amounts, account numbers or passwords.
- Frontend talks to the backend only through `frontend/src/lib/api.ts`; shared response types in `frontend/src/types/`.

## Config

Backend config via `.env` at repo root, `DATABASE_PATH` (default `<repo>/data/accountant.db`), `OLLAMA_URL` (default `http://127.0.0.1:11434`), `LLM_PROVIDER` (`ollama` | `mock`), `LLM_MODEL`, `PORT` (default `8765`). No secrets live in `.env`; bank passwords are in the Keychain.
