import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "statements"

HDFC_MAPPING = {
    "header_row": 3,
    "date_column": "Date",
    "description_column": "Narration",
    "amount_mode": "debit_credit",
    "debit_column": "Withdrawal Amt.",
    "credit_column": "Deposit Amt.",
    "date_format": "DD/MM/YY",
}


def test_imported_transactions_are_listed_newest_first_with_their_account(client):
    account_id = client.post(
        "/api/accounts", json={"bank_id": "hdfc", "type": "bank", "name": "Savings"}
    ).json()["id"]
    content = (FIXTURES / "hdfc/savings_2026_04.csv").read_bytes()
    statement_id = client.post(
        "/api/statements",
        data={"account_id": str(account_id), "mapping": json.dumps(HDFC_MAPPING)},
        files={"file": ("savings.csv", content, "text/csv")},
    ).json()["id"]

    response = client.get("/api/transactions")

    assert response.status_code == 200
    transactions = response.json()
    assert [(t["date"], t["amount_minor"], t["currency"]) for t in transactions] == [
        ("2026-04-11", -1000000, "INR"),
        ("2026-04-05", 15000000, "INR"),
        ("2026-04-03", -125000, "INR"),
    ]
    assert transactions[0]["description"] == "ATM WDL EXAMPLE BRANCH"
    assert transactions[0]["account_id"] == account_id
    assert transactions[0]["account_name"] == "Savings"
    assert transactions[0]["bank_id"] == "hdfc"
    assert transactions[0]["bank_name"] == "HDFC Bank"
    assert transactions[0]["statement_id"] == statement_id
    assert transactions[0]["needs_review"] is False


def test_no_transactions_is_an_empty_list(client):
    assert client.get("/api/transactions").json() == []
