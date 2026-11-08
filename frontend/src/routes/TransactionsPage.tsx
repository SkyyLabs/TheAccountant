import { useCallback, useEffect, useState } from "react";

import { ApiError, api } from "../lib/api";
import { formatMoney } from "../lib/format";
import type { Category, RuleSuggestion, Transaction } from "../types/api";

// Categorizing runs in the background after an upload; refresh while some are pending.
const REFRESH_MS = 3000;
const MAX_REFRESHES = 20;

type Offer = RuleSuggestion & { categoryName: string };

export function TransactionsPage() {
  const [transactions, setTransactions] = useState<Transaction[] | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [loadError, setLoadError] = useState(false);
  const [refreshes, setRefreshes] = useState(0);
  const [offer, setOffer] = useState<Offer | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .listTransactions()
      .then(setTransactions)
      .catch(() => setLoadError(true));
  }, []);

  useEffect(() => {
    load();
    api
      .listCategories()
      .then(setCategories)
      .catch(() => setLoadError(true));
  }, [load]);

  const pendingCount = transactions?.filter((t) => t.category_id === null).length ?? 0;
  useEffect(() => {
    if (pendingCount === 0 || refreshes >= MAX_REFRESHES) return;
    const timer = setTimeout(() => {
      setRefreshes((count) => count + 1);
      load();
    }, REFRESH_MS);
    return () => clearTimeout(timer);
  }, [pendingCount, refreshes, load]);

  async function changeCategory(transaction: Transaction, categoryId: number) {
    setMessage(null);
    try {
      const result = await api.setTransactionCategory(transaction.id, categoryId);
      setTransactions((current) =>
        (current ?? []).map((t) => (t.id === transaction.id ? result.transaction : t)),
      );
      const suggestion = result.suggested_rule;
      setOffer(
        suggestion && {
          ...suggestion,
          categoryName: result.transaction.category_name ?? "",
        },
      );
    } catch (caught) {
      setMessage(caught instanceof ApiError ? caught.message : "Could not change the category");
    }
  }

  async function acceptOffer() {
    if (!offer) return;
    try {
      const { applied_count } = await api.createRule({
        match_type: offer.match_type,
        pattern: offer.pattern,
        category_id: offer.category_id,
      });
      setOffer(null);
      setMessage(
        `Rule created. ${applied_count} other transaction${applied_count === 1 ? "" : "s"} moved to ${offer.categoryName}.`,
      );
      load();
    } catch (caught) {
      setMessage(caught instanceof ApiError ? caught.message : "Could not create the rule");
    }
  }

  async function categorizeNow() {
    setMessage(null);
    try {
      await api.categorizePending();
      setRefreshes(0);
      setMessage("Categorizing with the local model…");
      load();
    } catch {
      setMessage("Could not start categorizing");
    }
  }

  return (
    <section>
      <h1 className="text-2xl font-semibold">Transactions</h1>
      <p className="mt-2 max-w-prose text-slate-600 dark:text-slate-400">
        Every imported transaction, newest first. Change a category to correct it; filters come
        next.
      </p>
      {loadError && (
        <p role="alert" className="mt-4 text-sm text-red-700 dark:text-red-400">
          Could not load transactions.
        </p>
      )}
      {pendingCount > 0 && (
        <div className="mt-4 flex flex-wrap items-center gap-3 text-sm">
          <span>
            {pendingCount} not categorized yet. If Ollama was not running, start it and retry.
          </span>
          <button
            type="button"
            onClick={categorizeNow}
            className="rounded border border-slate-300 px-3 py-1 font-medium dark:border-slate-700"
          >
            Categorize now
          </button>
        </div>
      )}
      {offer && (
        <div
          role="status"
          className="mt-4 flex flex-wrap items-center gap-3 rounded border border-blue-200 bg-blue-50 p-3 text-sm dark:border-blue-900 dark:bg-blue-950"
        >
          <span>
            Always categorize “{offer.pattern}” as {offer.categoryName}?
          </span>
          <button
            type="button"
            onClick={acceptOffer}
            className="rounded bg-blue-600 px-3 py-1 font-medium text-white"
          >
            Create rule
          </button>
          <button type="button" onClick={() => setOffer(null)} className="px-2 py-1">
            No thanks
          </button>
        </div>
      )}
      {message && (
        <p role="status" className="mt-3 text-sm">
          {message}
        </p>
      )}
      {transactions === null && !loadError && <p className="mt-4 text-sm">Loading…</p>}
      {transactions?.length === 0 && (
        <p className="mt-4 text-sm text-slate-600 dark:text-slate-400">
          No transactions yet. Upload a statement in the Statements tab.
        </p>
      )}
      {transactions && transactions.length > 0 && (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500">
                <th scope="col" className="py-2 pr-3 font-medium">Date</th>
                <th scope="col" className="py-2 pr-3 font-medium">Description</th>
                <th scope="col" className="py-2 pr-3 font-medium">Category</th>
                <th scope="col" className="py-2 pr-3 font-medium">Account</th>
                <th scope="col" className="py-2 text-right font-medium">Amount</th>
              </tr>
            </thead>
            <tbody>
              {transactions.map((transaction) => (
                <tr key={transaction.id} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="py-2 pr-3 whitespace-nowrap">{transaction.date}</td>
                  <td className="py-2 pr-3">
                    {transaction.description}
                    {transaction.needs_review && (
                      <span className="ml-2 rounded bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-950 dark:text-amber-300">
                        Needs review
                      </span>
                    )}
                  </td>
                  <td className="py-2 pr-3">
                    <select
                      aria-label={`Category for ${transaction.description}`}
                      value={transaction.category_id ?? ""}
                      onChange={(event) => changeCategory(transaction, Number(event.target.value))}
                      className="rounded border border-slate-300 bg-white px-1 py-0.5 dark:border-slate-700 dark:bg-slate-900"
                    >
                      {transaction.category_id === null && <option value="">Not categorized</option>}
                      {categories.map((category) => (
                        <option key={category.id} value={category.id}>
                          {category.name}
                        </option>
                      ))}
                    </select>
                    {transaction.category_needs_review && (
                      <span className="ml-2 rounded bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-950 dark:text-amber-300">
                        Check category
                      </span>
                    )}
                  </td>
                  <td className="py-2 pr-3">
                    {transaction.bank_name} · {transaction.account_name}
                  </td>
                  <td
                    className={`py-2 text-right whitespace-nowrap tabular-nums ${transaction.amount_minor < 0 ? "" : "text-emerald-700 dark:text-emerald-400"}`}
                  >
                    {formatMoney(transaction.amount_minor, transaction.currency)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
