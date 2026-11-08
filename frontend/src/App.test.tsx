import { act, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";

import { App } from "./App";
import { WELCOME_MS } from "./components/Welcome";
import { fakeApi } from "./test/fakeApi";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

const EMPTY = {
  "GET /api/health": { body: { status: "ok", version: "0.1.0", schema_version: 7 } },
  "GET /api/summary": { body: { totals: [], by_month: [], by_category: [] } },
  "GET /api/transactions": { body: [] },
  "GET /api/statements": { body: [] },
  "GET /api/categories": { body: [] },
  "GET /api/accounts": { body: [] },
};

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

test("the app opens on a welcome screen, then the upload page on a first visit", async () => {
  fakeApi({ ...EMPTY, "GET /api/imports": { body: [] } });
  renderAt("/");
  expect(screen.getByRole("heading", { name: "TheAccountant" })).toBeInTheDocument();

  await act(async () => {
    vi.advanceTimersByTime(WELCOME_MS);
  });

  expect(await screen.findByRole("heading", { name: "Upload your statements" })).toBeInTheDocument();
});

test("with statements already read, the welcome screen leads to the dashboard", async () => {
  fakeApi({
    ...EMPTY,
    "GET /api/imports": {
      body: [{ id: 1, filename: "a.pdf", status: "done", progress_done: 1, progress_total: 1, error: null, rejected_count: 0, uploaded_at: "", statements: [] }],
    },
  });
  renderAt("/");

  await act(async () => {
    vi.advanceTimersByTime(WELCOME_MS);
  });

  expect(await screen.findByText("Nothing here yet")).toBeInTheDocument();
});

test("the header links to the dashboard, categories and upload", () => {
  fakeApi({ ...EMPTY, "GET /api/imports": { body: [] } });
  renderAt("/dashboard");

  const nav = screen.getByRole("navigation", { name: "Main" });
  expect(Array.from(nav.querySelectorAll("a")).map((a) => a.textContent)).toEqual([
    "Dashboard",
    "Categories",
  ]);
  expect(screen.getByRole("link", { name: "Upload" })).toHaveAttribute("href", "/upload");
});

test("the status shows the app is private and offline when the server answers", async () => {
  fakeApi({ ...EMPTY, "GET /api/imports": { body: [] } });
  renderAt("/dashboard");

  expect(await screen.findByText("Private · offline")).toBeInTheDocument();
});
