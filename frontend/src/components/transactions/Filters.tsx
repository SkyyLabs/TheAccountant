import { useSearchParams } from "react-router";

import type { Account, Category } from "../../types/api";

/** URL parameters, named exactly as the backend's filters, so the page URL is the query. */
export const FILTER_KEYS = [
  "date_from",
  "date_to",
  "category_ids",
  "account_ids",
  "currency",
  "amount_min",
  "amount_max",
  "q",
  "spending_only",
] as const;

/** The filter part of the page URL, in a stable order, ready to send to the backend. */
export function filterQuery(params: URLSearchParams): string {
  const query = new URLSearchParams();
  for (const key of FILTER_KEYS) {
    for (const value of params.getAll(key)) if (value) query.append(key, value);
  }
  return query.toString();
}

const fieldClass =
  "mt-1 w-full rounded border border-slate-300 bg-white px-2 py-1 dark:border-slate-700 dark:bg-slate-900";

type Option = { id: number; label: string };

function CheckboxGroup({
  legend,
  name,
  options,
  selected,
  onChange,
}: {
  legend: string;
  name: string;
  options: Option[];
  selected: string[];
  onChange: (values: string[]) => void;
}) {
  return (
    <details className="relative">
      <summary className="cursor-pointer rounded border border-slate-300 px-2 py-1 text-sm dark:border-slate-700">
        {legend}
        {selected.length > 0 && ` (${selected.length})`}
      </summary>
      <fieldset className="absolute z-10 mt-1 max-h-64 w-56 overflow-y-auto rounded border border-slate-200 bg-white p-2 shadow dark:border-slate-700 dark:bg-slate-900">
        <legend className="sr-only">{legend}</legend>
        {options.map((option) => {
          const value = String(option.id);
          return (
            <label key={option.id} className="flex items-center gap-2 py-0.5 text-sm">
              <input
                type="checkbox"
                name={name}
                checked={selected.includes(value)}
                onChange={(event) =>
                  onChange(
                    event.target.checked
                      ? [...selected, value]
                      : selected.filter((item) => item !== value),
                  )
                }
              />
              {option.label}
            </label>
          );
        })}
      </fieldset>
    </details>
  );
}

export function Filters({ categories, accounts }: { categories: Category[]; accounts: Account[] }) {
  const [params, setParams] = useSearchParams();

  function set(key: (typeof FILTER_KEYS)[number], values: string[]) {
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        next.delete(key);
        for (const value of values) if (value) next.append(key, value);
        return next;
      },
      { replace: true },
    );
  }

  const text = (key: (typeof FILTER_KEYS)[number], label: string, type = "text") => (
    <div>
      <label htmlFor={`filter-${key}`} className="block text-xs font-medium text-slate-600 dark:text-slate-400">
        {label}
      </label>
      <input
        id={`filter-${key}`}
        type={type}
        value={params.get(key) ?? ""}
        onChange={(event) => set(key, [event.target.value])}
        className={fieldClass}
      />
    </div>
  );

  const active = filterQuery(params) !== "";

  return (
    <div role="search" aria-label="Filter transactions" className="mt-4 grid gap-3 sm:grid-cols-4 lg:grid-cols-8 lg:items-end">
      {text("date_from", "From", "date")}
      {text("date_to", "To", "date")}
      {text("q", "Description contains")}
      <div>
        <label htmlFor="filter-currency" className="block text-xs font-medium text-slate-600 dark:text-slate-400">
          Currency
        </label>
        <select
          id="filter-currency"
          value={params.get("currency") ?? ""}
          onChange={(event) => set("currency", [event.target.value])}
          className={fieldClass}
        >
          <option value="">All</option>
          <option value="USD">USD</option>
          <option value="INR">INR</option>
        </select>
      </div>
      {text("amount_min", "Amount at least")}
      {text("amount_max", "Amount at most")}
      <CheckboxGroup
        legend="Categories"
        name="category_ids"
        options={categories.map((c) => ({ id: c.id, label: c.name }))}
        selected={params.getAll("category_ids")}
        onChange={(values) => set("category_ids", values)}
      />
      <CheckboxGroup
        legend="Accounts"
        name="account_ids"
        options={accounts.map((a) => ({ id: a.id, label: `${a.bank_name} · ${a.name}` }))}
        selected={params.getAll("account_ids")}
        onChange={(values) => set("account_ids", values)}
      />
      {active && (
        <button
          type="button"
          onClick={() => setParams(new URLSearchParams(), { replace: true })}
          className="text-left text-sm text-blue-700 dark:text-blue-400"
        >
          Clear filters
        </button>
      )}
    </div>
  );
}
