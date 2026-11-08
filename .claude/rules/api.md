# API rules

Applies when touching `backend/app/main.py` and route modules.

## Structure

- `main.py` holds `create_app()`: mounts `/api/*` routes and serves the built frontend (`frontend/dist`) at `/`. One process, `127.0.0.1` only, port `PORT` (default `8765`).
- Routes stay thin: validate input, call `statements/`, `categorize/` or `chat/`, shape the response. All SQL goes through `db.py`.
- There is no auth: single user, loopback only. Do not add login. Do not bind to other interfaces.

## Route design

- Pydantic models for every request and response body.
- **One error shape:** `{"error": {"code", "message"}}` for app errors, validation errors and HTTP errors, plus an optional `details` object when the client needs data to recover (the existing import id on a duplicate).
- Status codes: missing resource → 404, duplicate upload → 409 `duplicate_statement` (with the existing import id), unreadable PDF → 422 `pdf_unreadable`, file that is neither PDF nor text → 415, wrong or missing PDF password → 422 with code `pdf_password_required` / `pdf_password_invalid`, payload too large → 413, Ollama unavailable → 503 with code `llm_unavailable` where the LLM is answered in the request (chat); background work (imports, categorization) records a plain-language failure instead.
- Raise specific errors; no broad `except` that hides parser failures.
- Upload size limit enforced in middleware before the body is buffered. `MAX_UPLOAD_MB` default 25.
- Long work (reading a statement with the LLM, categorizing) runs in a background task; the UI polls `GET /api/imports/{id}`. Only the duplicate and password checks happen in the request.
- Fail at startup on bad config (non-loopback `OLLAMA_URL`, unknown `LLM_PROVIDER`).

## Endpoint surface (planned: keep current)

`GET /api/health` · `GET /api/banks` · `GET /api/accounts` (filter: bank_id) · `POST /api/imports` (multipart: file, optional password, remember default true; 202, read in the background) · `GET /api/imports` · `GET /api/imports/{id}` (status, progress, error, rejected count, statements) · `GET /api/statements` · `GET /api/statements/{id}` · `GET /api/transactions` (filters, all optional: date_from, date_to, category_ids and account_ids (repeatable, any of), currency, amount_min and amount_max (typed text parsed by `parse_amount`, compared with the size of the amount), q (description contains, case-insensitive), spending_only (leave out categories marked `excluded_from_spending`)) · `POST /api/transactions/categorize` (retry pending, 202) · `PATCH /api/transactions/{id}` (category; returns a suggested rule) · `GET /api/summary` (same filters; totals, by_month and by_category, every row per currency, money in and money out as positive totals) · `GET|POST|PATCH|DELETE /api/categories` · `GET|POST|PATCH|DELETE /api/rules` · `POST /api/chat`
