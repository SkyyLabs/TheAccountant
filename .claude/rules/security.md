# Security and privacy rules

Applies to all code. The product promise is **your financial data never leaves this Mac**. Read alongside the domain rule for the area you are touching.

## Nothing leaves the machine

- The only allowed outbound connection is the local Ollama server (`OLLAMA_URL`, default `http://127.0.0.1:11434`). Config validation rejects any non-loopback `OLLAMA_URL`.
- No cloud LLMs, analytics, error reporting, update checks, font or script CDNs, or remote images at runtime. Frontend assets are bundled at build time.
- The server binds `127.0.0.1` only, never `0.0.0.0`.
- Adding any dependency that phones home (telemetry on by default) requires disabling it, or choosing another package.

## Statement passwords

- Remembered per bank in the **macOS Keychain** via `keyring` (service `TheAccountant`, account = bank id). Never stored in SQLite, `.env`, logs, browser storage, or git.
- Sent from the UI only in the upload request body; never echoed back in responses.
- A wrong password returns a clear error and does not overwrite the saved one until a new password succeeds.

## Logging

Never log transaction descriptions, amounts, balances, account or card numbers, statement contents, LLM prompts containing them, or passwords. Do log safe context: statement id, bank id, row counts, durations, error codes.

## The repository is public

- Never commit real statements, the database, exports, screenshots of real data, or `.env`. `.gitignore` covers them; never force-add past it.
- Test fixtures are synthetic: invented merchants, round amounts, fake account numbers. When a real layout must be reproduced, recreate it with fake values.
- Never paste real transactions into PRs, issues, commit messages, `PROJECT_STATE.md` or `.memory/`.

## Agent access

`.claude/settings.json` denies agents reading `data/`, `statements/` and real fixtures. Debug with synthetic files or ask the user to describe the layout.

## Destructive-command guard

A PreToolUse hook (`.claude/hooks/guard-destructive.py`, wired in `.claude/settings.json`) forces a confirmation on destructive Bash commands — recursive `rm`, deleting the database, hand-written writes to SQLite, force push, `git reset --hard`, staging data files — and on pushing or committing directly to `stage`/`prod`. It is a safety net, not a sandbox: approve intentional work, never route around it.

## Future work

Database encryption (SQLCipher) is deferred by user decision; FileVault covers the disk for now.
