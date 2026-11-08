import { render, screen } from "@testing-library/react";

import { fakeApi } from "../test/fakeApi";
import { TransactionsPage } from "./TransactionsPage";

afterEach(() => {
  vi.unstubAllGlobals();
});

test("amounts are shown in their own currency, never converted", async () => {
  fakeApi({
    "GET /api/transactions": {
      body: [
        {
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
        },
        {
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
        },
      ],
    },
  });

  render(<TransactionsPage />);

  expect(await screen.findByText("₹1,50,000.00")).toBeInTheDocument();
  expect(screen.getByText("-$42.10")).toBeInTheDocument();
  expect(screen.getByText("HDFC Bank · Savings")).toBeInTheDocument();
  expect(screen.getByText("Needs review")).toBeInTheDocument();
});

test("no transactions points to the Statements tab", async () => {
  fakeApi({ "GET /api/transactions": { body: [] } });

  render(<TransactionsPage />);

  expect(
    await screen.findByText("No transactions yet. Upload a statement in the Statements tab."),
  ).toBeInTheDocument();
});
