# LLM pipeline rules

Applies when touching `backend/app/llm/`, `backend/app/categorize/` and `backend/app/chat/`.

## Local only, swappable through configuration

- Providers live behind one interface in `backend/app/llm/base.py`, selected by `get_llm_provider()` in `backend/app/llm/__init__.py` from `LLM_PROVIDER` (`ollama` | `mock`). Business logic never branches on the active provider.
- **There is no cloud provider and none may be added** — see `security.md`.
- The `mock` provider is deterministic and is the default in tests. Tests never call Ollama.
- Model name comes from `LLM_MODEL` (default `qwen2.5:7b`, fallback `llama3.1:8b`); never hardcoded at a call site. Must fit an 18 GB M3 Pro — stay at 7–8B.
- Use Ollama's structured output (`format` = JSON schema) for every call whose result the code consumes. Prompts live next to their caller as plain strings or files, not in a prompt framework.

## Where the LLM is used — and where it is not

| Task | LLM role | Code role |
|---|---|---|
| Unknown statement layout | Propose a column/field mapping | Apply it, show a preview, save only after user confirms |
| Categorization | Pick one category from the allowed list (enum in the schema) | Rules first, stored results second, LLM last; store the result |
| Chat | Choose a query tool and its arguments; phrase the answer | Run the query, compute every number |

The LLM **never** produces an amount, a date, a balance or a total that the user sees as fact.

## Categorization

1. User rules (exact or contains-match on normalized merchant, optional amount range) — no LLM call.
2. Stored result for the same normalized merchant — no LLM call.
3. LLM, batched (many transactions per call), constrained to the category enum. Low-confidence or invalid output → `Uncategorized` + `needs_review`.

A user correction is stored as a new row (the original LLM result stays for audit) and the UI offers "always categorize X as Y" as a rule.

## Chat

- The LLM calls fixed tools: `sum_transactions`, `list_transactions`, `compare_periods`, `top_merchants` — each takes typed filters (date range, categories, amount range, accounts, currency).
- No text-to-SQL. No raw SQL from the model.
- The answer shows the filters used and the computed figures, grouped by currency.

## Robustness

- Treat model output as untrusted input: validate against the schema; reject and retry once, then fall back to `needs_review`.
- Normalize Ollama errors and timeouts into the app's error type. If Ollama is not running, the UI says so plainly; parsing and browsing still work without it.
- Log timings and counts per batch, never the prompt or transaction text.
- Load nothing heavy at import time; the mock path imports no ML libraries.
- No RAG, embeddings or vector store unless explicitly requested.
