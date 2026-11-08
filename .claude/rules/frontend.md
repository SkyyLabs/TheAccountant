# Frontend rules

Applies when touching `frontend/` (Vite + React + TypeScript + Tailwind + shadcn/ui + Recharts).

- **Check installed versions before writing framework code** (`frontend/package.json`); APIs change between majors. Prefer the docs shipped in `node_modules` over memory.
- **The UI talks to the backend only through `frontend/src/lib/api.ts`.** Response types live in `frontend/src/types/`. No business logic, parsing or money arithmetic in the frontend beyond display formatting.
- **Fully offline:** no CDN fonts, scripts, icons or images. Everything is bundled. No analytics.
- **Screens:** welcome (`/`, 2.5 s, then upload on a first visit or the dashboard once data exists), `/upload` (drop many files, live progress per file, inline password), `/dashboard` (metrics per currency, spending donut, monthly bars, filters, editable transactions table), `/categories`. One route each under `frontend/src/routes/`, feature UI in `frontend/src/components/<screen>/`.
- **Look:** semantic colour tokens in `index.css` (same scheme as WatchIt: indigo primary, soft tinted surfaces, dark mode via `prefers-color-scheme`), `.card` / `.field` / `.button-primary` / `.button-quiet` classes, Geist (bundled), lucide icons, generous spacing (`space-y-6`, `p-5`/`p-6` cards). Use the tokens, not raw palette colours.
- **Money display:** format from minor units with the transaction's currency - `en-US` grouping for USD, `en-IN` (lakh/crore) for INR. Never show a mixed-currency total; show one figure per currency.
- **Filters** (date range, category, amount range, account, currency, text search) are reflected in the URL query string so views are shareable and survive reload. The URL parameter names are the backend's (`components/transactions/Filters.tsx` `FILTER_KEYS`), so the page passes them through unchanged.
- **Upload asks nothing** except, when the backend replies `pdf_password_required` / `pdf_password_invalid`, the PDF's password with a "remember for this bank" checkbox (on by default). Never store the password in browser storage.
- **Charts** (Recharts) are `aria-hidden` and each has a "Show as table" alternative with the same figures; one section per currency, never combined. Overview sends `spending_only=true` unless the user unticks it.
- **Never hide uncertainty:** `needs_review`, `unreconciled` and `unverifiable` are visible badges with an action, not colour alone.
- **State:** local React state and URL params; add a data library (e.g. TanStack Query) only when caching across tabs needs it. `localStorage` holds UI preferences only - never financial data.
- **Accessible by default:** labelled inputs, visible focus, keyboard-operable tables and dialogs, loading and empty states, clear errors.
- **Versions:** TypeScript is pinned to 5.9.3 until `typescript-eslint` supports TS 7. No shadcn/ui: plain elements with the component classes in `index.css`.
- Build the app; no landing page.
