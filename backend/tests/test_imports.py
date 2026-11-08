"""POST /api/imports: upload a file, nothing else; the (mock) local LLM reads it and the
code verifies every answer against the file's text."""

from conftest import (
    CHASE_MARCH_ACCOUNT,
    CHASE_MARCH_CSV,
    CHASE_MARCH_TRANSACTIONS,
    HDFC_APRIL_ACCOUNT,
    HDFC_APRIL_CSV,
    HDFC_APRIL_TRANSACTIONS,
    account_answer,
    transaction_answer,
)
from fixtures.chase_like_statement import chase_like_statement


def amounts(client) -> list[int]:
    return [t["amount_minor"] for t in client.get("/api/transactions").json()]


def test_card_statement_is_read_into_one_statement_with_signed_amounts(client, upload):
    result = upload(
        CHASE_MARCH_CSV, accounts=[CHASE_MARCH_ACCOUNT], transactions=CHASE_MARCH_TRANSACTIONS
    )

    assert result["status"] == "done"
    (statement,) = result["statements"]
    assert (statement["bank_name"], statement["account_name"], statement["currency"]) == (
        "Chase",
        "••4410",
        "USD",
    )
    assert statement["imported_count"] == 4
    assert sorted(amounts(client)) == [-125000, -4210, -275, 50000]


def test_statement_whose_balances_add_up_is_reconciled(client, upload):
    result = upload(
        HDFC_APRIL_CSV, accounts=[HDFC_APRIL_ACCOUNT], transactions=HDFC_APRIL_TRANSACTIONS
    )

    (statement,) = result["statements"]
    assert statement["reconciliation_status"] == "reconciled"
    assert (statement["opening_balance_minor"], statement["closing_balance_minor"]) == (
        12470678,
        26345678,
    )
    assert statement["bank_id"] == "hdfc"


def test_one_file_with_two_accounts_becomes_two_statements(client, upload):
    content = (
        b"Example Bank\nChecking 1111 Savings 2222\n"
        b"03/04 GREENLEAF GROCERY -42.10\n03/05 TRANSFER TO SAVINGS -100.00\n"
        b"03/05 TRANSFER FROM CHECKING 100.00\n"
    )
    result = upload(
        content,
        accounts=[
            account_answer(bank_name="Example Bank", last4="1111"),
            account_answer(bank_name="Example Bank", last4="2222"),
        ],
        transactions=[
            transaction_answer("2026-03-04", "GREENLEAF GROCERY", "42.10", "out", "1111"),
            transaction_answer("2026-03-05", "TRANSFER TO SAVINGS", "100.00", "out", "1111"),
            transaction_answer("2026-03-05", "TRANSFER FROM CHECKING", "100.00", "in", "2222"),
        ],
    )

    counts = [(s["account_name"], s["imported_count"]) for s in result["statements"]]
    assert counts == [("••1111", 2), ("••2222", 1)]


def test_amount_not_in_the_statement_is_kept_but_needs_review(client, upload):
    upload(
        CHASE_MARCH_CSV,
        accounts=[CHASE_MARCH_ACCOUNT],
        transactions=[transaction_answer("2026-03-04", "GREENLEAF GROCERY", "99.99", "out")],
    )

    (transaction,) = client.get("/api/transactions").json()
    assert transaction["amount_minor"] == -9999
    assert transaction["needs_review"] is True


def test_date_outside_the_statement_period_needs_review(client, upload):
    upload(
        CHASE_MARCH_CSV,
        accounts=[CHASE_MARCH_ACCOUNT],
        period=("2026-03-01", "2026-03-31"),
        transactions=[transaction_answer("2025-07-04", "GREENLEAF GROCERY", "42.10", "out")],
    )

    assert client.get("/api/transactions").json()[0]["needs_review"] is True


def test_verified_transaction_does_not_need_review(client, upload):
    upload(
        CHASE_MARCH_CSV,
        accounts=[CHASE_MARCH_ACCOUNT],
        period=("2026-03-01", "2026-03-31"),
        transactions=[transaction_answer("2026-03-04", "GREENLEAF GROCERY", "42.10", "out")],
    )

    assert client.get("/api/transactions").json()[0]["needs_review"] is False


