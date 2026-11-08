# Frontend rules

Applies when touching `frontend/` (Vite + React + TypeScript + Tailwind + shadcn/ui + Recharts).

- **Check installed versions before writing framework code** (`frontend/package.json`); APIs change between majors. Prefer the docs shipped in `node_modules` over memory.
- **The UI talks to the backend only through `frontend/src/lib/api.ts`.** Response types live in `frontend/src/types/`. No business logic, parsing or money arithmetic in the frontend beyond display formatting.
- **Fully offline:** no CDN fonts, scripts, icons or images. Everything is bundled. No analytics.
- **Tabs:** Overview, Transactions, Statements, Categories & Rules, Chat - one route each under `frontend/src/routes/`, feature UI in `frontend/src/components/<tab>/`, shadcn primitives in `frontend/src/components/ui/`.
- **Money display:** format from minor units with the transaction's currency - `en-US` grouping for USD, `en-IN` (lakh/crore) for INR. Never show a mixed-currency total; show one figure per currency.
- **Filters** (date range, category, amount range, account, currency, text search) are reflected in the URL query string so views are shareable and survive reload. The URL parameter names are the backend's (`components/transactions/Filters.tsx` `FILTER_KEYS`), so the page passes them through unchanged.
- **First upload for a bank:** dialog asks for the bank (defaults + "Other: type a name") and, when the backend replies `pdf_password_required`, the password with a "remember for this bank" checkbox (on by default). Never store the password in browser storage.
- **Charts** (Recharts) are `aria-hidden` and each has a "Show as table" alternative with the same figures; one section per currency, never combined. Overview sends `spending_only=true` unless the user unticks it.
- **Never hide uncertainty:** `needs_review`, `unreconciled` and `unverifiable` are visible badges with an action, not colour alone.
- **State:** local React state and URL params; add a data library (e.g. TanStack Query) only when caching across tabs needs it. `localStorage` holds UI preferences only - never financial data.
- **Accessible by default:** labelled inputs, visible focus, keyboard-operable tables and dialogs, loading and empty states, clear errors.
- **Versions:** TypeScript is pinned to 5.9.3 until `typescript-eslint` supports TS 7. shadcn/ui is added (via its CLI) with the first screen that needs a dialog, popover or combobox (plain semantic tables until then); Recharts with the Overview charts.
- Build the app; no landing page.
