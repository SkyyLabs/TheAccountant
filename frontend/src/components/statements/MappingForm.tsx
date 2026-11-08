import { useState } from "react";

import { ApiError, api } from "../../lib/api";
import { formatMoney } from "../../lib/format";
import type {
  AmountMode,
  CsvMapping,
  MappingRequiredDetails,
  Statement,
  StatementPreview,
} from "../../types/api";

type Draft = {
  header_row: number;
  date_column: string;
  description_column: string;
  amount_mode: AmountMode;
  amount_column: string;
  debit_column: string;
  credit_column: string;
  date_format: string;
};

const AMOUNT_MODES: { value: AmountMode; label: string }[] = [
  { value: "signed", label: "One amount column, negative is money out" },
  { value: "inverted", label: "One amount column, positive is money out (many card exports)" },
  { value: "debit_credit", label: "Separate debit and credit columns" },
];

const SAMPLE_LINES = 8;

function toMapping(draft: Draft): CsvMapping | null {
  const separate = draft.amount_mode === "debit_credit";
  const complete =
    draft.date_column &&
    draft.description_column &&
    draft.date_format &&
    (separate ? draft.debit_column && draft.credit_column : draft.amount_column);
  if (!complete) return null;
  return {
    ...draft,
    amount_column: separate ? null : draft.amount_column,
    debit_column: separate ? draft.debit_column : null,
    credit_column: separate ? draft.credit_column : null,
  };
}

type Props = {
  file: File;
  accountId: number;
  details: MappingRequiredDetails;
  onImported: (statement: Statement) => void;
  onCancel: () => void;
};

