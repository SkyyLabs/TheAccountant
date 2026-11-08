// The only module that talks to the backend. Same origin in production, Vite proxy in dev.
import type {
  Account,
  AccountType,
  ApiErrorBody,
  Bank,
  Country,
  CsvMapping,
  Health,
  Statement,
  StatementPreview,
  Transaction,
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
  return (await response.json()) as T;
}

function postJson<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function statementForm(file: File, accountId: number, mapping?: CsvMapping): FormData {
  const form = new FormData();
  form.append("file", file);
  form.append("account_id", String(accountId));
  if (mapping) form.append("mapping", JSON.stringify(mapping));
  return form;
}

export const api = {
  health: () => request<Health>("/health"),
  listBanks: () => request<Bank[]>("/banks"),
  createBank: (name: string, country: Country) => postJson<Bank>("/banks", { name, country }),
  listAccounts: (bankId: string) =>
    request<Account[]>(`/accounts?bank_id=${encodeURIComponent(bankId)}`),
  createAccount: (bankId: string, type: AccountType, name: string) =>
    postJson<Account>("/accounts", { bank_id: bankId, type, name }),
  listStatements: () => request<Statement[]>("/statements"),
  uploadStatement: (file: File, accountId: number, mapping?: CsvMapping) =>
    request<Statement>("/statements", {
      method: "POST",
      body: statementForm(file, accountId, mapping),
    }),
  previewStatement: (file: File, accountId: number, mapping: CsvMapping) =>
    request<StatementPreview>("/statements/preview", {
      method: "POST",
      body: statementForm(file, accountId, mapping),
    }),
  listTransactions: () => request<Transaction[]>("/transactions"),
};
