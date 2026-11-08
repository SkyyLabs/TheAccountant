import { formatMoney } from "./format";

test("USD uses thousands grouping", () => {
  expect(formatMoney(123456789, "USD")).toBe("$1,234,567.89");
});

test("INR uses lakh and crore grouping", () => {
  expect(formatMoney(1234567890, "INR")).toBe("₹1,23,45,678.90");
});

test("money out shows a minus sign", () => {
  expect(formatMoney(-4210, "USD")).toBe("-$42.10");
});
