# Contributing

## Branch strategy

```text
feature/*  →  dev  →  stage  →  prod
```

TheAccountant is a local app with no hosted deployment, so the branches mean:

| Branch | Purpose | Receives changes from | Used as |
|---|---|---|---|
| `dev` | Development, **default branch** | `feature/*` via PR | Day-to-day integration; CI on every PR |
| `stage` | Testing | `dev` via PR | Release candidate: run it against real statements, check every tab |
| `prod` | Release | `stage` via PR | The version the user runs day to day; tag each promotion `vX.Y.Z` |

Rules:

- Branch all feature work from `dev`. Name branches after the work: `feature/<short-name>`, e.g. `feature/app-skeleton`, `feature/hdfc-parser`.
- Never commit directly to `stage` or `prod`. Promote through PRs only: `dev → stage`, then `stage → prod`.
- Never force-push `dev`, `stage` or `prod`.
- Agents open PRs into `stage` or `prod` only when the user explicitly asks.
- **Do not stack feature branches on unmerged PRs.** A branch built on an unmerged branch blocks finished work behind an unrelated review. Wait for the merge, or branch from `dev` and accept a small conflict later.

### Hotfixes

A bug in the released version: branch `hotfix/<name>` from `prod`, PR into `prod`, then immediately PR `prod` back into `stage` and `dev` so the fix is not lost on the next promotion.

## PR size

**Optimize pull requests for a human reader.** Someone should be able to read a PR start to finish in a few minutes; a 5-file PR gets reviewed, a 33-file PR gets rubber-stamped.

- A milestone is not automatically one PR. Split at natural seams - scaffolding, configuration, application logic, CI - each stands on its own.
- Every PR leaves the project runnable.
- Prefer several sequential `feature/*` branches over one broad one:

```text
feature/backend-skeleton        # FastAPI app, config, SQLite migrations
feature/frontend-shell          # Vite app with the five tabs
feature/statement-upload        # upload, fingerprint, duplicate detection
```

Generated scaffolding is the one reasonable exception - a framework's initial output cannot usefully be halved. Say so in the PR description.

## Pull request workflow

1. Branch from `dev`.
2. Run `make verify` locally; it must pass.
3. Open the PR against the correct target branch, using the template.
4. Request AI review. Check the review covers the **current head commit** - a review of an earlier commit says nothing about what you are about to merge.
5. Address valid findings; note anything intentionally declined, with reasoning, in the PR thread.
6. Re-run review if the changes were substantial.
7. Merge only once review is acceptable and CI is green.

## Code style

- No abstraction unless it solves a current problem or is a specifically required swap point. The deliberate ones here: the LLM provider interface and per-bank statement profiles. One file when one file is enough.
- Small functions, descriptive names, explicit inputs and outputs, flat call stacks. No managers, orchestrators or generic wrapper layers.
- Test behavior that can actually break; do not test framework internals.
- **This repository is public.** Never commit real statements, exported data, the database, `.env` files, or passwords. Test fixtures are synthetic.
