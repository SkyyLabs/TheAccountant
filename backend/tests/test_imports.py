"""POST /api/imports: the user uploads a file and nothing else."""

from fixtures.chase_like_statement import chase_like_statement
from fpdf import FPDF


def post(client, name: str, content: bytes, **fields):
    mime = "application/pdf" if content.startswith(b"%PDF") else "text/csv"
    return client.post(
        "/api/imports",
        data={key: str(value) for key, value in fields.items()},
        files={"file": (name, content, mime)},
    )


def text_pdf(lines: list[str]) -> bytes:
    document = FPDF()
    document.add_page()
    document.set_font("Helvetica", size=9)
    for index, line in enumerate(lines):
        document.text(15, 20 + index * 6, line)
    return bytes(document.output())


def statements(response) -> list[tuple]:
    return [
        (
            s["bank_id"],
            s["account_name"],
            s["currency"],
            s["reconciliation_status"],
            s["imported_count"],
        )
        for s in response.json()["statements"]
    ]


def test_bank_pdf_with_two_accounts_becomes_two_reconciled_statements(client):
    response = post(client, "statement.pdf", chase_like_statement())

    assert response.status_code == 201
    assert statements(response) == [
        ("chase", "••4321", "USD", "reconciled", 8),
        ("chase", "••8765", "USD", "reconciled", 3),
    ]


def test_transfers_between_the_two_accounts_land_in_each(client):
    post(client, "statement.pdf", chase_like_statement())

    transfers = [
        (t["account_name"], t["amount_minor"])
        for t in client.get("/api/transactions", params={"q": "Transaction#: 11111111111"}).json()
    ]

    assert sorted(transfers) == [("••4321", 20000), ("••8765", -20000)]


def test_same_file_again_is_reported_with_its_statements(client):
    first = post(client, "statement.pdf", chase_like_statement()).json()["statements"]

    response = post(client, "statement.pdf", chase_like_statement())

    assert response.status_code == 409
    assert response.json()["error"]["details"] == {"statement_ids": [s["id"] for s in first]}


def test_encrypted_pdf_asks_for_its_password(client):
    response = post(client, "statement.pdf", chase_like_statement(password="s3cret"))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "pdf_password_required"


def test_wrong_password_is_reported(client):
    response = post(client, "s.pdf", chase_like_statement(password="s3cret"), password="nope")

    assert response.json()["error"]["code"] == "pdf_password_invalid"


def test_password_is_saved_under_the_bank_found_in_the_file(client, memory_keychain):
    post(client, "s.pdf", chase_like_statement(password="s3cret"), password="s3cret")

    assert memory_keychain.get_password("TheAccountant", "chase") == "s3cret"


def test_saved_password_opens_the_next_statement_without_asking(client):
    post(client, "a.pdf", chase_like_statement(password="s3cret"), password="s3cret")

    response = post(client, "b.pdf", chase_like_statement(password="s3cret", street="2 OTHER ROAD"))

    assert response.status_code == 201


def test_password_not_saved_when_asked_not_to(client, memory_keychain):
    post(
        client,
        "s.pdf",
        chase_like_statement(password="s3cret"),
        password="s3cret",
        remember="false",
    )

    assert memory_keychain.get_password("TheAccountant", "chase") is None


def test_csv_with_bank_and_account_in_its_header_lines_needs_no_model(client):
    content = (
        b"HDFC BANK Ltd.,,,,\n"
        b"Account No : XXXXXXXX4821,,,,\n"
        b'Opening Balance,"1,000.00",,,\n'
        b"Date,Narration,Withdrawal Amt.,Deposit Amt.,Closing Balance\n"
        b"03/04/26,UPI-SHARMA KIRANA STORE,250.00,,750.00\n"
        b'05/04/26,SALARY EXAMPLE CORP,,"1,000.00","1,750.00"\n'
        b'Closing Balance,"1,750.00",,,\n'
    )

    response = post(client, "statement.csv", content)

    assert statements(response) == [("hdfc", "••4821", "INR", "reconciled", 2)]
    dates = [t["date"] for t in client.get("/api/transactions").json()]
    assert dates == ["2026-04-05", "2026-04-03"]


def test_unknown_bank_named_in_the_file_is_created(client):
    content = (
        b"Acme Federal Credit Union,,,\n"
        b"Checking Account ****5566,,,\n"
        b"Posted,Payee,Money Out,Money In\n"
        b"03/04/2026,GREENLEAF GROCERY,42.10,\n"
        b'03/09/2026,EXAMPLE PAYROLL,,"1,500.00"\n'
    )
    client.app.state.llm.script(
        {
            "bank_name": "Acme Federal Credit Union",
            "country": "US",
            "account_type": "bank",
            "account_last4": "5566",
            "header_line": 3,
            "date_column": "Posted",
            "description_column": "Payee",
            "amount_mode": "debit_credit",
            "amount_column": None,
            "debit_column": "Money Out",
            "credit_column": "Money In",
            "opening_balance_label": None,
            "closing_balance_label": None,
        }
    )

    response = post(client, "export.csv", content)

    statement = response.json()["statements"][0]
    assert (statement["bank_name"], statement["account_name"]) == (
        "Acme Federal Credit Union",
        "••5566",
    )


