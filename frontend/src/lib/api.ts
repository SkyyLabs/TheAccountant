// The only module that talks to the backend. Same origin in production, Vite proxy in dev.
import type { ApiErrorBody, Health } from "../types/api";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
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
    );
  }
  return (await response.json()) as T;
}

export const api = {
  health: () => request<Health>("/health"),
};
