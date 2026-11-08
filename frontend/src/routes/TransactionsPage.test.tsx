import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";

import { fakeApi } from "../test/fakeApi";
import type { Category, Transaction } from "../types/api";
import { TransactionsPage } from "./TransactionsPage";

const CATEGORIES: Category[] = [
  { id: 2, name: "Groceries", region: "both", is_default: true },
  { id: 3, name: "Dining", region: "both", is_default: true },
  { id: 1, name: "Uncategorized", region: "both", is_default: true },
];

const SALARY: Transaction = {
  id: 2,
  statement_id: 1,
  account_id: 2,
  account_name: "Savings",
  bank_id: "hdfc",
  bank_name: "HDFC Bank",
  date: "2026-04-05",
  amount_minor: 15000000,
  currency: "INR",
  description: "SALARY EXAMPLE CORP",
  needs_review: false,
  category_id: 1,
  category_name: "Uncategorized",
  category_source: "llm",
  category_needs_review: true,
};

const GROCERY: Transaction = {
  id: 1,
  statement_id: 2,
  account_id: 1,
  account_name: "Freedom 1234",
  bank_id: "chase",
  bank_name: "Chase",
  date: "2026-03-04",
  amount_minor: -4210,
  currency: "USD",
  description: "GREENLEAF GROCERY",
  needs_review: true,
  category_id: 2,
  category_name: "Groceries",
  category_source: "llm",
  category_needs_review: false,
};

const EMPTY_SUMMARY = { body: { totals: [], by_month: [], by_category: [] } };

const ACCOUNTS = {
  body: [
    { id: 1, bank_id: "chase", bank_name: "Chase", type: "credit_card", name: "Freedom 1234" },
    { id: 2, bank_id: "hdfc", bank_name: "HDFC Bank", type: "bank", name: "Savings" },
  ],
};

function renderAt(path = "/transactions") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <TransactionsPage />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

test("amounts are shown in their own currency, never converted", async () => {
  fakeApi({
    "GET /api/transactions": { body: [SALARY, GROCERY] },
    "GET /api/categories": { body: CATEGORIES },
    "GET /api/summary": EMPTY_SUMMARY,
    "GET /api/accounts": ACCOUNTS,
  });

  renderAt();

  expect(await screen.findByText("₹1,50,000.00")).toBeInTheDocument();
  expect(screen.getByText("-$42.10")).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "HDFC Bank · Savings" })).toBeInTheDocument();
  expect(screen.getByText("Needs review")).toBeInTheDocument();
});

test("a category the model was unsure of is flagged for checking", async () => {
  fakeApi({
    "GET /api/transactions": { body: [SALARY] },
    "GET /api/categories": { body: CATEGORIES },
    "GET /api/summary": EMPTY_SUMMARY,
    "GET /api/accounts": ACCOUNTS,
  });

  renderAt();

  expect(await screen.findByText("Check category")).toBeInTheDocument();
});

test("changing a category saves it and offers an always rule", async () => {
  const { sent } = fakeApi({
    "GET /api/transactions": { body: [GROCERY] },
    "GET /api/categories": { body: CATEGORIES },
    "GET /api/summary": EMPTY_SUMMARY,
    "GET /api/accounts": ACCOUNTS,
    "PATCH /api/transactions/1": {
      body: {
        transaction: { ...GROCERY, category_id: 3, category_name: "Dining", category_source: "user" },
        suggested_rule: { match_type: "exact", pattern: "greenleaf grocery", category_id: 3 },
      },
    },
    "POST /api/rules": {
      status: 201,
      body: {
        rule: {
          id: 1,
          match_type: "exact",
          pattern: "greenleaf grocery",
          amount_min_minor: null,
          amount_max_minor: null,
          category_id: 3,
          category_name: "Dining",
          priority: 0,
        },
        applied_count: 2,
      },
    },
  });
  renderAt();
  const select = await screen.findByLabelText("Category for GREENLEAF GROCERY");
  await screen.findByRole("option", { name: "Dining" });

  fireEvent.change(select, { target: { value: "3" } });
  fireEvent.click(await screen.findByRole("button", { name: "Create rule" }));

  expect(JSON.parse(String(sent("PATCH", "/api/transactions/1")[0].body))).toEqual({
    category_id: 3,
  });
  expect(
    await screen.findByText("Rule created. 2 other transactions moved to Dining."),
  ).toBeInTheDocument();
  expect(JSON.parse(String(sent("POST", "/api/rules")[0].body))).toEqual({
    match_type: "exact",
    pattern: "greenleaf grocery",
    category_id: 3,
  });
});

