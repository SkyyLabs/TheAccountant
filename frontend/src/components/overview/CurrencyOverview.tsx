import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatMoney, formatMoneyCompact } from "../../lib/format";
import type { Currency, Summary } from "../../types/api";

const MONEY_OUT = "#2563eb";
const MONEY_IN = "#059669";
const TOP_CATEGORIES = 10;

const tableClass = "mt-2 w-full text-sm";

/** One currency's figures; currencies are never combined. */
export function CurrencyOverview({ currency, summary }: { currency: Currency; summary: Summary }) {
  const totals = summary.totals.find((row) => row.currency === currency);
  const months = summary.by_month.filter((row) => row.currency === currency);
  const categories = summary.by_category
    .filter((row) => row.currency === currency && row.money_out_minor > 0)
    .slice(0, TOP_CATEGORIES)
    .map((row) => ({ ...row, label: row.category_name ?? "Not categorized yet" }));
  const money = (value: unknown) => formatMoney(Number(value), currency);
  const axis = (value: number) => formatMoneyCompact(value, currency);

  return (
    <section aria-labelledby={`overview-${currency}`} className="mt-6">
      <h2 id={`overview-${currency}`} className="text-lg font-semibold">
        {currency}
      </h2>
      {totals && (
        <dl className="mt-2 flex flex-wrap gap-x-8 gap-y-1 text-sm">
          <div>
            <dt className="text-slate-500">Money out</dt>
            <dd className="text-xl font-semibold tabular-nums">{money(totals.money_out_minor)}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Money in</dt>
            <dd className="text-xl font-semibold tabular-nums">{money(totals.money_in_minor)}</dd>
          </div>
          <div>
            <dt className="text-slate-500">Transactions</dt>
            <dd className="text-xl font-semibold tabular-nums">{totals.transaction_count}</dd>
          </div>
        </dl>
      )}

      <div className="mt-4 grid gap-6 lg:grid-cols-2">
        <figure>
          <figcaption className="text-sm font-medium">By month</figcaption>
          <div aria-hidden="true" className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={months}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="month" fontSize={12} />
                <YAxis tickFormatter={axis} fontSize={12} width={64} />
                <Tooltip formatter={money} />
                <Legend />
                <Bar dataKey="money_out_minor" name="Money out" fill={MONEY_OUT} />
                <Bar dataKey="money_in_minor" name="Money in" fill={MONEY_IN} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <details>
            <summary className="cursor-pointer text-sm text-blue-700 dark:text-blue-400">
              Show by month as a table
            </summary>
            <table className={tableClass}>
              <caption className="sr-only">{currency} money in and out by month</caption>
              <thead>
                <tr className="text-left text-slate-500">
                  <th scope="col" className="font-medium">Month</th>
                  <th scope="col" className="text-right font-medium">Money out</th>
                  <th scope="col" className="text-right font-medium">Money in</th>
                </tr>
              </thead>
              <tbody>
                {months.map((row) => (
                  <tr key={row.month}>
                    <th scope="row" className="text-left font-normal">{row.month}</th>
                    <td className="text-right tabular-nums">{money(row.money_out_minor)}</td>
                    <td className="text-right tabular-nums">{money(row.money_in_minor)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </figure>

        <figure>
          <figcaption className="text-sm font-medium">Money out by category</figcaption>
          <div aria-hidden="true" className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={categories} layout="vertical" margin={{ left: 24 }}>
                <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                <XAxis type="number" tickFormatter={axis} fontSize={12} />
                <YAxis type="category" dataKey="label" width={120} fontSize={12} />
                <Tooltip formatter={money} />
                <Bar dataKey="money_out_minor" name="Money out" fill={MONEY_OUT} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <details>
            <summary className="cursor-pointer text-sm text-blue-700 dark:text-blue-400">
              Show by category as a table
            </summary>
            <table className={tableClass}>
              <caption className="sr-only">{currency} money out by category</caption>
              <thead>
                <tr className="text-left text-slate-500">
                  <th scope="col" className="font-medium">Category</th>
                  <th scope="col" className="text-right font-medium">Money out</th>
                </tr>
              </thead>
              <tbody>
                {categories.map((row) => (
                  <tr key={row.label}>
                    <th scope="row" className="text-left font-normal">{row.label}</th>
                    <td className="text-right tabular-nums">{money(row.money_out_minor)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </figure>
      </div>
    </section>
  );
}
