# LLM pipeline rules

Applies when touching `backend/app/llm/`, `backend/app/categorize/` and `backend/app/chat/`.

## Local only, swappable through configuration

- Providers live behind one interface in `backend/app/llm/base.py`, selected by `get_llm_provider()` in `backend/app/llm/__init__.py` from `LLM_PROVIDER` (`ollama` | `mock`). Business logic never branches on the active provider.
- **There is no cloud provider and none may be added**: see `security.md`.
- The `mock` provider is deterministic and is the default in tests. Tests never call Ollama.
- Model name comes from `LLM_MODEL` (default `qwen2.5:7b`, fallback `llama3.1:8b`); never hardcoded at a call site. Must fit an 18 GB M3 Pro - stay at 7-8B.
- Use Ollama's structured output (`format` = JSON schema) for every call whose result the code consumes. Prompts live next to their caller as plain strings or files, not in a prompt framework.

## Where the LLM is used, and where it is not

| Task | LLM role | Code role |
|---|---|---|
| Statement layout (first upload per account) | Name the header line, columns, amount mode and balance labels (`statements/layout.py`) | Settle header line, date format, card sign and labels against the file; apply to every row; fall back to header heuristics; preview with reconciliation; save only after the user confirms |
| Categorization | Pick one category from the allowed list (enum in the schema) | Rules first, stored results second, LLM last; store the result |
| Chat | Choose a query tool and its arguments; phrase the answer | Run the query, compute every number |

The LLM **never** produces an amount, a date, a balance or a total that the user sees as fact.

## Categorization

Implemented in `backend/app/categorize/categorizer.py`; runs as a background task after each upload, and again via `POST /api/transactions/categorize`.

1. User rules (exact or contains-match on the merchant key, optional signed amount range; highest priority first) - no LLM call.
2. Stored result for the same merchant key (the user's own choice first, then the latest; results still needing review are ignored) - no LLM call.
3. LLM, one question per merchant and direction, batches of 20, constrained to the category enum for the bank's region (`both` plus `US` or `IN`). Confidence below 0.6, `Uncategorized`, or an invalid answer after one retry → `Uncategorized` + `needs_review`. Ollama down → nothing assigned, statement `categorization_status = llm_unavailable`, retried later.

The merchant key is the description lower-cased without punctuation or words containing digits (reference numbers).

A user correction is stored as a new row (the original LLM result stays for audit) and the UI offers "always categorize X as Y" as a rule.

## Chat

- The LLM calls fixed tools: `sum_transactions`, `list_transactions`, `compare_periods`, `top_merchants` - each takes typed filters (date range, categories, amount range, accounts, currency).
- No text-to-SQL. No raw SQL from the model.
- The answer shows the filters used and the computed figures, grouped by currency.

## Robustness

- Treat model output as untrusted input: validate against the schema; reject and retry once, then fall back to `needs_review`.
- Normalize Ollama errors and timeouts into the app's error type. If Ollama is not running, the UI says so plainly; parsing and browsing still work without it.
- Log timings and counts per batch, never the prompt or transaction text.
- Load nothing heavy at import time; the mock path imports no ML libraries.
- No RAG, embeddings or vector store unless explicitly requested.
