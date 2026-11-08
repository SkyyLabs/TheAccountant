import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { fakeApi } from "../test/fakeApi";
import type { Bank, Statement } from "../types/api";
import { StatementsPage } from "./StatementsPage";

const CHASE: Bank = {
  id: "chase",
  name: "Chase",
  country: "US",
  currency: "USD",
  default_date_format: "MM/DD/YYYY",
  is_default: true,
};

const IMPORTED: Statement = {
  id: 7,
  account_id: 1,
  bank_id: "chase",
  bank_name: "Chase",
  account_name: "Freedom 1234",
  filename: "march.csv",
  currency: "USD",
  period_start: "2026-03-04",
  period_end: "2026-03-20",
  reconciliation_status: "unverifiable",
  row_count: 4,
  imported_count: 3,
  duplicate_count: 1,
  uploaded_at: "2026-03-21 10:00:00",
};

const MAPPING_REQUIRED = {
  status: 422,
  body: {
    error: {
      code: "csv_mapping_required",
      message: "map the CSV columns for this account",
      details: {
        rows: [
          ["Transaction Date", "Description", "Amount"],
          ["03/04/2026", "GREENLEAF GROCERY", "-42.10"],
        ],
        suggested_mapping: {
          header_row: 0,
          date_column: "Transaction Date",
          description_column: "Description",
          amount_mode: "signed",
          amount_column: "Amount",
          debit_column: null,
          credit_column: null,
          date_format: "MM/DD/YYYY",
        },
        date_formats: ["MM/DD/YYYY", "DD/MM/YYYY"],
      },
    },
  },
};

afterEach(() => {
  vi.unstubAllGlobals();
});

async function chooseChaseAccountAndFile() {
  fireEvent.change(await screen.findByLabelText("Bank"), { target: { value: "chase" } });
  await screen.findByRole("option", { name: "Freedom 1234 (card)" });
  const file = new File(["Transaction Date,Description,Amount\n"], "march.csv", { type: "text/csv" });
  fireEvent.change(screen.getByLabelText("Statement file (CSV)"), { target: { files: [file] } });
  fireEvent.click(screen.getByRole("button", { name: "Upload" }));
}

const ACCOUNTS = {
  body: [{ id: 1, bank_id: "chase", type: "credit_card", name: "Freedom 1234" }],
};

test("imported statements show their status as text, not colour alone", async () => {
  fakeApi({ "GET /api/banks": { body: [CHASE] }, "GET /api/statements": { body: [IMPORTED] } });

  render(<StatementsPage />);

  expect(await screen.findByText("march.csv")).toBeInTheDocument();
  expect(screen.getByText("Unverifiable")).toBeInTheDocument();
  expect(screen.getByText("The file has no balances to check totals against")).toBeInTheDocument();
  expect(screen.getByText("3 new, 1 duplicates skipped")).toBeInTheDocument();
});

test("first upload asks for a mapping, previews it, then imports with it", async () => {
  const { sent } = fakeApi({
    "GET /api/banks": { body: [CHASE] },
    "GET /api/statements": { body: [] },
    "GET /api/accounts": ACCOUNTS,
    "POST /api/statements": () =>
      sent("POST", "/api/statements").length === 1
        ? MAPPING_REQUIRED
        : { status: 201, body: IMPORTED },
    "POST /api/statements/preview": {
      body: {
        row_count: 1,
        skipped_row_count: 0,
        transactions: [
          { date: "2026-03-04", amount_minor: -4210, currency: "USD", description: "GREENLEAF GROCERY" },
        ],
      },
    },
  });
  render(<StatementsPage />);

  await chooseChaseAccountAndFile();
  expect(await screen.findByLabelText("Amount column")).toHaveValue("Amount");
  expect(screen.getByRole("button", { name: "Import" })).toBeDisabled();

  fireEvent.click(screen.getByRole("button", { name: "Preview" }));
  expect(await screen.findByText("-$42.10")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Import" }));

  expect(
    await screen.findByText("Imported 3 transactions from march.csv, 1 already imported from another statement."),
  ).toBeInTheDocument();
  const form = sent("POST", "/api/statements")[1].body as FormData;
  expect(form.get("account_id")).toBe("1");
  expect(JSON.parse(String(form.get("mapping")))).toEqual({
    header_row: 0,
    date_column: "Transaction Date",
    description_column: "Description",
    amount_mode: "signed",
    amount_column: "Amount",
    debit_column: null,
    credit_column: null,
    date_format: "MM/DD/YYYY",
  });
});

test("changing the mapping after a preview requires a new preview before import", async () => {
  fakeApi({
    "GET /api/banks": { body: [CHASE] },
    "GET /api/statements": { body: [] },
    "GET /api/accounts": ACCOUNTS,
    "POST /api/statements": MAPPING_REQUIRED,
    "POST /api/statements/preview": { body: { row_count: 0, skipped_row_count: 0, transactions: [] } },
  });
  render(<StatementsPage />);
  await chooseChaseAccountAndFile();
  fireEvent.click(await screen.findByRole("button", { name: "Preview" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Import" })).toBeEnabled());

  fireEvent.click(screen.getByLabelText("One amount column, positive is money out (many card exports)"));

  expect(screen.getByRole("button", { name: "Import" })).toBeDisabled();
});

test("uploading a file again says it was already imported", async () => {
  fakeApi({
    "GET /api/banks": { body: [CHASE] },
    "GET /api/statements": { body: [] },
    "GET /api/accounts": ACCOUNTS,
    "POST /api/statements": {
      status: 409,
      body: {
        error: {
          code: "duplicate_statement",
          message: "this file was already imported",
          details: { statement_id: 7 },
        },
      },
    },
  });
  render(<StatementsPage />);

  await chooseChaseAccountAndFile();

  expect(
    await screen.findByText("This file was already imported (statement #7). Nothing changed."),
  ).toBeInTheDocument();
});

test("an other bank is created with its country", async () => {
  const { sent } = fakeApi({
    "GET /api/banks": { body: [CHASE] },
    "GET /api/statements": { body: [] },
    "GET /api/accounts": { body: [] },
    "POST /api/banks": {
      status: 201,
      body: { ...CHASE, id: "kotak", name: "Kotak", country: "IN", currency: "INR", is_default: false },
    },
  });
  render(<StatementsPage />);

  fireEvent.change(await screen.findByLabelText("Bank"), { target: { value: "__other" } });
  fireEvent.change(screen.getByLabelText("Bank name"), { target: { value: "Kotak" } });
  fireEvent.change(screen.getByLabelText("Country"), { target: { value: "IN" } });
  fireEvent.click(screen.getByRole("button", { name: "Add bank" }));

  expect(await screen.findByLabelText("Account name")).toBeInTheDocument();
  expect(JSON.parse(String(sent("POST", "/api/banks")[0].body))).toEqual({
    name: "Kotak",
    country: "IN",
  });
});
