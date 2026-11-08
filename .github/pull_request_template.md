## Summary

<!-- What changed and why. One or two sentences. -->

## Target branch

- [ ] `feature/*` → `dev`
- [ ] `dev` → `stage`
- [ ] `stage` → `prod`
- [ ] `hotfix/*` → `prod` (back-merge to `stage` and `dev` follows)

## Milestone

<!-- e.g. M3 — PDF statements -->

## Changes

<!-- Bullet list of the meaningful changes. -->

## Validation

<!-- Exact commands run and what was observed. "Not verified: …" for anything not checked. -->

## Risks

<!-- Migrations, parsing/money correctness, privacy, UI. "None" if none. -->

## Checklist

- [ ] Scoped to a single concern; readable in a few minutes
- [ ] `make verify` passes locally
- [ ] No real statements, database files, `.env` files, or passwords committed (repo is public)
- [ ] No new outbound network calls (only local Ollama)
- [ ] `PROJECT_STATE.md` updated if this changes architecture, milestones, or known issues
- [ ] AI review run on the current head commit
- [ ] Review findings addressed or explicitly declined with reasoning
