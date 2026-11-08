"""Reconciliation: do a statement's transactions explain the change between its opening and
closing balance? Balances and amounts arrive already verified against the statement text."""


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
