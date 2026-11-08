import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";

import { App } from "./App";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

function stubHealth(response: Promise<Response>) {
  vi.stubGlobal("fetch", vi.fn(() => response));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

test("root redirects to the Overview tab", async () => {
  stubHealth(new Promise(() => {}));
  renderAt("/");

  expect(await screen.findByRole("heading", { name: "Overview" })).toBeInTheDocument();
});

test("all five tabs are in the main navigation", () => {
  stubHealth(new Promise(() => {}));
  renderAt("/overview");

  const nav = screen.getByRole("navigation", { name: "Main" });
  const labels = Array.from(nav.querySelectorAll("a")).map((link) => link.textContent);
  expect(labels).toEqual(["Overview", "Transactions", "Statements", "Categories & Rules", "Chat"]);
});

test("clicking a tab shows its page and marks it current", async () => {
  stubHealth(new Promise(() => {}));
  renderAt("/overview");

  fireEvent.click(screen.getByRole("link", { name: "Statements" }));

  expect(await screen.findByRole("heading", { name: "Statements" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Statements" })).toHaveAttribute("aria-current", "page");
});

test("unknown paths fall back to Overview", async () => {
  stubHealth(new Promise(() => {}));
  renderAt("/nope");

  expect(await screen.findByRole("heading", { name: "Overview" })).toBeInTheDocument();
});

test("backend status shows online when health succeeds", async () => {
  stubHealth(
    Promise.resolve(
      new Response(JSON.stringify({ status: "ok", version: "0.1.0", schema_version: 1 })),
    ),
  );
  renderAt("/overview");

  expect(await screen.findByText("Backend online")).toBeInTheDocument();
});

test("backend status shows offline with a hint when health fails", async () => {
  stubHealth(Promise.reject(new TypeError("Failed to fetch")));
  renderAt("/overview");

  expect(await screen.findByText("Backend offline: run make run")).toBeInTheDocument();
});
