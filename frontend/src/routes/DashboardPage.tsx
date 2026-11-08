import { AlertTriangle, ArrowDownLeft, ArrowUpRight, ListChecks, Receipt, UploadCloud } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router";

import { MonthlyTrend, SpendingByCategory } from "../components/dashboard/Charts";
import { Filters, RangeSwitch, filterQuery, useFilterParams } from "../components/dashboard/Filters";
import { TransactionsTable } from "../components/dashboard/TransactionsTable";
import { api } from "../lib/api";
import { categoryColor } from "../lib/colors";
import { formatMoney } from "../lib/format";
import type { Account, Category, Currency, Statement, Summary, Transaction } from "../types/api";

const REFRESH_MS = 3000;

/** The backend queries for this view: one for the table, one for the spending figures. */
function queriesFor(params: URLSearchParams, currency: Currency | null) {
  const query = new URLSearchParams(filterQuery(params));
  if (currency) query.set("currency", currency);
  // Charts leave out transfers and card payments so nothing is counted twice.
  const spending = new URLSearchParams(query);
  spending.set("spending_only", "true");
  return { filters: query.toString(), spendingFilters: spending.toString() };
}

function Metric({
  label,
  value,
  helper,
  icon: Icon,
  tone = "",
}: {
  label: string;
  value: string;
  helper: string;
  icon: typeof Receipt;
  tone?: string;
}) {
  return (
    <div className="card p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm text-muted-foreground">{label}</p>
          <p className={`mt-2 text-3xl font-semibold tabular-nums ${tone}`}>{value}</p>
          <p className="mt-1 text-xs text-muted-foreground">{helper}</p>
        </div>
        <Icon aria-hidden="true" className="h-5 w-5 text-muted-foreground" />
      </div>
    </div>
  );
}

