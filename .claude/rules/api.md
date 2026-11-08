# API rules

Applies when touching `backend/app/main.py` and route modules.

## Structure

- `main.py` holds `create_app()`: mounts `/api/*` routes and serves the built frontend (`frontend/dist`) at `/`. One process, `127.0.0.1` only, port `PORT` (default `8765`).
- Routes stay thin: validate input, call `statements/`, `categorize/` or `chat/`, shape the response. All SQL goes through `db.py`.
- There is no auth: single user, loopback only. Do not add login. Do not bind to other interfaces.

## Route design

- Pydantic models for every request and response body.
- **One error shape:** `{"error": {"code", "message"}}` for app errors, validation errors and HTTP errors.
- Status codes: missing resource → 404, duplicate upload → 409 (with the existing statement id), wrong or missing PDF password → 422 with code `pdf_password_required` / `pdf_password_invalid`, payload too large → 413, Ollama unavailable → 503 with code `llm_unavailable`.
- Raise specific errors; no broad `except` that hides parser failures.
- Upload size limit enforced in middleware before the body is buffered. `MAX_UPLOAD_MB` default 25.
- Long work (LLM categorization of a large statement) runs in a background task; the UI polls statement status. Parsing itself is synchronous.
- Fail at startup on bad config (non-loopback `OLLAMA_URL`, unknown `LLM_PROVIDER`).

## Endpoint surface (planned — keep current)

`GET /api/health` · `GET /api/banks` · `POST /api/banks` · `POST /api/statements` (multipart: file, bank_id, optional password, remember) · `GET /api/statements` · `GET /api/statements/{id}` · `POST /api/statements/{id}/reprocess` · `GET /api/transactions` (filters: date_from, date_to, category_ids, amount_min, amount_max, account_ids, currency, q) · `PATCH /api/transactions/{id}` (category) · `GET /api/summary` (by month/category/currency) · `GET|POST|PATCH|DELETE /api/categories` · `GET|POST|PATCH|DELETE /api/rules` · `POST /api/chat`
