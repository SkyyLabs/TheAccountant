import { fireEvent, render, screen } from "@testing-library/react";

import { fakeApi } from "../test/fakeApi";
import type { Category, Rule } from "../types/api";
import { CategoriesPage } from "./CategoriesPage";

const CATEGORIES: Category[] = [
  { id: 3, name: "Dining", region: "both", is_default: true, excluded_from_spending: false },
  { id: 9, name: "Domestic Help", region: "IN", is_default: true, excluded_from_spending: false },
  { id: 1, name: "Uncategorized", region: "both", is_default: true, excluded_from_spending: false },
];

const RULE: Rule = {
  id: 4,
  match_type: "contains",
  pattern: "swiggy",
  amount_min_minor: null,
  amount_max_minor: null,
  category_id: 3,
  category_name: "Dining",
  priority: 0,
};

afterEach(() => {
  vi.unstubAllGlobals();
});

test("categories show where they apply and Uncategorized cannot be changed", async () => {
  fakeApi({ "GET /api/categories": { body: CATEGORIES }, "GET /api/rules": { body: [] } });

  render(<CategoriesPage />);

  expect(await screen.findByRole("button", { name: "Rename Domestic Help" })).toBeInTheDocument();
  expect(screen.getByText("India")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Delete Dining" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Delete Uncategorized" })).not.toBeInTheDocument();
});

test("a rule is added with its match, category and priority", async () => {
  const { sent } = fakeApi({
    "GET /api/categories": { body: CATEGORIES },
    "GET /api/rules": { body: [] },
    "POST /api/rules": { status: 201, body: { rule: RULE, applied_count: 3 } },
  });
  render(<CategoriesPage />);
  await screen.findByRole("option", { name: "Dining" });

  fireEvent.change(screen.getByLabelText("Merchant text"), { target: { value: "Swiggy" } });
  fireEvent.change(screen.getByLabelText("Category"), { target: { value: "3" } });
  fireEvent.change(screen.getByLabelText("Priority (higher first)"), { target: { value: "2" } });
  fireEvent.click(screen.getByRole("button", { name: "Add rule" }));

  expect(
    await screen.findByText("Rule added for “swiggy”. 3 existing transactions moved to Dining."),
  ).toBeInTheDocument();
  expect(JSON.parse(String(sent("POST", "/api/rules")[0].body))).toEqual({
    match_type: "contains",
    pattern: "Swiggy",
    category_id: 3,
    priority: 2,
  });
});

test("a rule is deleted", async () => {
  const { sent } = fakeApi({
    "GET /api/categories": { body: CATEGORIES },
    "GET /api/rules": { body: [RULE] },
    "DELETE /api/rules/4": { status: 204, body: null },
  });
  render(<CategoriesPage />);

  fireEvent.click(await screen.findByRole("button", { name: "Delete the rule for swiggy" }));

  expect(await screen.findByText("Deleted the rule for “swiggy”.")).toBeInTheDocument();
  expect(sent("DELETE", "/api/rules/4")).toHaveLength(1);
});

test("deleting a category in use explains why it cannot be deleted", async () => {
  fakeApi({
    "GET /api/categories": { body: CATEGORIES },
    "GET /api/rules": { body: [RULE] },
    "DELETE /api/categories/3": {
      status: 409,
      body: {
        error: {
          code: "category_in_use",
          message: "move its transactions and rules to another category first",
        },
      },
    },
  });
  render(<CategoriesPage />);

  fireEvent.click(await screen.findByRole("button", { name: "Delete Dining" }));

  expect(
    await screen.findByText("move its transactions and rules to another category first"),
  ).toBeInTheDocument();
});

test("a category is added for one region", async () => {
  const { sent } = fakeApi({
    "GET /api/categories": { body: CATEGORIES },
    "GET /api/rules": { body: [] },
    "POST /api/categories": {
      status: 201,
      body: { id: 30, name: "Pets", region: "US", is_default: false, excluded_from_spending: false },
    },
  });
  render(<CategoriesPage />);

  fireEvent.change(await screen.findByLabelText("New category"), { target: { value: "Pets" } });
  fireEvent.change(screen.getByLabelText("Used for"), { target: { value: "US" } });
  fireEvent.click(screen.getByRole("button", { name: "Add category" }));

  expect(await screen.findByText("Added Pets.")).toBeInTheDocument();
  expect(JSON.parse(String(sent("POST", "/api/categories")[0].body))).toEqual({
    name: "Pets",
    region: "US",
  });
});

test("a category is renamed", async () => {
  const { sent } = fakeApi({
    "GET /api/categories": { body: CATEGORIES },
    "GET /api/rules": { body: [] },
    "PATCH /api/categories/3": {
      body: { id: 3, name: "Eating Out", region: "both", is_default: true, excluded_from_spending: false },
    },
  });
  render(<CategoriesPage />);

  fireEvent.click(await screen.findByRole("button", { name: "Rename Dining" }));
  fireEvent.change(screen.getByLabelText("New name for Dining"), {
    target: { value: "Eating Out" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));

  expect(await screen.findByText("Renamed to Eating Out.")).toBeInTheDocument();
  expect(JSON.parse(String(sent("PATCH", "/api/categories/3")[0].body))).toEqual({
    name: "Eating Out",
  });
});


test("a category can be left out of spending totals", async () => {
  const { sent } = fakeApi({
    "GET /api/categories": { body: CATEGORIES },
    "GET /api/rules": { body: [] },
    "PATCH /api/categories/3": {
      body: { id: 3, name: "Dining", region: "both", is_default: true, excluded_from_spending: true },
    },
  });
  render(<CategoriesPage />);
  await screen.findByRole("button", { name: "Rename Dining" });

  fireEvent.click(screen.getAllByLabelText("Not spending")[0]);

  expect(await screen.findByText("Dining is now left out of spending totals.")).toBeInTheDocument();
  expect(JSON.parse(String(sent("PATCH", "/api/categories/3")[0].body))).toEqual({
    excluded_from_spending: true,
  });
});
