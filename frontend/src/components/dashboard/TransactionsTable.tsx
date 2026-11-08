import { AlertTriangle } from "lucide-react";
import { useState } from "react";

import { ApiError, api } from "../../lib/api";
import { categoryColor } from "../../lib/colors";
import { formatMoney } from "../../lib/format";
import type { Category, RuleSuggestion, Transaction } from "../../types/api";

type Offer = RuleSuggestion & { categoryName: string };

export function TransactionsTable({
  transactions,
  categories,
  onChanged,
}: {
  transactions: Transaction[];
  categories: Category[];
  onChanged: () => void;
}) {
  const [offer, setOffer] = useState<Offer | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function changeCategory(transaction: Transaction, categoryId: number) {
    setMessage(null);
    try {
      const result = await api.setTransactionCategory(transaction.id, categoryId);
      const suggestion = result.suggested_rule;
      setOffer(suggestion && { ...suggestion, categoryName: result.transaction.category_name ?? "" });
      onChanged();
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
      onChanged();
    } catch (caught) {
      setMessage(caught instanceof ApiError ? caught.message : "Could not create the rule");
    }
  }

  return (
    <div>
      {offer && (
        <div
          role="status"
          className="mb-4 flex flex-wrap items-center gap-3 rounded-xl bg-accent px-4 py-3 text-sm text-accent-foreground"
        >
          <span className="flex-1">
            Always put “{offer.pattern}” in {offer.categoryName}?
          </span>
          <button type="button" onClick={acceptOffer} className="button-primary">
            Create rule
          </button>
          <button type="button" onClick={() => setOffer(null)} className="button-quiet">
            No thanks
          </button>
        </div>
      )}
      {message && (
        <p role="status" className="mb-4 text-sm text-muted-foreground">
          {message}
        </p>
      )}
      {transactions.length === 0 ? (
        <p className="py-12 text-center text-sm text-muted-foreground">
          No transactions match these filters.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs tracking-wide text-muted-foreground uppercase">
                <th scope="col" className="py-3 pr-4 font-medium">Date</th>
                <th scope="col" className="py-3 pr-4 font-medium">Description</th>
                <th scope="col" className="py-3 pr-4 font-medium">Category</th>
                <th scope="col" className="py-3 pr-4 font-medium">Account</th>
                <th scope="col" className="py-3 text-right font-medium">Amount</th>
              </tr>
            </thead>
            <tbody>
              {transactions.map((transaction) => {
                const color = categoryColor(transaction.category_id, transaction.category_name);
                return (
                  <tr key={transaction.id} className="border-b last:border-0 hover:bg-muted/50">
                    <td className="py-3 pr-4 whitespace-nowrap text-muted-foreground tabular-nums">
                      {transaction.date}
                    </td>
                    <td className="py-3 pr-4">
                      <span className="font-medium">{transaction.description}</span>
                      {transaction.needs_review && (
                        <span
                          title="The amount or date did not match the statement text exactly"
                          className="ml-2 inline-flex items-center gap-1 rounded-full bg-warning/15 px-2 py-0.5 text-xs font-medium text-warning"
                        >
                          <AlertTriangle aria-hidden="true" className="h-3 w-3" />
                          Check this
                        </span>
                      )}
                    </td>
                    <td className="py-3 pr-4">
                      <span className="flex items-center gap-2">
                        <span aria-hidden="true" className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: color }} />
                        <select
                          aria-label={`Category for ${transaction.description}`}
                          value={transaction.category_id ?? ""}
                          onChange={(event) => changeCategory(transaction, Number(event.target.value))}
                          className="rounded-md bg-transparent py-1 pr-1 text-sm hover:bg-muted focus:ring-2 focus:ring-primary/40 focus:outline-none"
                        >
                          {transaction.category_id === null && <option value="">Sorting…</option>}
                          {categories.map((category) => (
                            <option key={category.id} value={category.id}>
                              {category.name}
                            </option>
                          ))}
                        </select>
                        {transaction.category_needs_review && (
                          <span className="rounded-full bg-warning/15 px-2 py-0.5 text-xs font-medium text-warning">
                            Unsure
                          </span>
                        )}
                      </span>
                    </td>
                    <td className="py-3 pr-4 whitespace-nowrap text-muted-foreground">
                      {transaction.bank_name} {transaction.account_name}
                    </td>
                    <td
                      className={`py-3 text-right font-medium whitespace-nowrap tabular-nums ${transaction.amount_minor > 0 ? "text-success" : ""}`}
                    >
                      {formatMoney(transaction.amount_minor, transaction.currency)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
