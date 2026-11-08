# Coding practices

Applies to all code changes. The one test that catches most violations: **every changed line should trace directly to the request.** If you cannot say which asked-for thing a line serves, cut it.

## Don't over-engineer (YAGNI)

Build the minimum that solves the stated problem. Nothing speculative.

- No feature, endpoint, flag or option that was not asked for.
- No error handling for cases that cannot occur. Trust internal callers and framework guarantees; validate only at real boundaries (user/API input, external service responses, LLM output, DB reads).
- No config knob for a value with one caller and one sensible default. Inline it.
- No "we might need it later." Add it when later arrives.
- If a bug fix is 3 lines, ship 3 lines. Do not refactor the surrounding function because you are in there.

Ask before writing: *would a senior reviewer call this more than the task needs?* If yes, cut.

## Don't over-modularize

Abstraction is a cost - indirection, a file to open, a name to learn. Pay it only for real reuse or to remove real duplication.

- **Do not extract a function, component or helper used once.** Inline code the reader can see beats a jump to a one-caller helper.
- **Do not add a layer to "separate concerns"** when the concern lives in one place. Work within the project's existing boundaries (`backend/app/` modules: `statements/`, `categorize/`, `llm/`, `chat/`, `db.py`; and `frontend/`); do not invent sub-layers inside them.
- **Do not split a file because it is long.** Split when parts change independently or are reused.
- **Rule of three:** extract on the third real duplication, not the first.
- No managers, orchestrators, coordinators or generic wrapper layers. A wrong abstraction is harder to unwind than duplication - when unsure, duplicate and wait for the pattern.
- The deliberate exceptions are named swap points (for example a provider interface selected by config). Here: the LLM provider interface (`backend/app/llm/base.py`) and per-bank statement profiles (`backend/app/statements/banks/`). Nothing else.

## Don't duplicate (the other direction)

Once a thing is genuinely shared, define it once.

- Shared helpers go in the backend module that owns the concept (money and date helpers in `backend/app/statements/money.py` / `dates.py`); never copy a function between backend modules or into the frontend.
- Command sequences (verify, migrate, run) live in one task runner, referenced by CI and docs. Do not restate them in a slash command, a doc and CI - they drift.
- Facts (env flags, table lists, invariants) live in one authoritative file; others link to it.
- Config values come from environment-driven config, never hardcoded at call sites.

## Surgical changes

- Touch only what the request requires. Do not reformat, rename or "improve" adjacent code.
- Match the surrounding style, naming and comment density.
- Remove imports, variables and functions **your** change orphaned. Leave pre-existing dead code alone - mention it, do not delete it, unless asked.
- No new dependency without a clear, stated reason. A few lines of local code beat a package for a trivial need.

## House style

- **Reuse before writing.** Search for an existing helper, repository method or component first.
- **Verify, don't assert.** Before claiming done, run the verify command (see `.claude/commands/verify.md`) and report real output.
- **Name for the reader.** Explicit scope in names (`statement_id`, `amount_minor`, not `id`, `amt`), clear handler and component names, no invented abbreviations.
- **Small functions, explicit inputs and outputs, flat call stacks.**
- **Comment the why, not the what**: only where the reason is not obvious from the code.
- **Small, reviewable diffs.** Preserve existing behavior unless the change is the point.
