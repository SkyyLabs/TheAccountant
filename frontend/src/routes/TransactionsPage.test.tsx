import { fireEvent, render, screen } from "@testing-library/react";

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

afterEach(() => {
  vi.unstubAllGlobals();
});

test("amounts are shown in their own currency, never converted", async () => {
  fakeApi({
    "GET /api/transactions": { body: [SALARY, GROCERY] },
    "GET /api/categories": { body: CATEGORIES },
  });

  render(<TransactionsPage />);

  expect(await screen.findByText("₹1,50,000.00")).toBeInTheDocument();
  expect(screen.getByText("-$42.10")).toBeInTheDocument();
  expect(screen.getByText("HDFC Bank · Savings")).toBeInTheDocument();
  expect(screen.getByText("Needs review")).toBeInTheDocument();
});

test("a category the model was unsure of is flagged for checking", async () => {
  fakeApi({
    "GET /api/transactions": { body: [SALARY] },
    "GET /api/categories": { body: CATEGORIES },
  });

  render(<TransactionsPage />);

  expect(await screen.findByText("Check category")).toBeInTheDocument();
});

test("changing a category saves it and offers an always rule", async () => {
  const { sent } = fakeApi({
    "GET /api/transactions": { body: [GROCERY] },
    "GET /api/categories": { body: CATEGORIES },
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
  render(<TransactionsPage />);
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
    "PATCH /api/transactions/1": {
      body: {
        transaction: { ...GROCERY, category_id: 3, category_name: "Dining", category_source: "user" },
        suggested_rule: { match_type: "exact", pattern: "greenleaf grocery", category_id: 3 },
      },
    },
  });
  render(<TransactionsPage />);
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
    "POST /api/transactions/categorize": { status: 202, body: { status: "started" } },
  });
  render(<TransactionsPage />);

  fireEvent.click(await screen.findByRole("button", { name: "Categorize now" }));

  expect(await screen.findByText("Categorizing with the local model…")).toBeInTheDocument();
  expect(sent("POST", "/api/transactions/categorize")).toHaveLength(1);
});

test("no transactions points to the Statements tab", async () => {
  fakeApi({ "GET /api/transactions": { body: [] }, "GET /api/categories": { body: [] } });

  render(<TransactionsPage />);

  expect(
    await screen.findByText("No transactions yet. Upload a statement in the Statements tab."),
  ).toBeInTheDocument();
});
