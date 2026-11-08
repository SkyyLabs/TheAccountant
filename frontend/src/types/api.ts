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
  bank_name: string;
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
  categorization_status: "pending" | "done" | "llm_unavailable";
  uploaded_at: string;
};

export type Import = {
  id: number;
  filename: string;
  status: "processing" | "done" | "failed";
  /** Parts of the statement the local model has read so far. */
  progress_done: number;
  progress_total: number;
  /** Plain-language reason when the import failed. */
  error: string | null;
  /** Transactions the model returned without a usable date or amount. */
  rejected_count: number;
  uploaded_at: string;
  /** One per account found in the file. */
  statements: Statement[];
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
  category_id: number | null;
  category_name: string | null;
  category_source: CategorySource | null;
  category_needs_review: boolean;
};

export type CategorySource = "rule" | "cache" | "llm" | "user";
export type Region = "US" | "IN" | "both";

export type Category = {
  id: number;
  name: string;
  region: Region;
  is_default: boolean;
  /** Transfers and card payments: left out of spending totals so nothing counts twice. */
  excluded_from_spending: boolean;
};

export type MatchType = "exact" | "contains";

export type Rule = {
  id: number;
  match_type: MatchType;
  pattern: string;
  amount_min_minor: number | null;
  amount_max_minor: number | null;
  category_id: number;
  category_name: string;
  priority: number;
};

export type RuleSuggestion = { match_type: MatchType; pattern: string; category_id: number };

export type RuleInput = RuleSuggestion & { priority?: number };

export type TransactionCorrected = {
  transaction: Transaction;
  suggested_rule: RuleSuggestion | null;
};

export type RuleCreated = { rule: Rule; applied_count: number };

export type CurrencyTotals = {
  currency: Currency;
  money_in_minor: number;
  /** A positive total of money out. */
  money_out_minor: number;
  transaction_count: number;
};

export type Summary = {
  totals: CurrencyTotals[];
  by_month: (CurrencyTotals & { month: string })[];
  by_category: (CurrencyTotals & { category_id: number | null; category_name: string | null })[];
};
