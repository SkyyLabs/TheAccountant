import { ChevronDown, Search, X } from "lucide-react";
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

type FilterKey = (typeof FILTER_KEYS)[number];

/** The filter part of the page URL, in a stable order, ready to send to the backend. */
export function filterQuery(params: URLSearchParams): string {
  const query = new URLSearchParams();
  for (const key of FILTER_KEYS) {
    for (const value of params.getAll(key)) if (value) query.append(key, value);
  }
  return query.toString();
}

function isoDate(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

/** Quick ranges, counted back from today. */
export const RANGES = [
  { id: "all", label: "All time", from: () => null },
  { id: "year", label: "This year", from: (today: Date) => new Date(today.getFullYear(), 0, 1) },
  {
    id: "quarter",
    label: "3 months",
    from: (today: Date) => new Date(today.getFullYear(), today.getMonth() - 2, 1),
  },
  {
    id: "month",
    label: "This month",
    from: (today: Date) => new Date(today.getFullYear(), today.getMonth(), 1),
  },
] as const;

export function useFilterParams() {
  const [params, setParams] = useSearchParams();

  /** Change several parameters in one URL update. */
  function setMany(changes: Partial<Record<FilterKey | "review", string[]>>) {
    setParams(
      (current) => {
        const next = new URLSearchParams(current);
        for (const [key, values] of Object.entries(changes)) {
          next.delete(key);
          for (const value of values ?? []) if (value) next.append(key, value);
        }
        return next;
      },
      { replace: true },
    );
  }

  return {
    params,
    set: (key: FilterKey | "review", values: string[]) => setMany({ [key]: values }),
    setMany,
    clear: () => setParams(new URLSearchParams(), { replace: true }),
  };
}

export function RangeSwitch({ today = new Date() }: { today?: Date }) {
  const { params, setMany } = useFilterParams();
  const from = params.get("date_from");
  const active =
    RANGES.find((range) => {
      const start = range.from(today);
      return start ? isoDate(start) === from : !from;
    })?.id ?? null;
  return (
    <div role="group" aria-label="Date range" className="flex rounded-lg border bg-card p-1">
      {RANGES.map((range) => (
        <button
          key={range.id}
          type="button"
          aria-pressed={active === range.id}
          onClick={() => {
            const start = range.from(today);
            setMany({ date_from: start ? [isoDate(start)] : [], date_to: [] });
          }}
          className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
            active === range.id
              ? "bg-primary text-primary-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          {range.label}
        </button>
      ))}
    </div>
  );
}

function Checklist({
  label,
  name,
  options,
}: {
  label: string;
  name: "category_ids" | "account_ids";
  options: { id: number; label: string; color?: string }[];
}) {
  const { params, set } = useFilterParams();
  const selected = params.getAll(name);
  return (
    <details className="relative">
      <summary className="button-quiet cursor-pointer list-none">
        {label}
        {selected.length > 0 && (
          <span className="rounded-full bg-primary px-1.5 text-xs text-primary-foreground">
            {selected.length}
          </span>
        )}
        <ChevronDown aria-hidden="true" className="h-4 w-4 text-muted-foreground" />
      </summary>
      <fieldset className="card absolute z-30 mt-2 max-h-72 w-64 overflow-y-auto p-2 shadow-lg">
        <legend className="sr-only">{label}</legend>
        {options.map((option) => {
          const value = String(option.id);
          return (
            <label
              key={option.id}
              className="flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-muted"
            >
              <input
                type="checkbox"
                checked={selected.includes(value)}
                onChange={(event) =>
                  set(
                    name,
                    event.target.checked
                      ? [...selected, value]
                      : selected.filter((item) => item !== value),
                  )
                }
              />
              {option.color && (
                <span
                  aria-hidden="true"
                  className="h-2.5 w-2.5 rounded-full"
                  style={{ background: option.color }}
                />
              )}
              {option.label}
            </label>
          );
        })}
      </fieldset>
    </details>
  );
}

export function Filters({
  categories,
  accounts,
  colorOf,
}: {
  categories: Category[];
  accounts: Account[];
  colorOf: (category: Category) => string;
}) {
  const { params, set, clear } = useFilterParams();
  const active = FILTER_KEYS.some((key) => key !== "currency" && params.get(key));
  return (
    <div role="search" aria-label="Filter transactions" className="flex flex-wrap items-center gap-2">
      <div className="relative min-w-56 flex-1">
        <Search
          aria-hidden="true"
          className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-muted-foreground"
        />
        <input
          aria-label="Search transactions"
          placeholder="Search transactions"
          value={params.get("q") ?? ""}
          onChange={(event) => set("q", [event.target.value])}
          className="field pl-9"
        />
      </div>
      <Checklist
        label="Categories"
        name="category_ids"
        options={categories.map((c) => ({ id: c.id, label: c.name, color: colorOf(c) }))}
      />
      <Checklist
        label="Accounts"
        name="account_ids"
        options={accounts.map((a) => ({ id: a.id, label: `${a.bank_name} ${a.name}` }))}
      />
      <input
        aria-label="Amount at least"
        placeholder="Min amount"
        value={params.get("amount_min") ?? ""}
        onChange={(event) => set("amount_min", [event.target.value])}
        className="field w-32"
      />
      <input
        aria-label="Amount at most"
        placeholder="Max amount"
        value={params.get("amount_max") ?? ""}
        onChange={(event) => set("amount_max", [event.target.value])}
        className="field w-32"
      />
      {active && (
        <button type="button" onClick={clear} className="button-quiet">
          <X aria-hidden="true" className="h-4 w-4" />
          Clear
        </button>
      )}
    </div>
  );
}
