from pathlib import Path

import pytest

from app.statements.csv_import import (
    CsvError,
    CsvMapping,
    apply_mapping,
    read_rows,
    suggest_mapping,
    to_transactions,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "statements"


def rows_of(relative_path: str) -> list[list[str]]:
    return read_rows((FIXTURES / relative_path).read_bytes())


CHASE_MAPPING = CsvMapping(
    header_row=0,
    date_column="Transaction Date",
    description_column="Description",
    amount_mode="signed",
    amount_column="Amount",
    date_format="MM/DD/YYYY",
)
HDFC_MAPPING = CsvMapping(
    header_row=3,
    date_column="Date",
    description_column="Narration",
    amount_mode="debit_credit",
    debit_column="Withdrawal Amt.",
    credit_column="Deposit Amt.",
    date_format="DD/MM/YY",
)


def test_chase_layout_suggests_signed_amount_column():
    suggestion = suggest_mapping(rows_of("chase/card_2026_03.csv"), "MM/DD/YYYY")

    assert suggestion == {
        "header_row": 0,
        "date_column": "Transaction Date",
        "description_column": "Description",
        "amount_mode": "signed",
        "amount_column": "Amount",
        "debit_column": None,
        "credit_column": None,
        "date_format": "MM/DD/YYYY",
    }


def test_hdfc_layout_suggests_header_below_preamble_and_separate_columns():
    suggestion = suggest_mapping(rows_of("hdfc/savings_2026_04.csv"), "DD/MM/YY")

    assert suggestion == {
        "header_row": 3,
        "date_column": "Date",
        "description_column": "Narration",
        "amount_mode": "debit_credit",
        "amount_column": None,
        "debit_column": "Withdrawal Amt.",
        "credit_column": "Deposit Amt.",
        "date_format": "DD/MM/YY",
    }


def test_signed_mapping_keeps_the_file_sign():
    parsed, skipped = apply_mapping(rows_of("chase/card_2026_03.csv"), CHASE_MAPPING, "USD")

    assert [(row.date, row.amount_minor, row.description) for row in parsed] == [
        ("2026-03-04", -4210, "GREENLEAF GROCERY"),
        ("2026-03-09", -275, "METRO TRANSIT"),
        ("2026-03-12", 50000, "PAYMENT THANK YOU"),
        ("2026-03-20", -125000, "EXAMPLE ELECTRONICS"),
    ]
    assert skipped == 0


def test_inverted_mapping_makes_positive_card_charges_money_out():
    mapping = CsvMapping(
        header_row=0,
        date_column="Trans. Date",
        description_column="Description",
        amount_mode="inverted",
        amount_column="Amount",
        date_format="MM/DD/YYYY",
    )

    parsed, _ = apply_mapping(rows_of("discover/card_2026_03.csv"), mapping, "USD")

    assert [row.amount_minor for row in parsed] == [-4210, 30000]


def test_debit_credit_mapping_reads_indian_grouping_and_day_first_dates():
    parsed, _ = apply_mapping(rows_of("hdfc/savings_2026_04.csv"), HDFC_MAPPING, "INR")

    assert [(row.date, row.amount_minor) for row in parsed] == [
        ("2026-04-03", -125000),
        ("2026-04-05", 15000000),
        ("2026-04-11", -1000000),
    ]


def test_footer_row_without_amount_is_skipped_and_counted():
    _, skipped = apply_mapping(rows_of("hdfc/savings_2026_04.csv"), HDFC_MAPPING, "INR")

    assert skipped == 1


def test_raw_cells_are_kept_by_header():
    parsed, _ = apply_mapping(rows_of("hdfc/savings_2026_04.csv"), HDFC_MAPPING, "INR")

    assert parsed[0].raw_cells["Chq./Ref.No."] == "0000000001"


def test_row_with_unreadable_amount_stops_the_import_with_its_row_number():
    rows = [["Date", "Description", "Amount"], ["03/04/2026", "SHOP", "12x"]]
    mapping = CHASE_MAPPING.model_copy(update={"date_column": "Date"})

    with pytest.raises(CsvError, match="row 2") as raised:
        apply_mapping(rows, mapping, "USD")

    assert raised.value.code == "csv_row_invalid"


def test_row_with_both_debit_and_credit_is_rejected():
    rows = [
        ["Date", "Narration", "Withdrawal Amt.", "Deposit Amt."],
        ["03/04/26", "SHOP", "10.00", "10.00"],
    ]
    mapping = HDFC_MAPPING.model_copy(update={"header_row": 0})

    with pytest.raises(CsvError) as raised:
        apply_mapping(rows, mapping, "INR")

    assert raised.value.code == "csv_row_invalid"


def test_mapping_naming_a_missing_column_is_invalid():
    mapping = CHASE_MAPPING.model_copy(update={"amount_column": "Value"})

    with pytest.raises(CsvError) as raised:
        apply_mapping(rows_of("chase/card_2026_03.csv"), mapping, "USD")

    assert raised.value.code == "csv_mapping_invalid"


def test_debit_credit_mode_requires_both_columns():
    with pytest.raises(ValueError, match="debit_column and credit_column"):
        CsvMapping(
            header_row=0,
            date_column="Date",
            description_column="Narration",
            amount_mode="debit_credit",
            debit_column="Withdrawal Amt.",
            date_format="DD/MM/YY",
        )


def test_non_utf8_file_is_unreadable():
    with pytest.raises(CsvError) as raised:
        read_rows(b"Date,Amount\n03/04/2026,\xff\xfe\n")

    assert raised.value.code == "csv_unreadable"


def test_identical_rows_in_one_statement_get_different_fingerprints():
    rows = [
        ["Transaction Date", "Description", "Amount"],
        ["03/04/2026", "METRO TRANSIT", "-2.75"],
        ["03/04/2026", "METRO TRANSIT", "-2.75"],
    ]

    parsed, _ = apply_mapping(rows, CHASE_MAPPING, "USD")
    first, second = to_transactions(parsed, account_id=1)

    assert first["fingerprint"] != second["fingerprint"]


def test_same_row_in_two_statements_gets_the_same_fingerprint():
    march, _ = apply_mapping(rows_of("chase/card_2026_03.csv"), CHASE_MAPPING, "USD")
    april, _ = apply_mapping(rows_of("chase/card_2026_04.csv"), CHASE_MAPPING, "USD")

    march_electronics = to_transactions(march, account_id=1)[3]
    april_electronics = to_transactions(april, account_id=1)[1]

    assert march_electronics["fingerprint"] == april_electronics["fingerprint"]


def test_description_case_and_spacing_do_not_change_the_fingerprint():
    rows = [
        ["Transaction Date", "Description", "Amount"],
        ["03/04/2026", "Metro  Transit", "-2.75"],
    ]
    upper = [rows[0], ["03/04/2026", "METRO TRANSIT", "-2.75"]]

    spaced, _ = apply_mapping(rows, CHASE_MAPPING, "USD")
    plain, _ = apply_mapping(upper, CHASE_MAPPING, "USD")

    assert (
        to_transactions(spaced, 1)[0]["fingerprint"] == to_transactions(plain, 1)[0]["fingerprint"]
    )


def test_same_row_in_two_accounts_gets_different_fingerprints():
    parsed, _ = apply_mapping(rows_of("chase/card_2026_03.csv"), CHASE_MAPPING, "USD")

    assert (
        to_transactions(parsed, 1)[0]["fingerprint"] != to_transactions(parsed, 2)[0]["fingerprint"]
    )
