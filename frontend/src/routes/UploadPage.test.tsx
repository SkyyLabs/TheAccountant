import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";

import { fakeApi } from "../test/fakeApi";
import type { Import, Statement } from "../types/api";
import { POLL_MS, REDIRECT_MS, UploadPage } from "./UploadPage";

const STATEMENT: Statement = {
  id: 1,
  account_id: 1,
  bank_id: "chase",
  bank_name: "Chase",
  account_name: "••4321",
  filename: "dec.pdf",
  currency: "USD",
  period_start: "2025-12-08",
  period_end: "2026-01-05",
  reconciliation_status: "reconciled",
  opening_balance_minor: 50000,
  closing_balance_minor: 66802,
  reconciliation_difference_minor: 0,
  row_count: 8,
  imported_count: 8,
  duplicate_count: 0,
  categorization_status: "done",
  uploaded_at: "",
};

function importOf(changes: Partial<Import>): Import {
  return {
    id: 7,
    filename: "dec.pdf",
    status: "processing",
    progress_done: 0,
    progress_total: 0,
    error: null,
    rejected_count: 0,
    uploaded_at: "",
    statements: [],
    ...changes,
  } as Import;
}

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/upload"]}>
      <Routes>
        <Route path="/upload" element={<UploadPage />} />
        <Route path="/dashboard" element={<h1>Dashboard page</h1>} />
      </Routes>
    </MemoryRouter>,
  );
}

function choose(...names: string[]) {
  const files = names.map((name) => new File(["%PDF-1.7"], name, { type: "application/pdf" }));
  fireEvent.change(screen.getByLabelText("Choose statement files"), { target: { files } });
}

async function wait(ms: number) {
  await act(async () => {
    vi.advanceTimersByTime(ms);
  });
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

test("each chosen file is uploaded on its own", async () => {
  const { sent } = fakeApi({
    "POST /api/imports": { status: 202, body: importOf({}) },
    "GET /api/imports/7": { body: importOf({}) },
  });
  renderPage();

  choose("dec.pdf", "jan.csv");

  expect(await screen.findByText("jan.csv")).toBeInTheDocument();
  expect(sent("POST", "/api/imports")).toHaveLength(2);
  expect((sent("POST", "/api/imports")[0].body as FormData).get("password")).toBeNull();
});

test("progress follows the local AI reading the statement", async () => {
  let polls = 0;
  fakeApi({
    "POST /api/imports": { status: 202, body: importOf({}) },
    "GET /api/imports/7": () => {
      polls += 1;
      return { body: importOf({ progress_done: 1, progress_total: 3 }) };
    },
  });
  renderPage();
  choose("dec.pdf");
  await screen.findByText("Reading with the local AI…");

  await wait(POLL_MS);

  expect(await screen.findByText("Reading with the local AI · part 2 of 3")).toBeInTheDocument();
  expect(polls).toBeGreaterThan(0);
});

test("when every file is read, the dashboard opens", async () => {
  fakeApi({
    "POST /api/imports": { status: 202, body: importOf({}) },
    "GET /api/imports/7": { body: importOf({ status: "done", progress_done: 2, progress_total: 2, statements: [STATEMENT] }) },
  });
  renderPage();
  choose("dec.pdf");
  await screen.findByText("Reading with the local AI…");

  await wait(POLL_MS);
  expect(await screen.findByText("8 transactions · Chase ••4321")).toBeInTheDocument();
  await wait(REDIRECT_MS);

  expect(await screen.findByRole("heading", { name: "Dashboard page" })).toBeInTheDocument();
});

test("a failed file shows the reason and does not open the dashboard", async () => {
  fakeApi({
    "POST /api/imports": { status: 202, body: importOf({}) },
    "GET /api/imports/7": {
      body: importOf({ status: "failed", error: "No transactions were found in this file." }),
    },
  });
  renderPage();
  choose("notes.pdf");
  await screen.findByText("Reading with the local AI…");

  await wait(POLL_MS);
  expect(await screen.findByText("No transactions were found in this file.")).toBeInTheDocument();
  await wait(REDIRECT_MS * 2);

  expect(screen.queryByRole("heading", { name: "Dashboard page" })).not.toBeInTheDocument();
});

test("a locked PDF asks for its password and sends it with remember on", async () => {
  let attempts = 0;
  const { sent } = fakeApi({
    "POST /api/imports": () => {
      attempts += 1;
      return attempts === 1
        ? { status: 422, body: { error: { code: "pdf_password_required", message: "needs a password" } } }
        : { status: 202, body: importOf({}) };
    },
    "GET /api/imports/7": { body: importOf({}) },
  });
  renderPage();
  choose("locked.pdf");

  fireEvent.change(await screen.findByLabelText("Password for locked.pdf"), { target: { value: "s3cret" } });
  fireEvent.click(screen.getByRole("button", { name: "Unlock" }));

  expect(await screen.findByText("Reading with the local AI…")).toBeInTheDocument();
  const form = sent("POST", "/api/imports")[1].body as FormData;
  expect(form.get("password")).toBe("s3cret");
  expect(form.get("remember")).toBe("true");
});

test("a wrong password says so", async () => {
  fakeApi({
    "POST /api/imports": { status: 422, body: { error: { code: "pdf_password_invalid", message: "wrong" } } },
  });
  renderPage();

  choose("locked.pdf");

  expect(await screen.findByText("That password did not open the PDF.")).toBeInTheDocument();
});

test("a file uploaded before is marked as such", async () => {
  fakeApi({
    "POST /api/imports": {
      status: 409,
      body: { error: { code: "duplicate_statement", message: "already", details: { import_id: 3 } } },
    },
  });
  renderPage();

  choose("dec.pdf");

  expect(await screen.findByText("Already uploaded before")).toBeInTheDocument();
});
