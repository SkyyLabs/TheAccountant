import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router";

import { fakeApi } from "../test/fakeApi";
import { OverviewPage } from "./OverviewPage";

const SUMMARY = {
  totals: [
    { currency: "INR", money_in_minor: 15000000, money_out_minor: 1125000, transaction_count: 3 },
    { currency: "USD", money_in_minor: 0, money_out_minor: 129485, transaction_count: 3 },
  ],
  by_month: [
    { month: "2026-03", currency: "USD", money_in_minor: 0, money_out_minor: 129485, transaction_count: 3 },
    { month: "2026-04", currency: "INR", money_in_minor: 15000000, money_out_minor: 1125000, transaction_count: 3 },
  ],
  by_category: [
    { category_id: null, category_name: null, currency: "INR", money_in_minor: 15000000, money_out_minor: 1125000, transaction_count: 3 },
    { category_id: 6, category_name: "Shopping", currency: "USD", money_in_minor: 0, money_out_minor: 125000, transaction_count: 1 },
    { category_id: 2, category_name: "Groceries", currency: "USD", money_in_minor: 0, money_out_minor: 4210, transaction_count: 1 },
    { category_id: 21, category_name: "Card Payments", currency: "USD", money_in_minor: 50000, money_out_minor: 0, transaction_count: 1 },
  ],
};

const CATEGORIES = {
  body: [
    { id: 20, name: "Transfers", region: "both", is_default: true, excluded_from_spending: true },
    { id: 21, name: "Card Payments", region: "both", is_default: true, excluded_from_spending: true },
  ],
};

function renderAt(path = "/overview") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <OverviewPage />
    </MemoryRouter>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

test("each currency gets its own figures, never combined", async () => {
  fakeApi({
    "GET /api/summary": { body: SUMMARY },
    "GET /api/categories": CATEGORIES,
    "GET /api/accounts": { body: [] },
  });

  renderAt();

  const inr = await screen.findByRole("region", { name: "INR" });
  const usd = screen.getByRole("region", { name: "USD" });
  expect(within(inr).getByText("₹11,250.00", { selector: "dd" })).toBeInTheDocument();
  expect(within(usd).getByText("$1,294.85", { selector: "dd" })).toBeInTheDocument();
  expect(within(usd).queryByText("₹11,250.00")).not.toBeInTheDocument();
});

test("the category table lists money out, biggest first, without categories that only had money in", async () => {
  fakeApi({
    "GET /api/summary": { body: SUMMARY },
    "GET /api/categories": CATEGORIES,
    "GET /api/accounts": { body: [] },
  });
  renderAt();

  const usd = await screen.findByRole("region", { name: "USD" });
  const table = within(usd).getByRole("table", { name: "USD money out by category" });

  const rows = within(table).getAllByRole("row").slice(1).map((row) => row.textContent);
  expect(rows).toEqual(["Shopping$1,250.00", "Groceries$42.10"]);
});

test("uncategorized spending is shown as not categorized yet", async () => {
  fakeApi({
    "GET /api/summary": { body: SUMMARY },
    "GET /api/categories": CATEGORIES,
    "GET /api/accounts": { body: [] },
  });
  renderAt();

  const inr = await screen.findByRole("region", { name: "INR" });

  expect(within(inr).getByRole("rowheader", { name: "Not categorized yet" })).toBeInTheDocument();
});

test("transfers and card payments are left out by default and can be counted", async () => {
  const { requests } = fakeApi({
    "GET /api/summary": { body: SUMMARY },
    "GET /api/categories": CATEGORIES,
    "GET /api/accounts": { body: [] },
  });
  renderAt("/overview?currency=USD");
  const toggle = await screen.findByLabelText(
    "Leave out Transfers and Card Payments (money moving between your own accounts)",
  );
  expect(toggle).toBeChecked();

  fireEvent.click(toggle);

  const summaries = () => requests.filter((r) => r.path === "/api/summary").map((r) => String(r.query));
  await waitFor(() => expect(summaries()).toContain("currency=USD&spending_only=false"));
  expect(summaries()[0]).toBe("currency=USD&spending_only=true");
});

test("nothing imported yet points to the Statements tab", async () => {
  fakeApi({
    "GET /api/summary": { body: { totals: [], by_month: [], by_category: [] } },
    "GET /api/categories": CATEGORIES,
    "GET /api/accounts": { body: [] },
  });

  renderAt();

  expect(
    await screen.findByText(
      "Nothing to show yet. Upload a statement in the Statements tab, or widen the filters.",
    ),
  ).toBeInTheDocument();
});