test("declining the rule offer creates nothing", async () => {
  const { sent } = fakeApi({
    "GET /api/transactions": { body: [GROCERY] },
    "GET /api/categories": { body: CATEGORIES },
    "GET /api/summary": EMPTY_SUMMARY,
    "GET /api/accounts": ACCOUNTS,
    "PATCH /api/transactions/1": {
      body: {
        transaction: { ...GROCERY, category_id: 3, category_name: "Dining", category_source: "user" },
        suggested_rule: { match_type: "exact", pattern: "greenleaf grocery", category_id: 3 },
      },
    },
  });
  renderAt();
  const select = await screen.findByLabelText("Category for GREENLEAF GROCERY");
  await screen.findByRole("option", { name: "Dining" });
  fireEvent.change(select, { target: { value: "3" } });

  fireEvent.click(await screen.findByRole("button", { name: "No thanks" }));

  expect(screen.queryByRole("button", { name: "Create rule" })).not.toBeInTheDocument();
  expect(sent("POST", "/api/rules")).toHaveLength(0);
});

test("uncategorized transactions can be sent to the model again", async () => {
  const { sent } = fakeApi({
    "GET /api/transactions": {
      body: [{ ...GROCERY, category_id: null, category_name: null, category_source: null }],
    },
    "GET /api/categories": { body: CATEGORIES },
    "GET /api/summary": EMPTY_SUMMARY,
    "GET /api/accounts": ACCOUNTS,
    "POST /api/transactions/categorize": { status: 202, body: { status: "started" } },
  });
  renderAt();

  fireEvent.click(await screen.findByRole("button", { name: "Categorize now" }));

  expect(await screen.findByText("Categorizing with the local model…")).toBeInTheDocument();
  expect(sent("POST", "/api/transactions/categorize")).toHaveLength(1);
});

test("no transactions points to the Statements tab", async () => {
  fakeApi({
    "GET /api/transactions": { body: [] },
    "GET /api/categories": { body: [] },
    "GET /api/summary": EMPTY_SUMMARY,
    "GET /api/accounts": ACCOUNTS,
  });

  renderAt();

  expect(
    await screen.findByText("No transactions yet. Upload a statement in the Statements tab."),
  ).toBeInTheDocument();
});


test("filters in the address are sent to the backend for the list and the totals", async () => {
  const { requests } = fakeApi({
    "GET /api/transactions": { body: [] },
    "GET /api/categories": { body: CATEGORIES },
    "GET /api/summary": EMPTY_SUMMARY,
    "GET /api/accounts": ACCOUNTS,
  });

  renderAt("/transactions?currency=INR&category_ids=2&category_ids=3&q=cafe&unrelated=1");

  expect(await screen.findByText("No transactions match these filters.")).toBeInTheDocument();
  const sent = requests.map((request) => request.path + "?" + String(request.query));
  expect(sent).toContain("/api/transactions?category_ids=2&category_ids=3&currency=INR&q=cafe");
  expect(sent).toContain("/api/summary?category_ids=2&category_ids=3&currency=INR&q=cafe");
});

test("choosing a filter fetches with it", async () => {
  const { requests } = fakeApi({
    "GET /api/transactions": { body: [GROCERY] },
    "GET /api/categories": { body: CATEGORIES },
    "GET /api/summary": EMPTY_SUMMARY,
    "GET /api/accounts": ACCOUNTS,
  });
  renderAt();
  await screen.findByText("GREENLEAF GROCERY");

  fireEvent.change(screen.getByLabelText("Currency"), { target: { value: "USD" } });
  fireEvent.click(screen.getByText("Accounts", { selector: "summary" }));
  fireEvent.click(screen.getByLabelText("HDFC Bank · Savings"));

  await waitFor(() =>
    expect(requests.map((r) => `${r.path}?${r.query}`)).toContain(
      "/api/transactions?account_ids=2&currency=USD",
    ),
  );
});

test("totals are shown per currency", async () => {
  fakeApi({
    "GET /api/transactions": { body: [SALARY, GROCERY] },
    "GET /api/categories": { body: CATEGORIES },
    "GET /api/accounts": ACCOUNTS,
    "GET /api/summary": {
      body: {
        totals: [
          { currency: "INR", money_in_minor: 15000000, money_out_minor: 1125000, transaction_count: 3 },
          { currency: "USD", money_in_minor: 50000, money_out_minor: 129485, transaction_count: 4 },
        ],
        by_month: [],
        by_category: [],
      },
    },
  });

  renderAt();

  const totals = await screen.findByRole("list", { name: "Totals" });
  expect(totals).toHaveTextContent("INR: in ₹1,50,000.00 · out ₹11,250.00 · 3 transactions");
  expect(totals).toHaveTextContent("USD: in $500.00 · out $1,294.85 · 4 transactions");
});
