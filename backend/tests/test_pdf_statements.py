import json

from fpdf import FPDF

HEADER = ("Date", "Narration", "Withdrawal Amt.", "Deposit Amt.")
APRIL = [
    HEADER,
    ("03/04/26", "UPI-SHARMA KIRANA STORE", "1,250.00", ""),
    ("05/04/26", "SALARY EXAMPLE CORP", "", "1,50,000.00"),
]
MAPPING = {
    "header_row": 0,
    "date_column": "Date",
    "description_column": "Narration",
    "amount_mode": "debit_credit",
    "debit_column": "Withdrawal Amt.",
    "credit_column": "Deposit Amt.",
    "date_format": "DD/MM/YY",
}


def hdfc_account(client) -> int:
    return client.post(
        "/api/accounts", json={"bank_id": "hdfc", "type": "bank", "name": "Savings"}
    ).json()["id"]


def post_pdf(client, account_id: int, content: bytes, **fields):
    data = {"account_id": str(account_id)}
    for name, value in fields.items():
        data[name] = json.dumps(value) if name == "mapping" else str(value)
    return client.post(
        "/api/statements",
        data=data,
        files={"file": ("statement.pdf", content, "application/pdf")},
    )


def test_pdf_tables_go_through_the_mapping_flow(client, statement_pdf):
    account_id = hdfc_account(client)

    response = post_pdf(client, account_id, statement_pdf([APRIL]))

    assert response.status_code == 422
    details = response.json()["error"]["details"]
    assert details["rows"][0] == list(HEADER)
    assert details["suggested_mapping"]["amount_mode"] == "debit_credit"


def test_pdf_with_mapping_imports_amounts_and_dates(client, statement_pdf):
    account_id = hdfc_account(client)

    response = post_pdf(client, account_id, statement_pdf([APRIL]), mapping=MAPPING)

    assert response.status_code == 201
    assert response.json()["imported_count"] == 2
    transactions = client.get("/api/transactions").json()
    assert [(t["date"], t["amount_minor"]) for t in transactions] == [
        ("2026-04-05", 15000000),
        ("2026-04-03", -125000),
    ]


def test_header_repeated_on_each_page_is_not_a_transaction(client, statement_pdf):
    account_id = hdfc_account(client)
    second_page = [HEADER, ("11/04/26", "ATM WDL EXAMPLE BRANCH", "10,000.00", "")]

    response = post_pdf(client, account_id, statement_pdf([APRIL, second_page]), mapping=MAPPING)

    assert response.json()["imported_count"] == 3


def test_encrypted_pdf_without_a_password_asks_for_one(client, statement_pdf):
    account_id = hdfc_account(client)

    response = post_pdf(client, account_id, statement_pdf([APRIL], password="s3cret"))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "pdf_password_required"


def test_wrong_password_is_invalid(client, statement_pdf):
    account_id = hdfc_account(client)

    response = post_pdf(
        client, account_id, statement_pdf([APRIL], password="s3cret"), password="wrong"
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "pdf_password_invalid"


def test_correct_password_is_remembered_for_the_bank(client, statement_pdf, memory_keychain):
    account_id = hdfc_account(client)

    post_pdf(client, account_id, statement_pdf([APRIL], password="s3cret"), password="s3cret")

    assert memory_keychain.get_password("TheAccountant", "hdfc") == "s3cret"


def test_remembered_password_opens_the_next_pdf(client, statement_pdf):
    account_id = hdfc_account(client)
    post_pdf(
        client,
        account_id,
        statement_pdf([APRIL], password="s3cret"),
        password="s3cret",
        mapping=MAPPING,
    )
    may = [HEADER, ("02/05/26", "CORNER CAFE", "150.00", "")]

    response = post_pdf(client, account_id, statement_pdf([may], password="s3cret"))

    assert response.status_code == 201


def test_password_not_remembered_when_asked_not_to(client, statement_pdf, memory_keychain):
    account_id = hdfc_account(client)

    post_pdf(
        client,
        account_id,
        statement_pdf([APRIL], password="s3cret"),
        password="s3cret",
        remember="false",
    )

    assert memory_keychain.get_password("TheAccountant", "hdfc") is None


def test_wrong_password_does_not_replace_the_saved_one(client, statement_pdf, memory_keychain):
    account_id = hdfc_account(client)
    memory_keychain.set_password("TheAccountant", "hdfc", "s3cret")

    post_pdf(client, account_id, statement_pdf([APRIL], password="s3cret"), password="wrong")

    assert memory_keychain.get_password("TheAccountant", "hdfc") == "s3cret"


def test_saved_password_that_no_longer_works_asks_again(client, statement_pdf, memory_keychain):
    account_id = hdfc_account(client)
    memory_keychain.set_password("TheAccountant", "hdfc", "old-password")

    response = post_pdf(client, account_id, statement_pdf([APRIL], password="new-password"))

    assert response.json()["error"]["code"] == "pdf_password_required"


def test_password_is_never_echoed_in_the_response(client, statement_pdf):
    account_id = hdfc_account(client)

    response = post_pdf(
        client,
        account_id,
        statement_pdf([APRIL], password="s3cret"),
        password="s3cret",
        mapping=MAPPING,
    )

    assert "s3cret" not in response.text


def test_preview_opens_an_encrypted_pdf_with_its_password(client, statement_pdf):
    account_id = hdfc_account(client)

    response = client.post(
        "/api/statements/preview",
        data={"account_id": str(account_id), "mapping": json.dumps(MAPPING), "password": "s3cret"},
        files={"file": ("s.pdf", statement_pdf([APRIL], password="s3cret"), "application/pdf")},
    )

    assert response.status_code == 200
    assert response.json()["row_count"] == 2


def test_pdf_without_tables_says_so(client):
    document = FPDF()
    document.add_page()
    document.set_font("Helvetica", size=10)
    document.cell(0, 6, "03/04/26 UPI-SHARMA KIRANA STORE 1,250.00")
    account_id = hdfc_account(client)

    response = post_pdf(client, account_id, bytes(document.output()))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "pdf_no_tables"
