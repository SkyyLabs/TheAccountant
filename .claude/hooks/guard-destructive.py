#!/usr/bin/env python3
"""PreToolUse guard for Bash: require confirmation on destructive commands.

Reads the Claude Code PreToolUse hook payload on stdin. If the command matches a
destructive pattern, returns permissionDecision "ask" (shows the reason and
forces an explicit confirm) rather than "deny", so intentional destructive work
is still possible, just never silent. Exit 0 with no output = normal permission
flow.

Also guards the dev -> stage -> prod workflow: pushing to stage/prod, or
committing while checked out on stage/prod, asks first.

This is a safety net, not a sandbox.
"""
import json
import re
import subprocess
import sys

PROTECTED_BRANCHES = ("stage", "prod")

# (regex, reason). Regexes run against a lowercased, whitespace-normalized command.
RULES = [
    (r"\brm\b[^|;&\n]*\s-\w*r", "recursive file delete (rm -r/-rf)"),
    (r"\brm\s+-\w*r\w*\s+/(\s|$)", "delete targeting filesystem root"),
    (r"\bgit\s+push\b.*(--force\b|--force-with-lease\b|\s-\w*f\b)", "force push (rewrites remote history)"),
    (r"\bgit\s+reset\s+--hard\b", "git reset --hard (discards uncommitted work)"),
    (r"\bgit\s+clean\b.*-\w*[fd]", "git clean (deletes untracked files)"),
    (r"\bgit\s+checkout\s+--\s", "git checkout -- (discards file changes)"),
    (r"\bgit\s+branch\s+-\w*d\w*\s+.*\b(dev|stage|prod)\b", "deleting a long-lived branch"),
    (r"\bgit\s+push\b.*[\s:+](stage|prod)(\s|$|;|&|\|)", "pushing directly to stage/prod (promote through a PR)"),
    (r"\bdropdb\b", "dropping a database"),
    (r"\b(drop\s+table|drop\s+database|drop\s+schema|truncate)\b", "destructive SQL (DROP/TRUNCATE)"),
    (r"\bdelete\s+from\b", "SQL DELETE (row loss if unscoped)"),
    (r"\b(alembic\s+downgrade|prisma\s+migrate\s+reset|drizzle-kit\s+drop)\b", "destructive migration command"),
    (r">\s*\.env(\.\w+)?\b", "overwriting a .env secrets file"),
    (r"\bchmod\s+-r\b", "recursive permission change"),
    (r"\brm\b.*(\bdata/|\.db\b|\.sqlite3?\b)", "deleting the local database (all imported statements and results)"),
    (r"\bsqlite3\b.*\b(drop|delete|update)\b", "writing to the local database by hand"),
    (r"\bgit\s+add\b.*(\bdata/|\.db\b|\.pdf\b|\.csv\b|\s-f\b|--force\b)", "staging data files or forcing past .gitignore (repo is public)"),
]


def current_branch() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=3,
        ).stdout.strip()
    except Exception:
        return ""


def ask(reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": f"Guard: {reason}. Confirm this is intended.",
        }
    }))


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    if payload.get("tool_name") != "Bash":
        return 0
    command = (payload.get("tool_input") or {}).get("command", "")
    if not command:
        return 0

    normalized = re.sub(r"\s+", " ", command).lower()
    for pattern, reason in RULES:
        if re.search(pattern, normalized):
            ask(reason)
            return 0

    if re.search(r"\bgit\s+(commit|merge|cherry-pick|rebase)\b", normalized):
        branch = current_branch()
        if branch in PROTECTED_BRANCHES:
            ask(f"changing history on '{branch}' directly (branch from dev and promote through PRs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
