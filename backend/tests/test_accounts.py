from conftest import (
    CHASE_MARCH_ACCOUNT,
    CHASE_MARCH_CSV,
    CHASE_MARCH_TRANSACTIONS,
    HDFC_APRIL_ACCOUNT,
    HDFC_APRIL_CSV,
    HDFC_APRIL_TRANSACTIONS,
)


def test_accounts_found_in_statements_are_listed_with_their_bank(client, upload):
    upload(CHASE_MARCH_CSV, accounts=[CHASE_MARCH_ACCOUNT], transactions=CHASE_MARCH_TRANSACTIONS)
    upload(HDFC_APRIL_CSV, accounts=[HDFC_APRIL_ACCOUNT], transactions=HDFC_APRIL_TRANSACTIONS)

    accounts = [(a["bank_name"], a["name"], a["type"]) for a in client.get("/api/accounts").json()]

    assert accounts == [
        ("Chase", "••4410", "credit_card"),
        ("HDFC Bank", "••4821", "bank"),
    ]


def test_accounts_can_be_filtered_by_bank(client, upload):
    upload(CHASE_MARCH_CSV, accounts=[CHASE_MARCH_ACCOUNT], transactions=CHASE_MARCH_TRANSACTIONS)
    upload(HDFC_APRIL_CSV, accounts=[HDFC_APRIL_ACCOUNT], transactions=HDFC_APRIL_TRANSACTIONS)

    response = client.get("/api/accounts", params={"bank_id": "hdfc"})

    assert [a["name"] for a in response.json()] == ["••4821"]
