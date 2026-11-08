import { useCallback, useEffect, useState } from "react";

import { UploadPanel } from "../components/statements/UploadPanel";
import { api } from "../lib/api";
import type { ReconciliationStatus, Statement } from "../types/api";

const STATUS: Record<ReconciliationStatus, { label: string; hint: string; className: string }> = {
  reconciled: {
    label: "Reconciled",
    hint: "Balances match the transactions",
    className: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  },
  unreconciled: {
    label: "Unreconciled",
    hint: "Balances do not match the transactions",
    className: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
  },
  unverifiable: {
    label: "Unverifiable",
    hint: "The file has no balances to check totals against",
    className: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  },
};

export function StatementsPage() {
  const [statements, setStatements] = useState<Statement[] | null>(null);
  const [loadError, setLoadError] = useState(false);

  const load = useCallback(() => {
    api
      .listStatements()
      .then((loaded) => {
        setStatements(loaded);
        setLoadError(false);
      })
      .catch(() => setLoadError(true));
  }, []);

  useEffect(load, [load]);

  return (
    <section>
      <h1 className="text-2xl font-semibold">Statements</h1>
      <p className="mt-2 max-w-prose text-slate-600 dark:text-slate-400">
        Each file is imported once; re-uploads and overlapping transactions are detected.
      </p>

      <UploadPanel onImported={load} />

      <h2 className="mt-6 text-lg font-semibold">Imported statements</h2>
      {loadError && (
        <p role="alert" className="mt-2 text-sm text-red-700 dark:text-red-400">
          Could not load statements.
        </p>
      )}
      {statements === null && !loadError && <p className="mt-2 text-sm">Loading…</p>}
      {statements?.length === 0 && (
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">No statements yet.</p>
      )}
      {statements && statements.length > 0 && (
        <div className="mt-2 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500">
                <th scope="col" className="py-2 pr-3 font-medium">File</th>
                <th scope="col" className="py-2 pr-3 font-medium">Account</th>
                <th scope="col" className="py-2 pr-3 font-medium">Period</th>
                <th scope="col" className="py-2 pr-3 font-medium">Transactions</th>
                <th scope="col" className="py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {statements.map((statement) => {
                const status = STATUS[statement.reconciliation_status];
                return (
                  <tr key={statement.id} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="py-2 pr-3">{statement.filename}</td>
                    <td className="py-2 pr-3">
                      {statement.bank_name} · {statement.account_name}
                    </td>
                    <td className="py-2 pr-3 whitespace-nowrap">
                      {statement.period_start} to {statement.period_end}
                    </td>
                    <td className="py-2 pr-3">
                      {statement.imported_count} new
                      {statement.duplicate_count > 0 && `, ${statement.duplicate_count} duplicates skipped`}
                    </td>
                    <td className="py-2">
                      <span className={`rounded px-2 py-0.5 text-xs font-medium ${status.className}`}>
                        {status.label}
                      </span>
                      <span className="ml-2 text-xs text-slate-500">{status.hint}</span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
