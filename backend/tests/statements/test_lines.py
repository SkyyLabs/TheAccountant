import pytest
from fixtures.chase_like_statement import chase_like_statement

from app.statements.lines import LinesError, read_sections, statement_period
from app.statements.pdf import read_text


@pytest.fixture(scope="module")
def sections():
    text = read_text(chase_like_statement(), None)
    return read_sections(text, currency="USD", day_first=False)


def test_each_account_in_one_pdf_is_its_own_section(sections):
    assert [s.account_last4 for s in sections] == ["4321", "8765"]


def test_sections_carry_their_own_beginning_and_ending_balances(sections):
    checking, savings = sections

    assert (checking.opening_minor, checking.closing_minor) == (50000, 66802)
    assert (savings.opening_minor, savings.closing_minor) == (500000, 510004)


def test_yearless_dates_take_the_year_from_the_statement_period(sections):
    dates = [t.date for t in sections[0].transactions]

    assert dates[0] == "2025-12-08"
    assert dates[-1] == "2026-01-05"


def test_amounts_and_signs_come_from_the_lines(sections):
    amounts = [t.amount_minor for t in sections[0].transactions]

    assert amounts == [20000, -6000, -1440, 138524, -90663, -488, -30000, -13131]


def test_every_row_fits_the_running_balance(sections):
    assert all(t.fits_balance for s in sections for t in s.transactions)


def test_wrapped_description_line_is_joined(sections):
    assert sections[0].transactions[2].description == (
        "Card Purchase 12/08 Example Market Shop WA Card 1111"
    )


def test_page_furniture_is_not_added_to_a_description(sections):
    assert sections[0].transactions[4].description == "12/12 Payment To Chase Card Ending IN 9999"


def test_a_card_number_inside_a_transaction_does_not_change_the_account(sections):
    # "Payment To Chase Card Ending IN 9999" is a transaction, not the account.
    assert "9999" not in [s.account_last4 for s in sections]


def test_unsigned_amount_takes_its_sign_from_the_balance_change():
    text = (
        "Statement period 03/01/2026 - 03/31/2026\n"
        "Account Number: 1234\n"
        "Beginning Balance 100.00\n"
        "03/04 GREENLEAF GROCERY 42.10 57.90\n"
        "03/09 EXAMPLE PAYROLL 500.00 557.90\n"
        "Ending Balance 557.90\n"
    )

    (section,) = read_sections(text, currency="USD", day_first=False)

    assert [t.amount_minor for t in section.transactions] == [-4210, 50000]


def test_row_that_breaks_the_running_balance_is_marked_not_fixed():
    text = (
        "Statement period 03/01/2026 - 03/31/2026\n"
        "Beginning Balance 100.00\n"
        "03/04 GREENLEAF GROCERY -42.10 50.00\n"
        "Ending Balance 50.00\n"
    )

    (section,) = read_sections(text, currency="USD", day_first=False)

    assert section.transactions[0].fits_balance is False
    assert section.transactions[0].amount_minor == -4210


def test_indian_dates_read_day_first():
    text = (
        "Statement period 01/04/2026 - 30/04/2026\n"
        "Opening Balance 1,000.00\n"
        "03/04 UPI-SHARMA KIRANA 250.00 750.00\n"
        "Closing Balance 750.00\n"
    )

    (section,) = read_sections(text, currency="INR", day_first=True)

    assert section.transactions[0].date == "2026-04-03"


def test_card_statement_without_balance_stretch_keeps_all_lines():
    text = (
        "Opening/Closing Date 03/01/2026 - 03/31/2026\n"
        "Account Number: XXXX XXXX XXXX 5555\n"
        "Previous Balance $500.00\n"
        "Payment, Credits -$500.00\n"
        "New Balance $44.85\n"
        "ACCOUNT ACTIVITY\n"
        "03/04 GREENLEAF GROCERY 42.10\n"
        "03/09 METRO TRANSIT 2.75\n"
        "03/12 Payment Thank You-Mobile -500.00\n"
    )

    (section,) = read_sections(text, currency="USD", day_first=False)

    assert section.account_last4 == "5555"
    assert [t.amount_minor for t in section.transactions] == [4210, 275, -50000]
    assert (section.opening_minor, section.closing_minor) == (50000, 4485)


def test_yearless_dates_without_a_period_are_an_error():
    text = "Beginning Balance 100.00\n03/04 SHOP -1.00 99.00\nEnding Balance 99.00\n"

    with pytest.raises(LinesError):
        read_sections(text, currency="USD", day_first=False)


def test_period_in_words_is_found():
    period = statement_period("December 04, 2025 through January 06, 2026", day_first=False)

    assert [d.isoformat() for d in period] == ["2025-12-04", "2026-01-06"]
