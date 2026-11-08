from app.llm.base import LlmError, LlmUnavailable
from app.llm.mock import MockProvider
from app.statements.layout import propose_layout

ROWS = [
    ["EXAMPLE BANK STATEMENT"],
    ["Opening Balance 1,00,000.00"],
    ["Txn Dt", "Particulars", "Dr", "Cr"],
    ["03/04/26", "UPI-SHARMA KIRANA STORE", "1,250.00", ""],
    ["05/04/26", "SALARY EXAMPLE CORP", "", "1,50,000.00"],
    ["Closing Balance 2,48,750.00"],
]
GOOD_ANSWER = {
    "header_line": 3,
    "date_column": "Txn Dt",
    "description_column": "Particulars",
    "amount_mode": "debit_credit",
    "amount_column": None,
    "debit_column": "Dr",
    "credit_column": "Cr",
    "opening_balance_label": "Opening Balance",
    "closing_balance_label": "Closing Balance",
}


def propose(provider):
    return propose_layout(
        ROWS, provider, account_type="bank", currency="INR", default_date_format="DD/MM/YYYY"
    )


def test_valid_llm_proposal_is_used():
    provider = MockProvider()
    provider.script(GOOD_ANSWER)

    suggestion, source = propose(provider)

    assert source == "llm"
    assert suggestion == {
        "header_row": 2,
        "date_column": "Txn Dt",
        "description_column": "Particulars",
        "amount_mode": "debit_credit",
        "amount_column": None,
        "debit_column": "Dr",
        "credit_column": "Cr",
        "date_format": "DD/MM/YY",
        "opening_balance_label": "Opening Balance",
        "closing_balance_label": "Closing Balance",
    }


def test_proposal_naming_a_missing_column_is_retried_once():
    provider = MockProvider()
    provider.script({**GOOD_ANSWER, "debit_column": "Debit"}, GOOD_ANSWER)

    _, source = propose(provider)

    assert source == "llm"
    assert len(provider.prompts) == 2


def test_two_bad_answers_fall_back_to_the_heuristic():
    provider = MockProvider()
    provider.script(LlmError("not json"), {"header_line": 99})

    suggestion, source = propose(provider)

    assert source == "heuristic"
    assert suggestion["opening_balance_label"] == "opening balance"
    assert suggestion["closing_balance_label"] == "closing balance"


def test_unavailable_llm_falls_back_without_a_retry():
    provider = MockProvider()
    provider.script(LlmUnavailable("ollama not running"))

    _, source = propose(provider)

    assert source == "heuristic"
    assert len(provider.prompts) == 1


def test_unused_amount_columns_are_cleared():
    provider = MockProvider()
    provider.script({**GOOD_ANSWER, "amount_column": "Dr"})

    suggestion, _ = propose(provider)

    assert suggestion["amount_column"] is None


def test_prompt_shows_numbered_lines_with_cells():
    provider = MockProvider()
    provider.script(GOOD_ANSWER)

    propose(provider)

    assert "3: Txn Dt | Particulars | Dr | Cr" in provider.prompts[0]


def test_date_format_is_the_first_in_the_bank_order_that_parses_every_row():
    provider = MockProvider()
    provider.script(GOOD_ANSWER)

    suggestion, _ = propose(provider)

    # 03/04/26 also parses as MM/DD/YY; an Indian bank reads day first.
    assert suggestion["date_format"] == "DD/MM/YY"


def test_ambiguous_dates_follow_the_bank_default_format():
    rows = [["Date", "Details", "Amount"], ["03/04/2026", "SHOP", "-1.00"]]
    provider = MockProvider()
    provider.script(
        {
            **GOOD_ANSWER,
            "header_line": 1,
            "date_column": "Date",
            "description_column": "Details",
            "amount_mode": "signed",
            "amount_column": "Amount",
        }
    )

    suggestion, _ = propose_layout(
        rows, provider, account_type="bank", currency="INR", default_date_format="DD/MM/YYYY"
    )

    assert suggestion["date_format"] == "DD/MM/YYYY"


def test_header_line_off_by_one_is_corrected_by_code():
    provider = MockProvider()
    provider.script({**GOOD_ANSWER, "header_line": 4})

    suggestion, source = propose(provider)

    assert source == "llm"
    assert suggestion["header_row"] == 2


def test_card_with_positive_charges_is_switched_to_inverted():
    rows = [
        ["Trans. Date", "Description", "Amount"],
        ["03/04/2026", "GREENLEAF GROCERY", "42.10"],
        ["03/09/2026", "METRO TRANSIT", "2.75"],
        ["03/15/2026", "INTERNET PAYMENT", "-300.00"],
    ]
    provider = MockProvider()
    provider.script(
        {
            **GOOD_ANSWER,
            "header_line": 1,
            "date_column": "Trans. Date",
            "description_column": "Description",
            "amount_mode": "signed",
            "amount_column": "Amount",
        }
    )

    suggestion, _ = propose_layout(
        rows, provider, account_type="credit_card", currency="USD", default_date_format="MM/DD/YYYY"
    )

    assert suggestion["amount_mode"] == "inverted"


def test_bank_account_sign_is_left_as_proposed():
    provider = MockProvider()
    provider.script({**GOOD_ANSWER})

    suggestion, _ = propose(provider)

    assert suggestion["amount_mode"] == "debit_credit"


def test_balance_label_without_a_readable_amount_is_replaced_by_a_known_label():
    provider = MockProvider()
    provider.script({**GOOD_ANSWER, "closing_balance_label": "EXAMPLE BANK"})

    suggestion, _ = propose(provider)

    assert suggestion["closing_balance_label"] == "closing balance"
    assert suggestion["opening_balance_label"] == "Opening Balance"
