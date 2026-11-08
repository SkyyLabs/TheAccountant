import pytest

from app.statements.reconciliation import reconcile


def test_bank_statement_that_adds_up_is_reconciled():
    assert reconcile(100000, 85000, [-20000, 5000], "bank") == ("reconciled", 0)


def test_bank_statement_that_does_not_add_up_reports_the_difference():
    assert reconcile(100000, 86000, [-20000, 5000], "bank") == ("unreconciled", 1000)


def test_card_charges_raise_the_balance_owed():
    # Previous 500.00 owed, charges 42.10 and 2.75, payment 500.00: new balance 44.85.
    assert reconcile(50000, 4485, [-4210, -275, 50000], "credit_card") == ("reconciled", 0)


@pytest.mark.parametrize(("opening", "closing"), [(None, 100), (100, None), (None, None)])
def test_statement_without_both_balances_is_unverifiable(opening, closing):
    assert reconcile(opening, closing, [100], "bank") == ("unverifiable", None)
