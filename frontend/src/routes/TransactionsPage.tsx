import { useEffect, useState } from "react";

import { api } from "../lib/api";
import { formatMoney } from "../lib/format";
import type { Transaction } from "../types/api";

export function TransactionsPage() {
  const [transactions, setTransactions] = useState<Transaction[] | null>(null);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    api
      .listTransactions()
      .then(setTransactions)
      .catch(() => setLoadError(true));
  }, []);

  return (
    <section>
      <h1 className="text-2xl font-semibold">Transactions</h1>
      <p className="mt-2 max-w-prose text-slate-600 dark:text-slate-400">
        Every imported transaction, newest first. Filters and categories come next.
      </p>
      {loadError && (
        <p role="alert" className="mt-4 text-sm text-red-700 dark:text-red-400">
          Could not load transactions.
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