def test_bank_name_and_number_not_in_the_statement_are_dropped(client, upload):
    result = upload(
        CHASE_MARCH_CSV,
        accounts=[account_answer(bank_name="Imaginary Bank", last4="9999")],
        transactions=CHASE_MARCH_TRANSACTIONS,
    )

    (statement,) = result["statements"]
    assert (statement["bank_name"], statement["account_name"]) == ("Unknown bank", "Account")


def test_balance_not_printed_in_the_statement_is_ignored(client, upload):
    result = upload(
        CHASE_MARCH_CSV,
        accounts=[{**CHASE_MARCH_ACCOUNT, "opening_balance": "777.00", "closing_balance": "1.00"}],
        transactions=CHASE_MARCH_TRANSACTIONS,
    )

    assert result["statements"][0]["reconciliation_status"] == "unverifiable"


def test_transaction_without_a_usable_date_is_counted_as_rejected(client, upload):
    result = upload(
        CHASE_MARCH_CSV,
        accounts=[CHASE_MARCH_ACCOUNT],
        transactions=[
            transaction_answer("2026-03-04", "GREENLEAF GROCERY", "42.10", "out"),
            transaction_answer("March-ish", "METRO TRANSIT", "2.75", "out"),
        ],
    )

    assert result["rejected_count"] == 1
    assert result["statements"][0]["imported_count"] == 1


def test_file_without_transactions_fails_with_a_reason(client, upload):
    result = upload(b"just some notes\n", accounts=[], transactions=[])

    assert result["status"] == "failed"
    assert result["error"] == "No transactions were found in this file."


def test_without_the_local_model_the_import_fails_with_a_reason(client):
    response = client.post("/api/imports", files={"file": ("s.csv", CHASE_MARCH_CSV, "text/csv")})

    result = client.get(f"/api/imports/{response.json()['id']}").json()
    assert result["status"] == "failed"
    assert result["error"] == "The local AI is not running. Start Ollama and upload again."


def test_progress_reaches_every_part_of_the_statement(client, upload):
    result = upload(
        CHASE_MARCH_CSV, accounts=[CHASE_MARCH_ACCOUNT], transactions=CHASE_MARCH_TRANSACTIONS
    )

    assert result["progress_total"] >= 1
    assert result["progress_done"] == result["progress_total"]


def test_same_file_again_is_reported(client, upload):
    first = upload(
        CHASE_MARCH_CSV, accounts=[CHASE_MARCH_ACCOUNT], transactions=CHASE_MARCH_TRANSACTIONS
    )

    response = client.post("/api/imports", files={"file": ("s.csv", CHASE_MARCH_CSV, "text/csv")})

    assert response.status_code == 409
    assert response.json()["error"]["details"] == {"import_id": first["id"]}


def test_failed_file_can_be_uploaded_again(client, upload):
    client.post("/api/imports", files={"file": ("s.csv", CHASE_MARCH_CSV, "text/csv")})

    result = upload(
        CHASE_MARCH_CSV, accounts=[CHASE_MARCH_ACCOUNT], transactions=CHASE_MARCH_TRANSACTIONS
    )

    assert result["status"] == "done"


def test_overlapping_statements_do_not_count_a_transaction_twice(client, upload):
    upload(CHASE_MARCH_CSV, accounts=[CHASE_MARCH_ACCOUNT], transactions=CHASE_MARCH_TRANSACTIONS)
    april = CHASE_MARCH_CSV + b"04/02/2026,CORNER CAFE,-15.00\n"

    result = upload(
        april,
        accounts=[CHASE_MARCH_ACCOUNT],
        transactions=[
            *CHASE_MARCH_TRANSACTIONS,
            transaction_answer("2026-04-02", "CORNER CAFE", "15.00", "out"),
        ],
    )

    (statement,) = result["statements"]
    assert (statement["imported_count"], statement["duplicate_count"]) == (1, 4)


