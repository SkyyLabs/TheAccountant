# Testing rules

Applies when writing or changing tests, and to every bug fix.

Tests live in `backend/tests/` (synthetic statement fixtures in `backend/tests/fixtures/`) and run with `make test`; the full sequence is the verify command.

## A passing test is not evidence until you have seen it fail

**Mutation-check every fix:** revert the fix, confirm its test fails, restore the fix, confirm it passes. Tests written alongside a fix often pass against the reverted code because they are satisfied by something else:

- A test satisfied by a *different* layer's check (a route validation) instead of the code under test (the middleware).
- Test data that cannot show the bug (a gradient that survives point-sampling; a fully transparent image when the bug only shows on partial transparency).
- A patched setting that another code path also reads, so the patch, not the code, makes it pass.

Assert on something only the code under test produces (its own error message, its own output shape) so the test fails if that code is removed.

## What to test

- Test behavior that can actually break: every bank profile parses its fixture and reconciles; money parsing (Indian grouping, `Cr`/`Dr`, parentheses, debit/credit columns); date formats per bank; file and transaction dedupe; categorization order (rule → cache → LLM); chat tools' arithmetic; LLM output validation with malformed mock output.
- Do not test framework internals or trivial wiring.
- When you touch pure logic, add or update a case. When you fix a bug, add the test that would have caught it.
- Never call Ollama or touch `data/accountant.db` in tests: use the `mock` LLM provider and a temporary database per test. Fixtures are synthetic — never real statements (the repo is public).

## Reporting

Report the real command and its result. If something could not be run (no Docker, missing credentials), say so and say what covers it instead (for example, CI builds the image on every PR).
