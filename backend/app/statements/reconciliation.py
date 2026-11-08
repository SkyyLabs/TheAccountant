"""Statement balances and reconciliation. The balance amounts are read by parse_amount from
the lines the confirmed mapping labels; nothing here comes from the LLM."""

import re

from app.statements.money import AmountError, parse_amount

# A money-looking token: optional sign or bracket, optional symbol, digits with grouping and
# exactly two decimals, optional Cr/Dr.
_AMOUNT_TEXT = re.compile(
    r"\(?[-−]?\s?(?:\$|₹|rs\.?\s?)?\s?\d[\d,]*\.\d{2}\)?(?:\s?(?:cr|dr)\b\.?)?",
    re.IGNORECASE,
)


def find_balance(
    rows: list[list[str]], label: str | None, currency: str, *, last: bool
) -> int | None:
    """The amount after `label` on the first (opening) or last (closing) line that has one."""
    if not label:
        return None
    wanted = label.lower()
    lines = [" ".join(cell for cell in row if cell) for row in rows]
    for line in reversed(lines) if last else lines:
        position = line.lower().find(wanted)
        if position < 0:
            continue
        for match in _AMOUNT_TEXT.finditer(line, position + len(wanted)):
            try:
                return parse_amount(match.group().strip(), currency)
            except AmountError:
                continue
    return None


def reconcile(
    opening_minor: int | None,
    closing_minor: int | None,
    amounts_minor: list[int],
    account_type: str,
) -> tuple[str, int | None]:
    """Return (status, difference). Difference = stated closing minus expected closing.

    Bank: opening + transactions = closing. Card balances are what is owed, so money out
    (negative) raises them: previous - transactions = new.
    """
    if opening_minor is None or closing_minor is None:
        return "unverifiable", None
    total = sum(amounts_minor)
    expected = opening_minor - total if account_type == "credit_card" else opening_minor + total
    difference = closing_minor - expected
    return ("reconciled" if difference == 0 else "unreconciled"), difference
