# TheAccountant

A private, offline personal-finance app that runs only on the owner's Mac. The user uploads bank and credit-card account statements (CSV or PDF, from any US or Indian bank); the app extracts transactions, categorizes them with a **local** LLM (Ollama), and shows them in a tabbed browser UI with date, category, amount and account filters, charts, and a chat for questions like "how much did I spend on food in March?". Statements and all results are stored in a local SQLite database so re-uploads are detected and skipped. **Nothing leaves the machine** - no cloud, no login, no telemetry, no network calls except to the local Ollama server.

Out of scope for now: taxes, bank-sync APIs, email parsing, budgets, multi-user, cloud anything. Future work is listed in `PROJECT_STATE.md`.

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
  app/statements/        upload, fingerprinting, PDF unlock, parsing, reconciliation
  app/statements/banks/  per-bank profiles (chase, discover, capital_one, sofi, icici, hdfc, sbi, axis)
  app/categorize/        rules → cached result → LLM
  app/llm/               provider interface, Ollama provider, deterministic mock
  app/chat/              question → fixed query tools → answer
  tests/
frontend/                Vite + React + TypeScript 5.9 + Tailwind; shadcn/ui and Recharts added with the first screen that needs them
data/                    gitignored: accountant.db (the only datastore)
```

### Upload flow (load-bearing path)

The user uploads files and nothing else (user decision, 2026-11-08): no bank picker, no account form, no column mapping. `POST /api/imports` -> `statements/importer.py`.

1. SHA-256 of the bytes; an already-imported file is reported (409) with its statement ids.
2. Encrypted PDF: tried with every bank's saved Keychain password; otherwise the UI asks for the password, which is saved under the bank found in the file once it opened it.
3. Whose statement: patterns first (bank names, masked account numbers, file names, card/bank wording), the local LLM only for what they miss. The bank name and last 4 digits are accepted only if they appear in the file.
4. How to read it: PDF transaction lines (`lines.py`: one section per account, running-balance check per row), else tables (pdfplumber, Docling, word positions) with the LLM-proposed layout settled by code; CSV through the layout proposal. A known account's saved layout is reused with no LLM call.
5. Reconciliation per account: opening + transactions = closing (cards: previous - transactions = new) and, where printed, every row's running balance. Anything that does not check out is stored but flagged (`unreconciled`, rows `needs_review`), never silently trusted or "fixed".
6. De-duplication by transaction fingerprint, so overlapping statements do not double count.
7. Categorization in the background: rules, stored results, then the LLM constrained to the category list.

UI (redesign in progress, user direction 2026-11-08): welcome screen, then a single upload screen (one or more files), then a dashboard with charts, filters and the categorized transactions, with "upload more" always at hand. Categories & Rules and Chat stay as secondary screens.

## Specialist rules (`.claude/rules/`)

Domain detail lives in focused files. **Read the relevant one before editing that area.**

| File | Read when touching |
| --- | --- |
| [.claude/rules/coding-practices.md](.claude/rules/coding-practices.md) | any code change |
| [.claude/rules/testing.md](.claude/rules/testing.md) | writing or changing tests, fixing bugs |
| [.claude/rules/security.md](.claude/rules/security.md) | privacy, passwords, logging, anything that could touch the network |
| [.claude/rules/statements.md](.claude/rules/statements.md) | `backend/app/statements/` - parsing, money, dates, reconciliation, dedupe |
| [.claude/rules/llm-pipeline.md](.claude/rules/llm-pipeline.md) | `backend/app/llm/`, `categorize/`, `chat/` |
| [.claude/rules/database.md](.claude/rules/database.md) | `backend/app/db.py`, `migrations/`, any SQL |
| [.claude/rules/api.md](.claude/rules/api.md) | `backend/app/main.py` and routes |
| [.claude/rules/frontend.md](.claude/rules/frontend.md) | `frontend/` |

## Critical invariants (never break)

- **Nothing leaves the machine.** No outbound network calls except `localhost:11434` (Ollama). The one exception is `make models`, run once by the user to download the Docling models; at runtime Docling runs with `HF_HUB_OFFLINE=1` and a local models path. No cloud LLMs, analytics, CDNs at runtime, or update checks. Server binds `127.0.0.1` only. See `security.md`.
- **The LLM is never the source of an amount or date when a parser can read it.** LLM-extracted values are marked `needs_review`. The chat computes numbers in code; the LLM only phrases the answer. See `statements.md` / `llm-pipeline.md`.
- **Money is integer minor units (cents/paise) plus a currency code - never floats.** Currencies are never summed together. See `statements.md`.
- **Date format is per bank** (US `MM/DD`, India `DD/MM`), never guessed per row. See `statements.md`.
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
