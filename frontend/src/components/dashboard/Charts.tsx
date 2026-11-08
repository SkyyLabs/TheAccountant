import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { categoryColor } from "../../lib/colors";
import { formatMoney, formatMoneyCompact } from "../../lib/format";
import type { Currency, Summary } from "../../types/api";

type Props = { currency: Currency; summary: Summary };

/** Money out by category: a donut with a legend that doubles as the accessible table. */
export function SpendingByCategory({ currency, summary }: Props) {
  const rows = summary.by_category
    .filter((row) => row.currency === currency && row.money_out_minor > 0)
    .map((row) => ({
      ...row,
      label: row.category_name ?? "Not categorized yet",
      color: categoryColor(row.category_id, row.category_name),
    }));
  if (rows.length === 0) {
    return <p className="py-16 text-center text-sm text-muted-foreground">No spending in this view.</p>;
  }
  return (
    <div className="grid items-center gap-6 sm:grid-cols-[220px_1fr]">
      <div aria-hidden="true" className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={rows}
              dataKey="money_out_minor"
              nameKey="label"
              innerRadius="62%"
              outerRadius="100%"
              paddingAngle={2}
              stroke="none"
            >
              {rows.map((row) => (
                <Cell key={row.label} fill={row.color} />
              ))}
            </Pie>
            <Tooltip formatter={(value) => formatMoney(Number(value), currency)} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <table className="w-full text-sm">
        <caption className="sr-only">{currency} spending by category</caption>
        <tbody>
          {rows.map((row) => (
            <tr key={row.label}>
              <th scope="row" className="py-1.5 text-left font-normal">
                <span className="flex items-center gap-2">
                  <span aria-hidden="true" className="h-2.5 w-2.5 rounded-full" style={{ background: row.color }} />
                  {row.label}
                </span>
              </th>
              <td className="py-1.5 text-right font-medium tabular-nums">
                {formatMoney(row.money_out_minor, currency)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Money in and out per month, with the same figures as a table for screen readers. */
export function MonthlyTrend({ currency, summary }: Props) {
  const months = summary.by_month.filter((row) => row.currency === currency);
  return (
    <figure>
      <div aria-hidden="true" className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={months} barGap={4}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="var(--border)" />
            <XAxis dataKey="month" fontSize={12} tickLine={false} axisLine={false} />
            <YAxis
              tickFormatter={(value: number) => formatMoneyCompact(value, currency)}
              fontSize={12}
              width={64}
              tickLine={false}
              axisLine={false}
            />
            <Tooltip formatter={(value) => formatMoney(Number(value), currency)} />
            <Legend iconType="circle" />
            <Bar dataKey="money_out_minor" name="Spent" fill="var(--primary)" radius={[6, 6, 0, 0]} />
            <Bar dataKey="money_in_minor" name="Received" fill="var(--success)" radius={[6, 6, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <table className="sr-only">
        <caption>{currency} money in and out by month</caption>
        <thead>
          <tr>
            <th scope="col">Month</th>
            <th scope="col">Spent</th>
            <th scope="col">Received</th>
          </tr>
        </thead>
        <tbody>
          {months.map((row) => (
            <tr key={row.month}>
              <th scope="row">{row.month}</th>
              <td>{formatMoney(row.money_out_minor, currency)}</td>
              <td>{formatMoney(row.money_in_minor, currency)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </figure>
  );
}