def test_bank_name_the_model_made_up_is_ignored(client):
    content = b"Date,Description,Amount\n03/04/2026,GREENLEAF GROCERY,-42.10\n"
    client.app.state.llm.script(
        {
            "bank_name": "Imaginary Bank",
            "country": "US",
            "account_type": "bank",
            "account_last4": "9999",
            "header_line": 1,
            "date_column": "Date",
            "description_column": "Description",
            "amount_mode": "signed",
            "amount_column": "Amount",
            "debit_column": None,
            "credit_column": None,
            "opening_balance_label": None,
            "closing_balance_label": None,
        }
    )

    statement = post(client, "export.csv", content).json()["statements"][0]

    assert (statement["bank_name"], statement["account_name"]) == ("Unknown bank", "Account")


def test_next_file_from_the_same_account_reuses_its_layout_without_the_model(client):
    first = (
        b"HDFC BANK Ltd.,,,\nAccount No : XXXXXXXX4821,,,\n"
        b"Date,Narration,Withdrawal Amt.,Deposit Amt.\n03/04/26,SHOP,250.00,\n"
    )
    second = first.replace(b"03/04/26,SHOP", b"09/04/26,CAFE")
    post(client, "a.csv", first)

    response = post(client, "b.csv", second)

    assert response.status_code == 201
    layout_questions = [p for p in client.app.state.llm.prompts if p.startswith("Statement:")]
    assert len(layout_questions) == 1  # the first file only


def test_card_statement_charges_are_money_out_and_reconcile(client):
    content = text_pdf(
        [
            "Discover it Card",
            "Account Number: XXXX XXXX XXXX 9012",
            "Opening/Closing Date 03/01/2026 - 03/31/2026",
            "Previous Balance $500.00",
            "New Balance $44.85",
            "Minimum Payment Due $25.00",
            "TRANSACTIONS",
            "03/04 GREENLEAF GROCERY 42.10",
            "03/09 METRO TRANSIT 2.75",
            "03/12 INTERNET PAYMENT - THANK YOU -500.00",
        ]
    )

    response = post(client, "discover.pdf", content)

    statement = response.json()["statements"][0]
    assert (statement["bank_id"], statement["reconciliation_status"]) == ("discover", "reconciled")
    amounts = sorted(t["amount_minor"] for t in client.get("/api/transactions").json())
    assert amounts == [-4210, -275, 50000]


def test_row_that_breaks_the_running_balance_is_flagged(client):
    content = text_pdf(
        [
            "JPMorgan Chase Bank, N.A.",
            "March 01, 2026 through March 31, 2026",
            "Account Number: 000000333331234",
            "Beginning Balance $100.00",
            "03/04 GREENLEAF GROCERY -42.10 50.00",
            "Ending Balance $50.00",
        ]
    )

    statement = post(client, "s.pdf", content).json()["statements"][0]

    assert statement["reconciliation_status"] == "unreconciled"
    assert client.get("/api/transactions").json()[0]["needs_review"] is True


def test_file_with_no_transactions_is_unreadable(client):
    response = post(client, "notes.csv", b"just,some\nwords,here\n")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "statement_unreadable"


def test_rows_breaking_the_running_balance_flag_the_statement_even_when_totals_agree(client):
    # Both rows show balance 80.00; the totals (100.00 - 20.00 = 80.00) still agree.
    content = text_pdf(
        [
            "JPMorgan Chase Bank, N.A.",
            "March 01, 2026 through March 31, 2026",
            "Account Number: 000000333331234",
            "Beginning Balance $100.00",
            "03/04 GREENLEAF GROCERY -10.00 80.00",
            "03/05 METRO TRANSIT -10.00 80.00",
            "Ending Balance $80.00",
        ]
    )

    statement = post(client, "s.pdf", content).json()["statements"][0]

    assert statement["reconciliation_status"] == "unreconciled"


def test_bank_and_account_can_come_from_the_file_name_alone(client):
    content = (
        b"Transaction Date,Post Date,Description,Category,Type,Amount,Memo\n"
        b"03/04/2026,03/05/2026,GREENLEAF GROCERY,Groceries,Sale,-42.10,\n"
    )

    statement = post(client, "Chase4410_Activity20260301.CSV", content).json()["statements"][0]

    assert (statement["bank_id"], statement["account_name"]) == ("chase", "••4410")