export function MappingForm({ file, accountId, details, onImported, onCancel }: Props) {
  const suggestion = details.suggested_mapping;
  const [draft, setDraft] = useState<Draft>({
    header_row: suggestion.header_row ?? 0,
    date_column: suggestion.date_column ?? "",
    description_column: suggestion.description_column ?? "",
    amount_mode: suggestion.amount_mode ?? "signed",
    amount_column: suggestion.amount_column ?? "",
    debit_column: suggestion.debit_column ?? "",
    credit_column: suggestion.credit_column ?? "",
    date_format: suggestion.date_format ?? "",
  });
  const [preview, setPreview] = useState<StatementPreview | null>(null);
  const [previewedMapping, setPreviewedMapping] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const headers = (details.rows[draft.header_row] ?? []).filter((cell) => cell);
  const mapping = toMapping(draft);
  // Import only what the user has seen previewed.
  const canImport = mapping !== null && previewedMapping === JSON.stringify(mapping);

  function update(changes: Partial<Draft>) {
    setDraft((current) => ({ ...current, ...changes }));
    setError(null);
  }

  async function runPreview() {
    if (!mapping) return;
    setBusy(true);
    setError(null);
    try {
      setPreview(await api.previewStatement(file, accountId, mapping));
      setPreviewedMapping(JSON.stringify(mapping));
    } catch (caught) {
      setPreview(null);
      setPreviewedMapping(null);
      setError(caught instanceof ApiError ? caught.message : "Preview failed");
    } finally {
      setBusy(false);
    }
  }

  async function runImport() {
    if (!mapping) return;
    setBusy(true);
    setError(null);
    try {
      onImported(await api.uploadStatement(file, accountId, mapping));
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Import failed");
    } finally {
      setBusy(false);
    }
  }

  function columnSelect(label: string, field: keyof Draft) {
    const id = `mapping-${field}`;
    return (
      <div>
        <label htmlFor={id} className="block text-sm font-medium">
          {label}
        </label>
        <select
          id={id}
          value={String(draft[field])}
          onChange={(event) => update({ [field]: event.target.value })}
          className="mt-1 w-full rounded border border-slate-300 bg-white px-2 py-1 dark:border-slate-700 dark:bg-slate-900"
        >
          <option value="">Choose a column</option>
          {headers.map((header) => (
            <option key={header} value={header}>
              {header}
            </option>
          ))}
        </select>
      </div>
    );
  }

  return (
    <section
      aria-labelledby="mapping-heading"
      className="mt-4 rounded border border-slate-200 p-4 dark:border-slate-800"
    >
      <h3 id="mapping-heading" className="text-lg font-semibold">
        Map the columns of {file.name}
      </h3>
      <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
        First upload for this account. Check the suggestion, preview, then import. The mapping is
        remembered for the next file from this account.
      </p>

      <div className="mt-3 overflow-x-auto">
        <table className="text-xs">
          <caption className="sr-only">First lines of the file</caption>
          <tbody>
            {details.rows.slice(0, SAMPLE_LINES).map((row, index) => (
              <tr
                key={index}
                className={index === draft.header_row ? "bg-blue-50 font-semibold dark:bg-blue-950" : ""}
              >
                <th scope="row" className="pr-2 text-right font-normal text-slate-500">
                  {index + 1}
                </th>
                {row.map((cell, cellIndex) => (
                  <td key={cellIndex} className="whitespace-nowrap px-2 py-0.5">
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <div>
          <label htmlFor="mapping-header-row" className="block text-sm font-medium">
            Header line
          </label>
          <input
            id="mapping-header-row"
            type="number"
            min={1}
            max={details.rows.length}
            value={draft.header_row + 1}
            onChange={(event) => update({ header_row: Math.max(0, Number(event.target.value) - 1) })}
            className="mt-1 w-full rounded border border-slate-300 bg-white px-2 py-1 dark:border-slate-700 dark:bg-slate-900"
          />
        </div>
        <div>
          <label htmlFor="mapping-date-format" className="block text-sm font-medium">
            Date format
          </label>
          <select
            id="mapping-date-format"
            value={draft.date_format}
            onChange={(event) => update({ date_format: event.target.value })}
            className="mt-1 w-full rounded border border-slate-300 bg-white px-2 py-1 dark:border-slate-700 dark:bg-slate-900"
          >
            {details.date_formats.map((format) => (
              <option key={format} value={format}>
                {format}
              </option>
            ))}
          </select>
        </div>
        {columnSelect("Date column", "date_column")}
        {columnSelect("Description column", "description_column")}
      </div>

      <fieldset className="mt-4">
        <legend className="text-sm font-medium">Amounts</legend>
        {AMOUNT_MODES.map((mode) => (
          <label key={mode.value} className="mt-1 flex items-center gap-2 text-sm">
            <input
              type="radio"
              name="amount_mode"
              value={mode.value}
              checked={draft.amount_mode === mode.value}
              onChange={() => update({ amount_mode: mode.value })}
            />
            {mode.label}
          </label>
        ))}
      </fieldset>

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        {draft.amount_mode === "debit_credit" ? (
          <>
            {columnSelect("Debit column (money out)", "debit_column")}
            {columnSelect("Credit column (money in)", "credit_column")}
          </>
        ) : (
          columnSelect("Amount column", "amount_column")
        )}
      </div>

      {error && (
        <p role="alert" className="mt-3 text-sm text-red-700 dark:text-red-400">
          {error}
        </p>
      )}

      <div className="mt-4 flex gap-2">
        <button
          type="button"
          onClick={runPreview}
          disabled={!mapping || busy}
          className="rounded border border-slate-300 px-3 py-1.5 text-sm font-medium disabled:opacity-50 dark:border-slate-700"
        >
          Preview
        </button>
        <button
          type="button"
          onClick={runImport}
          disabled={!canImport || busy}
          className="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
        >
          Import
        </button>
        <button type="button" onClick={onCancel} className="px-3 py-1.5 text-sm">
          Cancel
        </button>
      </div>

      {preview && (
        <div className="mt-4">
          <p className="text-sm">
            {preview.row_count} transactions found
            {preview.skipped_row_count > 0 &&
              `, ${preview.skipped_row_count} lines without a date or amount skipped`}
            . Check that money out shows a minus sign.
          </p>
          <table className="mt-2 w-full text-sm">
            <caption className="sr-only">Preview of parsed transactions</caption>
            <thead>
              <tr className="text-left text-slate-500">
                <th scope="col" className="py-1 pr-3 font-medium">Date</th>
                <th scope="col" className="py-1 pr-3 font-medium">Description</th>
                <th scope="col" className="py-1 text-right font-medium">Amount</th>
              </tr>
            </thead>
            <tbody>
              {preview.transactions.map((transaction, index) => (
                <tr key={index} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="py-1 pr-3 whitespace-nowrap">{transaction.date}</td>
                  <td className="py-1 pr-3">{transaction.description}</td>
                  <td className="py-1 text-right tabular-nums">
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
