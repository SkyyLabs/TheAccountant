# API rules

Applies when touching `backend/app/main.py` and route modules.

## Structure

- `main.py` holds `create_app()`: mounts `/api/*` routes and serves the built frontend (`frontend/dist`) at `/`. One process, `127.0.0.1` only, port `PORT` (default `8765`).
- Routes stay thin: validate input, call `statements/`, `categorize/` or `chat/`, shape the response. All SQL goes through `db.py`.
- There is no auth: single user, loopback only. Do not add login. Do not bind to other interfaces.

## Route design

- Pydantic models for every request and response body.
- **One error shape:** `{"error": {"code", "message"}}` for app errors, validation errors and HTTP errors, plus an optional `details` object when the client needs data to recover (the existing statement id on a duplicate, CSV rows and a suggested mapping on `csv_mapping_required`).
- Status codes: missing resource → 404, duplicate upload → 409 `duplicate_statement` (with the existing statement id), unreadable PDF → 422 `pdf_unreadable`, PDF with no ruled table → 422 `pdf_no_tables`, CSV or PDF needing a column mapping → 422 `csv_mapping_required`, wrong or missing PDF password → 422 with code `pdf_password_required` / `pdf_password_invalid`, payload too large → 413, Ollama unavailable → 503 with code `llm_unavailable` where the LLM is required (chat); the statement layout proposal falls back to heuristics instead (`suggestion_source: "heuristic"`).
- Raise specific errors; no broad `except` that hides parser failures.
- Upload size limit enforced in middleware before the body is buffered. `MAX_UPLOAD_MB` default 25.
- Long work (LLM categorization of a large statement) runs in a background task; the UI polls statement status. Parsing itself is synchronous.
- Fail at startup on bad config (non-loopback `OLLAMA_URL`, unknown `LLM_PROVIDER`).

## Endpoint surface (planned: keep current)

`GET /api/health` · `GET /api/banks` · `POST /api/banks` · `GET /api/accounts` (filter: bank_id) · `POST /api/accounts` · `POST /api/imports` (multipart: file, optional password, remember default true; returns every statement found, one per account) · `POST /api/statements` (older explicit path: file, account_id, optional mapping JSON, password, remember) · `POST /api/statements/preview` (multipart: file, account_id, mapping, optional password; never saves it) · `GET /api/statements` · `GET /api/statements/{id}` · `POST /api/statements/{id}/reprocess` · `GET /api/transactions` (filters, all optional: date_from, date_to, category_ids and account_ids (repeatable, any of), currency, amount_min and amount_max (typed text parsed by `parse_amount`, compared with the size of the amount), q (description contains, case-insensitive), spending_only (leave out categories marked `excluded_from_spending`)) · `POST /api/transactions/categorize` (retry pending, 202) · `PATCH /api/transactions/{id}` (category; returns a suggested rule) · `GET /api/summary` (same filters; totals, by_month and by_category, every row per currency, money in and money out as positive totals) · `GET|POST|PATCH|DELETE /api/categories` · `GET|POST|PATCH|DELETE /api/rules` · `POST /api/chat`
