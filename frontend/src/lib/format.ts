import type { Currency } from "../types/api";

// en-IN groups by lakh and crore (12,34,567.00); en-US by thousands.
const LOCALE: Record<Currency, string> = { USD: "en-US", INR: "en-IN" };

/** Display only: amounts stay integer minor units everywhere else. */
export function formatMoney(amountMinor: number, currency: Currency): string {
  return new Intl.NumberFormat(LOCALE[currency], { style: "currency", currency }).format(
    amountMinor / 100,
  );
}
