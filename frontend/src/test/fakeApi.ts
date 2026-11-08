// A stand-in for the backend: maps "METHOD /api/path" to a status and JSON body, and records
// every request so tests can assert what the UI sent.
type Reply = { status?: number; body: unknown };
type Handler = Reply | (() => Reply);

export type RecordedRequest = {
  method: string;
  path: string;
  query: URLSearchParams;
  body: BodyInit | null | undefined;
};

export function fakeApi(handlers: Record<string, Handler>) {
  const requests: RecordedRequest[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const method = init?.method ?? "GET";
      const url = new URL(String(input), "http://localhost");
      const path = url.pathname;
      requests.push({ method, path, query: url.searchParams, body: init?.body });
      const handler = handlers[`${method} ${path}`];
      if (!handler) {
        return new Response(
          JSON.stringify({ error: { code: "not_found", message: "Not Found" } }),
          { status: 404 },
        );
      }
      const reply = typeof handler === "function" ? handler() : handler;
      const status = reply.status ?? 200;
      // A 204 response may not carry a body.
      return new Response(status === 204 ? null : JSON.stringify(reply.body), { status });
    }),
  );
  return {
    requests,
    sent: (method: string, path: string) =>
      requests.filter((request) => request.method === method && request.path === path),
  };
}
