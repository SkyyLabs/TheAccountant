from conftest import HDFC_APRIL_ACCOUNT, HDFC_APRIL_CSV, HDFC_APRIL_TRANSACTIONS


def test_imported_transactions_are_listed_newest_first_with_their_account(client, upload):
    result = upload(
        HDFC_APRIL_CSV, accounts=[HDFC_APRIL_ACCOUNT], transactions=HDFC_APRIL_TRANSACTIONS
    )

    transactions = client.get("/api/transactions").json()

    assert [(t["date"], t["amount_minor"], t["currency"]) for t in transactions] == [
        ("2026-04-11", -1000000, "INR"),
        ("2026-04-05", 15000000, "INR"),
        ("2026-04-03", -125000, "INR"),
    ]
    assert transactions[0]["description"] == "ATM WDL EXAMPLE BRANCH"
    assert (transactions[0]["bank_id"], transactions[0]["bank_name"]) == ("hdfc", "HDFC Bank")
    assert transactions[0]["account_name"] == "••4821"
    assert transactions[0]["statement_id"] == result["statements"][0]["id"]


def test_no_transactions_is_an_empty_list(client):
    assert client.get("/api/transactions").json() == []
