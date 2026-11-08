// The only module that talks to the backend. Same origin in production, Vite proxy in dev.
import type {
  Account,
  AccountType,
  ApiErrorBody,
  Bank,
  Category,
  Country,
  CsvMapping,
  Health,
  Region,
  RuleCreated,
  RuleInput,
  Rule,
  Statement,
  StatementPreview,
  Summary,
  Transaction,
  TransactionCorrected,
} from "../types/api";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details?: unknown,
  ) {
    super(message);
  }
}

function sendJson<T>(method: string, path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, init);
  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as ApiErrorBody | null;
    throw new ApiError(
      response.status,
      body?.error.code ?? `http_${response.status}`,
      body?.error.message ?? response.statusText,
      body?.error.details,
    );
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function postJson<T>(path: string, body: unknown): Promise<T> {
  return sendJson<T>("POST", path, body);
}

export type StatementUnlock = { password: string; remember: boolean };

function query(filters: string): string {
  return filters ? `?${filters}` : "";
}

function statementForm(
  file: File,
  accountId: number,
  mapping?: CsvMapping,
  unlock?: StatementUnlock,
): FormData {
  const form = new FormData();
  form.append("file", file);
  form.append("account_id", String(accountId));
  if (mapping) form.append("mapping", JSON.stringify(mapping));
  if (unlock) {
    form.append("password", unlock.password);
    form.append("remember", String(unlock.remember));
  }
  return form;
}

export const api = {
  health: () => request<Health>("/health"),
  listBanks: () => request<Bank[]>("/banks"),
  createBank: (name: string, country: Country) => postJson<Bank>("/banks", { name, country }),
  listAccounts: (bankId?: string) =>
    request<Account[]>(bankId ? `/accounts?bank_id=${encodeURIComponent(bankId)}` : "/accounts"),
  createAccount: (bankId: string, type: AccountType, name: string) =>
    postJson<Account>("/accounts", { bank_id: bankId, type, name }),
  listStatements: () => request<Statement[]>("/statements"),
  uploadStatement: (
    file: File,
    accountId: number,
    mapping?: CsvMapping,
    unlock?: StatementUnlock,
  ) =>
    request<Statement>("/statements", {
      method: "POST",
      body: statementForm(file, accountId, mapping, unlock),
    }),
  previewStatement: (
    file: File,
    accountId: number,
    mapping: CsvMapping,
    unlock?: StatementUnlock,
  ) =>
    request<StatementPreview>("/statements/preview", {
      method: "POST",
      // Preview never saves the password; only a successful upload does.
      body: statementForm(file, accountId, mapping, unlock && { ...unlock, remember: false }),
    }),
  /** `filters` uses the same parameter names as the page URL (see FILTER_KEYS). */
  listTransactions: (filters = "") => request<Transaction[]>(`/transactions${query(filters)}`),
  summary: (filters = "") => request<Summary>(`/summary${query(filters)}`),
  setTransactionCategory: (transactionId: number, categoryId: number) =>
    sendJson<TransactionCorrected>("PATCH", `/transactions/${transactionId}`, {
      category_id: categoryId,
    }),
  categorizePending: () => request<{ status: string }>("/transactions/categorize", { method: "POST" }),
  listCategories: () => request<Category[]>("/categories"),
  createCategory: (name: string, region: Region) =>
    postJson<Category>("/categories", { name, region }),
  renameCategory: (categoryId: number, name: string) =>
    sendJson<Category>("PATCH", `/categories/${categoryId}`, { name }),
  deleteCategory: (categoryId: number) =>
    request<void>(`/categories/${categoryId}`, { method: "DELETE" }),
  listRules: () => request<Rule[]>("/rules"),
  createRule: (rule: RuleInput) => postJson<RuleCreated>("/rules", rule),
  deleteRule: (ruleId: number) => request<void>(`/rules/${ruleId}`, { method: "DELETE" }),
};