def test_binary_file_that_is_not_a_pdf_is_refused(client):
    response = client.post(
        "/api/imports", files={"file": ("photo.png", b"\x89PNG\r\n\x1a\n\xff\xfe", "image/png")}
    )

    assert response.status_code == 415


def test_encrypted_pdf_asks_for_its_password_before_any_work(client):
    response = client.post(
        "/api/imports",
        files={"file": ("s.pdf", chase_like_statement(password="s3cret"), "application/pdf")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "pdf_password_required"


def test_wrong_password_is_reported(client):
    response = client.post(
        "/api/imports",
        data={"password": "nope"},
        files={"file": ("s.pdf", chase_like_statement(password="s3cret"), "application/pdf")},
    )

    assert response.json()["error"]["code"] == "pdf_password_invalid"


CHASE_PDF_ACCOUNTS = [
    account_answer(
        bank_name="JPMorgan Chase Bank", last4="4321", opening="$500.00", closing="$668.02"
    )
]
CHASE_PDF_TRANSACTIONS = [
    transaction_answer("2025-12-08", "Example Cable Co PPD ID: 0000000001", "60.00", "out", "4321")
]


def test_password_is_saved_under_the_bank_found_in_the_file(client, upload, memory_keychain):
    upload(
        chase_like_statement(password="s3cret"),
        accounts=CHASE_PDF_ACCOUNTS,
        transactions=CHASE_PDF_TRANSACTIONS,
        password="s3cret",
    )

    assert memory_keychain.get_password("TheAccountant", "chase") == "s3cret"


def test_saved_password_opens_the_next_statement_without_asking(client, upload):
    upload(
        chase_like_statement(password="s3cret"),
        accounts=CHASE_PDF_ACCOUNTS,
        transactions=CHASE_PDF_TRANSACTIONS,
        password="s3cret",
    )

    response = client.post(
        "/api/imports",
        files={
            "file": (
                "b.pdf",
                chase_like_statement(password="s3cret", street="2 OTHER ROAD"),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 202


def test_password_not_saved_when_asked_not_to(client, memory_keychain):
    client.app.state.llm.script(
        {"accounts": CHASE_PDF_ACCOUNTS, "period_start": None, "period_end": None},
        {"transactions": CHASE_PDF_TRANSACTIONS},
    )

    response = client.post(
        "/api/imports",
        data={"password": "s3cret", "remember": "false"},
        files={"file": ("s.pdf", chase_like_statement(password="s3cret"), "application/pdf")},
    )

    assert client.get(f"/api/imports/{response.json()['id']}").json()["status"] == "done"
    assert memory_keychain.get_password("TheAccountant", "chase") is None


def test_pdf_text_reaches_the_model_with_its_columns(client, upload):
    upload(chase_like_statement(), accounts=CHASE_PDF_ACCOUNTS, transactions=CHASE_PDF_TRANSACTIONS)

    transactions_prompt = client.app.state.llm.prompts[1]
    assert "Example Cable Co PPD ID: 0000000001 | -60.00 | 640.00" in transactions_prompt


def test_unknown_import_is_not_found(client):
    assert client.get("/api/imports/999").json()["error"]["code"] == "import_not_found"


def test_digits_from_the_middle_of_an_account_number_are_not_its_last_four(client, upload):
    content = CHASE_MARCH_CSV.replace(
        b"Chase card ending 4410", b"Chase Account Number: 000000111114321"
    )

    result = upload(
        content,
        accounts=[account_answer(bank_name="Chase", last4="1432")],
        transactions=CHASE_MARCH_TRANSACTIONS,
    )

    assert result["statements"][0]["account_name"] == "Account"


def test_the_real_last_four_of_an_account_number_is_kept(client, upload):
    content = CHASE_MARCH_CSV.replace(
        b"Chase card ending 4410", b"Chase Account Number: 000000111114321"
    )

    result = upload(
        content,
        accounts=[account_answer(bank_name="Chase", last4="4321")],
        transactions=CHASE_MARCH_TRANSACTIONS,
    )

    assert result["statements"][0]["account_name"] == "••4321"
