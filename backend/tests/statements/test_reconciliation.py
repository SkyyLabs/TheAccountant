import pytest

from app.statements.reconciliation import find_balance, reconcile

ROWS = [
    ["EXAMPLE BANK STATEMENT"],
    ["Opening Balance", "1,24,706.78"],
    ["Date", "Narration", "Withdrawal Amt.", "Deposit Amt.", "Closing Balance"],
    ["03/04/26", "UPI-SHARMA KIRANA STORE", "1,250.00", "", "1,23,456.78"],
    ["", "Closing Balance", "", "", "2,63,456.78"],
]


def test_opening_balance_is_read_after_its_label():
    assert find_balance(ROWS, "Opening Balance", "INR", last=False) == 12470678


def test_closing_balance_skips_the_column_header_with_the_same_words():
    assert find_balance(ROWS, "closing balance", "INR", last=True) == 26345678


def test_balance_in_one_cell_with_its_label_is_read():
    rows = [["Previous Balance $1,500.00"]]

    assert find_balance(rows, "Previous Balance", "USD", last=False) == 150000


def test_dr_balance_is_negative():
    rows = [["Closing Balance 2,500.00 Dr"]]

    assert find_balance(rows, "Closing Balance", "INR", last=True) == -250000


def test_missing_label_has_no_balance():
    assert find_balance(ROWS, "New Balance", "INR", last=True) is None


def test_no_label_has_no_balance():
    assert find_balance(ROWS, None, "INR", last=False) is None


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


def test_closing_balance_is_the_last_one_when_each_page_carries_one_forward():
    rows = [
        ["Balance carried forward 1,000.00"],
        ["Balance carried forward 2,000.00"],
        ["Balance carried forward 3,000.00"],
    ]

    assert find_balance(rows, "Balance carried forward", "INR", last=True) == 300000


def test_opening_balance_is_the_first_one():
    rows = [["Balance brought forward 1,000.00"], ["Balance brought forward 2,000.00"]]

    assert find_balance(rows, "Balance brought forward", "INR", last=False) == 100000