export function DashboardPage() {
  const { params, set } = useFilterParams();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [transactions, setTransactions] = useState<Transaction[]>([]);
  const [statements, setStatements] = useState<Statement[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loadError, setLoadError] = useState(false);
  const [reloads, setReloads] = useState(0);
  const reload = () => setReloads((count) => count + 1);

  // Charts and totals are per currency, never combined; the switch shows when there are two.
  const currencies = [...new Set((summary?.totals ?? []).map((t) => t.currency))];
  const currency = (params.get("currency") as Currency | null) ?? currencies[0] ?? null;
  const { filters, spendingFilters } = queriesFor(params, currency);

  useEffect(() => {
    Promise.all([
      api.summary(spendingFilters),
      api.listTransactions(filters),
      api.listStatements(),
    ])
      .then(([loadedSummary, loadedTransactions, loadedStatements]) => {
        setSummary(loadedSummary);
        setTransactions(loadedTransactions);
        setStatements(loadedStatements);
        setLoadError(false);
      })
      .catch(() => setLoadError(true));
  }, [filters, spendingFilters, reloads]);

  useEffect(() => {
    Promise.all([api.listCategories(), api.listAccounts()])
      .then(([loadedCategories, loadedAccounts]) => {
        setCategories(loadedCategories);
        setAccounts(loadedAccounts);
      })
      .catch(() => setLoadError(true));
  }, []);

  // Categorizing finishes in the background; refresh while some are still being sorted.
  const sorting = transactions.some((t) => t.category_id === null);
  useEffect(() => {
    if (!sorting) return;
    const timer = setTimeout(() => setReloads((count) => count + 1), REFRESH_MS);
    return () => clearTimeout(timer);
  }, [sorting, reloads]);

  const totals = summary?.totals.find((t) => t.currency === currency);
  const toCheck = transactions.filter((t) => t.needs_review).length;
  const unreconciled = statements.filter((s) => s.reconciliation_status === "unreconciled");
  const reviewOnly = params.get("review") === "1";
  const shown = reviewOnly ? transactions.filter((t) => t.needs_review) : transactions;

  if (summary && summary.totals.length === 0 && filterQuery(params) === "" && statements.length === 0) {
    return (
      <div className="card mx-auto max-w-xl animate-rise p-10 text-center">
        <UploadCloud aria-hidden="true" className="mx-auto h-10 w-10 text-primary" />
        <h1 className="mt-4 text-2xl font-semibold tracking-tight">Nothing here yet</h1>
        <p className="mt-2 text-muted-foreground">Upload a statement and the local AI will sort it out.</p>
        <Link to="/upload" className="button-primary mt-6">
          Upload statements
        </Link>
      </div>
    );
  }

  return (
    <div className="animate-rise space-y-6">
      <section className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="text-sm text-muted-foreground">Dashboard</p>
          <h1 className="mt-1 text-3xl font-semibold tracking-tight">Where your money went</h1>
          <p className="mt-2 max-w-2xl text-sm text-muted-foreground">
            Every account and card you uploaded, sorted into categories by the AI on this Mac.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {currencies.length > 1 && (
            <div role="group" aria-label="Currency" className="flex rounded-lg border bg-card p-1">
              {currencies.map((code) => (
                <button
                  key={code}
                  type="button"
                  aria-pressed={code === currency}
                  onClick={() => set("currency", [code])}
                  className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${
                    code === currency ? "bg-primary text-primary-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {code}
                </button>
              ))}
            </div>
          )}
          <RangeSwitch />
        </div>
      </section>

      {loadError && (
        <p role="alert" className="text-sm text-destructive">
          Could not load your data. Is the app server running?
        </p>
      )}

      {(toCheck > 0 || unreconciled.length > 0) && (
        <div role="status" className="flex flex-wrap items-center gap-3 rounded-xl bg-warning/10 px-4 py-3 text-sm">
          <AlertTriangle aria-hidden="true" className="h-4 w-4 text-warning" />
          <span className="flex-1">
            {toCheck > 0 && `${toCheck} transaction${toCheck === 1 ? "" : "s"} did not match the statement text exactly. `}
            {unreconciled.length > 0 &&
              `${unreconciled.length} statement${unreconciled.length === 1 ? "'s" : "s'"} totals do not add up to the printed balance.`}
          </span>
          {toCheck > 0 && (
            <button type="button" onClick={() => set("review", reviewOnly ? [] : ["1"])} className="button-quiet">
              {reviewOnly ? "Show all" : "Show them"}
            </button>
          )}
        </div>
      )}

      {currency && totals && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <Metric label="Spent" value={formatMoney(totals.money_out_minor, currency)} helper="Excluding transfers and card payments" icon={ArrowUpRight} />
          <Metric label="Received" value={formatMoney(totals.money_in_minor, currency)} helper="Salary, refunds and other income" icon={ArrowDownLeft} tone="text-success" />
          <Metric label="Transactions" value={String(totals.transaction_count)} helper={`${currency} in this view`} icon={Receipt} />
          <Metric label="To check" value={String(toCheck)} helper="Did not match the statement exactly" icon={ListChecks} tone={toCheck > 0 ? "text-warning" : ""} />
        </div>
      )}

      {currency && summary && (
        <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
          <section aria-labelledby="by-category" className="card p-6">
            <h2 id="by-category" className="font-medium">Spending by category</h2>
            <div className="mt-4">
              <SpendingByCategory currency={currency} summary={summary} />
            </div>
          </section>
          <section aria-labelledby="by-month" className="card p-6">
            <h2 id="by-month" className="font-medium">Month by month</h2>
            <div className="mt-4">
              <MonthlyTrend currency={currency} summary={summary} />
            </div>
          </section>
        </div>
      )}

      <section aria-labelledby="transactions" className="card p-6">
        <div className="mb-4 flex items-center justify-between gap-4">
          <h2 id="transactions" className="font-medium">Transactions</h2>
          <span className="text-sm text-muted-foreground">{shown.length} shown</span>
        </div>
        <Filters categories={categories} accounts={accounts} colorOf={(c) => categoryColor(c.id, c.name)} />
        <div className="mt-4">
          <TransactionsTable transactions={shown} categories={categories} onChanged={reload} />
        </div>
      </section>
    </div>
  );
}
