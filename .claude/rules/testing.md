# Testing rules

Applies when writing or changing tests, and to every feature and bug fix. Conventions below are chosen for M1 (pytest for the backend, Vitest + Testing Library for the frontend); update this file if M1 settles on something different.

## Commands

```bash
make test                                                         # backend suite
.venv/bin/pytest backend/tests/statements/test_hdfc.py            # one file
.venv/bin/pytest backend/tests/statements/test_hdfc.py::test_name # one test
cd frontend && npx vitest run src/components/transactions/Filters.test.tsx   # one frontend file
make verify                                                       # full check sequence, required before claiming done
```

Tests need no services: no Ollama, no network, no real database. They use `LLM_PROVIDER=mock` and a temporary SQLite file per test (the `settings` and `client` fixtures in `backend/tests/conftest.py`).

## Where tests live and how they are named

- Backend: `backend/tests/` mirroring `backend/app/` (`backend/app/statements/money.py` → `backend/tests/statements/test_money.py`). Shared fixtures in `backend/tests/conftest.py`.
- Frontend: next to the component, `Component.test.tsx`.
- Synthetic statement fixtures: `backend/tests/fixtures/statements/<bank_id>/` (CSV and PDF). Real statements never go in the repo; `backend/tests/fixtures/real/` is gitignored for local-only checks.
- **Test names state the behavior and the expected outcome**: `test_duplicate_upload_returns_existing_statement`, `test_hdfc_dr_suffix_is_money_out`, not `test_upload_2`. If the name needs "and", it is two tests.

## Choose the level

| Level | Use for | Limits |
|---|---|---|
| Unit | Money and date parsing, fingerprints, reconciliation maths, rule matching, chat tool arithmetic, LLM output validation | No disk except temp files, milliseconds |
| Integration | Route → service → SQLite: upload flow, duplicate detection, categorization order, filters on `GET /api/transactions` | FastAPI `TestClient`, temp DB, seconds |
| End-to-end | Later, a handful: upload a statement and see it in Transactions | Only once the UI exists |

Test at the **public seam**: the parser's `parse(file, profile)`, the repository functions, the HTTP routes, the React component as a user sees it. Never test private helpers directly, and never check a result by querying SQLite when a repository read exists.

## Writing a test

- **Arrange, Act, Assert**, visibly separated. One behavior per test.
- **DAMP over DRY.** A test reads top to bottom as a specification. Use builders for value objects (`make_transaction(amount_minor=-1250)`), not shared setup that hides what matters. No loops or conditionals in tests; use `pytest.mark.parametrize` for tables of cases (date formats, number formats).
- **Expected values are literals worked out by hand**, never recomputed the way the code computes them. `assert parse_amount("1,23,456.78 Dr") == -12345678`.
- **Assert on what only the code under test produces** (its error code, its output) so the test fails if that code is removed.
- **Deterministic and isolated:** freeze time where dates matter, no reliance on test order, each test gets its own temp DB.

## Mocks and test doubles

Preference order: real implementation, then fake, then stub, then mock.

- The boundaries here are the **LLM** (use the `mock` provider, which returns scripted, deterministic output), the **macOS Keychain** (use an in-memory `keyring` backend in tests), and the clock.
- Never mock `db.py`, parsers or the categorizer; use the real ones against a temp database.
- To test bad LLM output, script the mock provider to return malformed JSON, an unknown category, or a timeout.

## Test data and fixtures

- Every fixture is **synthetic**: invented merchants, fake account numbers, round amounts. When a real layout must be reproduced, recreate it with fake values.
- Data must be able to show the bug:
  - Dates where day and month differ and both are ≤ 12 (`03/04/2026`), so a format swap fails.
  - Indian grouping (`1,23,456.78`), `Cr`/`Dr` suffixes, parenthesized negatives, separate debit/credit columns.
  - Card statements where charges are positive in the file but money out after normalization.
  - Two currencies in one dataset, so a cross-currency sum fails.

## Workflow

- **New behavior: red first.** Write the test, run it, see it fail for the expected reason, then write the minimum code to pass.
- **Bug fix: reproduce first** with a failing test, then fix.
- **Mutation-check every fix:** revert the fix, confirm the test fails, restore it.
- After the targeted test passes, run `make verify`.

## Integrity (non-negotiable)

- **Never weaken, delete, skip (`skip`, `xfail`, `.only`, commenting out) or loosen a test to make it pass** without telling the user explicitly and why.
- **Never hard-code values or special-case fixture inputs** in parsers or profiles. A bank profile must work for any statement in that layout, not just the fixture.
- If a test looks wrong, or the task cannot be done without breaking one, stop and say so.
- Tests never call Ollama, never read `data/accountant.db`, and never use real statements.
- "Tests pass" requires evidence: the command and its output, including how many tests ran. Zero tests collected is a failure.

## Always test in this project

- Every bank profile: its synthetic fixture parses to the expected transactions **and reconciles**.
- Money parsing to integer minor units with the right sign, for every format listed above.
- Date parsing per bank format, including the day/month swap case.
- Reconciliation: balanced, unbalanced (difference reported) and no-balance (`unverifiable`) statements.
- Duplicates: same file twice; overlapping statements; genuine identical transactions within one statement are kept.
- Categorization order: rule beats stored result beats LLM; invalid LLM output becomes `Uncategorized` + `needs_review`.
- Chat tools compute totals per currency and never mix currencies.
- Password handling: wrong password returns `pdf_password_invalid` and does not overwrite the saved one.

## Not worth testing

FastAPI, Pydantic, SQLite or React internals, shadcn components, trivial wiring, and states that cannot occur.

## Done checklist

- [ ] Every new behavior and every bug fix has a test that was seen failing first
- [ ] Tests sit at public seams, with names that state behavior
- [ ] Mocks only for the LLM, Keychain and clock; fixtures synthetic
- [ ] No test skipped, weakened or deleted silently
- [ ] `make verify` passes, output reported with the test count
