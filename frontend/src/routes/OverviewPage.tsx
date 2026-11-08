import { useEffect, useState } from "react";
import { useSearchParams } from "react-router";

import { CurrencyOverview } from "../components/overview/CurrencyOverview";
import { Filters, filterQuery } from "../components/transactions/Filters";
import { api } from "../lib/api";
import type { Account, Category, Summary } from "../types/api";

export function OverviewPage() {
  const [params, setParams] = useSearchParams();
  // Spending view by default: transfers and card payments would count purchases twice.
  const spendingOnly = params.get("spending_only") !== "false";
  const query = new URLSearchParams(filterQuery(params));
  query.set("spending_only", String(spendingOnly));
  const filters = query.toString();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    api
      .summary(filters)
      .then(setSummary)
      .catch(() => setLoadError(true));
  }, [filters]);

  useEffect(() => {
    Promise.all([api.listCategories(), api.listAccounts()])
      .then(([loadedCategories, loadedAccounts]) => {
        setCategories(loadedCategories);
        setAccounts(loadedAccounts);
      })
      .catch(() => setLoadError(true));
  }, []);

  const excludedNames = categories.filter((c) => c.excluded_from_spending).map((c) => c.name);

  return (
    <section>
      <h1 className="text-2xl font-semibold">Overview</h1>
      <Filters categories={categories} accounts={accounts} />
      <label className="mt-3 flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={spendingOnly}
          onChange={(event) =>
            setParams(
              (current) => {
                const next = new URLSearchParams(current);
                if (event.target.checked) next.delete("spending_only");
                else next.set("spending_only", "false");
                return next;
              },
              { replace: true },
            )
          }
        />
        Leave out {excludedNames.length > 0 ? excludedNames.join(" and ") : "transfers"} (money
        moving between your own accounts)
      </label>
      {loadError && (
        <p role="alert" className="mt-4 text-sm text-red-700 dark:text-red-400">
          Could not load the overview.
        </p>
      )}
      {summary === null && !loadError && <p className="mt-4 text-sm">Loading…</p>}
      {summary?.totals.length === 0 && (
        <p className="mt-4 text-sm text-slate-600 dark:text-slate-400">
          Nothing to show yet. Upload a statement in the Statements tab, or widen the filters.
        </p>
      )}
      {summary?.totals.map((total) => (
        <CurrencyOverview key={total.currency} currency={total.currency} summary={summary} />
      ))}
    </section>
  );
}
