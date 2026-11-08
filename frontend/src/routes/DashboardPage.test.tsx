import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";

import { fakeApi } from "../test/fakeApi";
import type { Category, Summary, Transaction } from "../types/api";
import { DashboardPage } from "./DashboardPage";

const SUMMARY: Summary = {
  totals: [
    { currency: "INR", money_in_minor: 15000000, money_out_minor: 1125000, transaction_count: 3 },
    { currency: "USD", money_in_minor: 0, money_out_minor: 129485, transaction_count: 3 },
  ],
  by_month: [
    { month: "2026-03", currency: "USD", money_in_minor: 0, money_out_minor: 129485, transaction_count: 3 },
  ],
  by_category: [
    { category_id: 6, category_name: "Shopping", currency: "USD", money_in_minor: 0, money_out_minor: 125000, transaction_count: 1 },
    { category_id: 2, category_name: "Groceries", currency: "USD", money_in_minor: 0, money_out_minor: 4210, transaction_count: 1 },
    { category_id: null, category_name: null, currency: "INR", money_in_minor: 0, money_out_minor: 1125000, transaction_count: 2 },
  ],
};

const CATEGORIES: Category[] = [
  { id: 2, name: "Groceries", region: "both", is_default: true, excluded_from_spending: false },
  { id: 3, name: "Dining", region: "both", is_default: true, excluded_from_spending: false },
];

const GROCERY: Transaction = {
  id: 1,
  statement_id: 1,
  account_id: 1,
  account_name: "••4410",
  bank_id: "chase",
  bank_name: "Chase",
  date: "2026-03-04",
  amount_minor: -4210,
  currency: "USD",
  description: "GREENLEAF GROCERY",
  needs_review: false,
  category_id: 2,
  category_name: "Groceries",
  category_source: "llm",
  category_needs_review: false,
};

function api(overrides = {}) {
  return fakeApi({
    "GET /api/summary": { body: SUMMARY },
    "GET /api/transactions": { body: [GROCERY] },
    "GET /api/statements": { body: [] },
    "GET /api/categories": { body: CATEGORIES },
    "GET /api/accounts": { body: [] },
    ...overrides,
  });
}

function renderAt(path = "/dashboard") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <DashboardPage />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

test("figures are for one currency at a time, with a switch when there are two", async () => {
  api();
  renderAt("/dashboard?currency=USD");

  expect(await screen.findByText("$1,294.85", { selector: "p" })).toBeInTheDocument();
  expect(screen.queryByText("₹11,250.00")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "INR" })).toHaveAttribute("aria-pressed", "false");
});

test("spending by category lists each category's money out", async () => {
  api();
  renderAt("/dashboard?currency=USD");

  const table = await screen.findByRole("table", { name: "USD spending by category" });

  expect(within(table).getAllByRole("row").map((row) => row.textContent)).toEqual([
    "Shopping$1,250.00",
    "Groceries$42.10",
  ]);
});

test("the spending figures leave out transfers while the table keeps every transaction", async () => {
  const { requests } = api();
  renderAt("/dashboard?currency=USD&q=cafe");

  await screen.findByText("GREENLEAF GROCERY");

  const queries = requests.map((r) => `${r.path}?${r.query}`);
  expect(queries).toContain("/api/summary?currency=USD&q=cafe&spending_only=true");
  expect(queries).toContain("/api/transactions?currency=USD&q=cafe");
});

test("a range button filters from the start of that range", async () => {
  const { requests } = api();
  renderAt("/dashboard?currency=USD");
  await screen.findByText("GREENLEAF GROCERY");

  fireEvent.click(screen.getByRole("button", { name: "This year" }));

  const year = new Date().getFullYear();
  await waitFor(() =>
    expect(requests.map((r) => `${r.path}?${r.query}`)).toContain(
      `/api/transactions?date_from=${year}-01-01&currency=USD`,
    ),
  );
});

test("a load error goes away once the data loads again", async () => {
  let calls = 0;
  api({
    "GET /api/summary": () =>
      ++calls === 1
        ? { status: 500, body: { error: { code: "internal", message: "down" } } }
        : { body: SUMMARY },
  });
  renderAt("/dashboard?currency=USD");
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not load your data");

  fireEvent.click(screen.getByRole("button", { name: "This year" }));

  expect(await screen.findByText("GREENLEAF GROCERY")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("transactions that did not match the statement are flagged and can be shown alone", async () => {
  api({
    "GET /api/transactions": {
      body: [GROCERY, { ...GROCERY, id: 2, description: "ODD ONE", needs_review: true }],
    },
  });
  renderAt("/dashboard?currency=USD");

  fireEvent.click(await screen.findByRole("button", { name: "Show them" }));

  expect(await screen.findByText("ODD ONE")).toBeInTheDocument();
  expect(screen.queryByText("GREENLEAF GROCERY")).not.toBeInTheDocument();
});

test("changing a category offers a rule for the merchant", async () => {
  const { sent } = api({
    "PATCH /api/transactions/1": {
      body: {
        transaction: { ...GROCERY, category_id: 3, category_name: "Dining", category_source: "user" },
        suggested_rule: { match_type: "exact", pattern: "greenleaf grocery", category_id: 3 },
      },
    },
    "POST /api/rules": {
      status: 201,
      body: {
        rule: { id: 1, match_type: "exact", pattern: "greenleaf grocery", amount_min_minor: null, amount_max_minor: null, category_id: 3, category_name: "Dining", priority: 0 },
        applied_count: 2,
      },
    },
  });
  renderAt("/dashboard?currency=USD");
  await screen.findByRole("option", { name: "Dining" });

  fireEvent.change(screen.getByLabelText("Category for GREENLEAF GROCERY"), { target: { value: "3" } });
  fireEvent.click(await screen.findByRole("button", { name: "Create rule" }));

  expect(await screen.findByText("Rule created. 2 other transactions moved to Dining.")).toBeInTheDocument();
  expect(JSON.parse(String(sent("POST", "/api/rules")[0].body))).toEqual({
    match_type: "exact",
    pattern: "greenleaf grocery",
    category_id: 3,
  });
});

test("with nothing uploaded yet the dashboard points to upload", async () => {
  api({
    "GET /api/summary": { body: { totals: [], by_month: [], by_category: [] } },
    "GET /api/transactions": { body: [] },
  });
  renderAt();

  expect(await screen.findByRole("link", { name: "Upload statements" })).toHaveAttribute("href", "/upload");
});
