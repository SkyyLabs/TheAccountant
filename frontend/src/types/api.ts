export type Health = {
  status: "ok";
  version: string;
  schema_version: number;
};

export type ApiErrorBody = {
  error: { code: string; message: string; details?: unknown };
};

export type Country = "US" | "IN";
export type Currency = "USD" | "INR";
export type AccountType = "bank" | "credit_card";

export type Bank = {
  id: string;
  name: string;
  country: Country;
  currency: Currency;
  default_date_format: string;
  is_default: boolean;
};

export type Account = {
  id: number;
  bank_id: string;
  type: AccountType;
  name: string;
};

export type ReconciliationStatus = "reconciled" | "unreconciled" | "unverifiable";

export type Statement = {
  id: number;
  account_id: number;
  bank_id: string;
  bank_name: string;
  account_name: string;
  filename: string;
  currency: Currency;
  period_start: string | null;
  period_end: string | null;
  reconciliation_status: ReconciliationStatus;
  opening_balance_minor: number | null;
  closing_balance_minor: number | null;
  /** Stated closing balance minus the closing balance the transactions imply. */
  reconciliation_difference_minor: number | null;
  row_count: number;
  imported_count: number;
  duplicate_count: number;
  uploaded_at: string;
};

export type AmountMode = "signed" | "inverted" | "debit_credit";

export type CsvMapping = {
  header_row: number;
  date_column: string;
  description_column: string;
  amount_mode: AmountMode;
  amount_column: string | null;
  debit_column: string | null;
  credit_column: string | null;
  date_format: string;
  opening_balance_label: string | null;
  closing_balance_label: string | null;
};

/** Sent with a 422 csv_mapping_required: what the user needs to map the columns. */
export type MappingRequiredDetails = {
  rows: string[][];
  suggested_mapping: { [K in keyof CsvMapping]: CsvMapping[K] | null };
  /** "llm": proposed by the local model and checked against the file; "heuristic": from header names. */
  suggestion_source: "llm" | "heuristic";
  date_formats: string[];
};

export type PreviewTransaction = {
  date: string;
  amount_minor: number;
  currency: Currency;
  description: string;
};

export type StatementPreview = {
  row_count: number;
  skipped_row_count: number;
  opening_balance_minor: number | null;
  closing_balance_minor: number | null;
  reconciliation_status: ReconciliationStatus;
  reconciliation_difference_minor: number | null;
  transactions: PreviewTransaction[];
};

export type Transaction = {
  id: number;
  statement_id: number;
  account_id: number;
  account_name: string;
  bank_id: string;
  bank_name: string;
  date: string;
  amount_minor: number;
  currency: Currency;
  description: string;
  needs_review: boolean;
};
