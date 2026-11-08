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
};

/** Sent with a 422 csv_mapping_required: what the user needs to map the columns. */
export type MappingRequiredDetails = {
  rows: string[][];
  suggested_mapping: { [K in keyof CsvMapping]: CsvMapping[K] | null };
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
