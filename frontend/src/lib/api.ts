// The only module that talks to the backend. Same origin in production, Vite proxy in dev.
import type {
  Account,
  ApiErrorBody,
  Category,
  Health,
  Import,
  Region,
  RuleCreated,
  RuleInput,
  Rule,
  Statement,
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

function query(filters: string): string {
  return filters ? `?${filters}` : "";
}

function importForm(file: File, password?: string, remember = true): FormData {
  const form = new FormData();
  form.append("file", file);
  if (password) {
    form.append("password", password);
    form.append("remember", String(remember));
  }
  return form;
}

export const api = {
  health: () => request<Health>("/health"),
  listAccounts: () => request<Account[]>("/accounts"),
  listStatements: () => request<Statement[]>("/statements"),
  /** Upload one statement; the local model reads it in the background (poll getImport). */
  uploadImport: (file: File, password?: string, remember = true) =>
    request<Import>("/imports", { method: "POST", body: importForm(file, password, remember) }),
  getImport: (importId: number) => request<Import>(`/imports/${importId}`),
  listImports: () => request<Import[]>("/imports"),
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
  setExcludedFromSpending: (categoryId: number, excluded: boolean) =>
    sendJson<Category>("PATCH", `/categories/${categoryId}`, { excluded_from_spending: excluded }),
  deleteCategory: (categoryId: number) =>
    request<void>(`/categories/${categoryId}`, { method: "DELETE" }),
  listRules: () => request<Rule[]>("/rules"),
  createRule: (rule: RuleInput) => postJson<RuleCreated>("/rules", rule),
  deleteRule: (ruleId: number) => request<void>(`/rules/${ruleId}`, { method: "DELETE" }),
};
