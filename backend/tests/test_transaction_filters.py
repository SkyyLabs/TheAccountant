import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "statements"
CHASE_MAPPING = {
    "header_row": 0,
    "date_column": "Transaction Date",
    "description_column": "Description",
    "amount_mode": "signed",
    "amount_column": "Amount",
    "date_format": "MM/DD/YYYY",
}
HDFC_MAPPING = {
    "header_row": 3,
    "date_column": "Date",
    "description_column": "Narration",
    "amount_mode": "debit_credit",
    "debit_column": "Withdrawal Amt.",
    "credit_column": "Deposit Amt.",
    "date_format": "DD/MM/YY",
}


@pytest.fixture
def two_currencies(client):
    """Chase card in USD (March 2026) and HDFC savings in INR (April 2026)."""
    chase = client.post(
        "/api/accounts", json={"bank_id": "chase", "type": "credit_card", "name": "Card"}
    ).json()["id"]
    hdfc = client.post(
        "/api/accounts", json={"bank_id": "hdfc", "type": "bank", "name": "Savings"}
    ).json()["id"]
    client.app.state.llm.script(
        {
            "items": [
                {"index": 0, "category": "Groceries", "confidence": 0.9},
                {"index": 1, "category": "Transport", "confidence": 0.9},
                {"index": 2, "category": "Card Payments", "confidence": 0.9},
                {"index": 3, "category": "Shopping", "confidence": 0.9},
            ]
        }
    )
    for account_id, fixture, mapping in [
        (chase, "chase/card_2026_03.csv", CHASE_MAPPING),
        (hdfc, "hdfc/savings_2026_04.csv", HDFC_MAPPING),
    ]:
        client.post(
            "/api/statements",
            data={"account_id": str(account_id), "mapping": json.dumps(mapping)},
            files={"file": ("s.csv", (FIXTURES / fixture).read_bytes(), "text/csv")},
        )
    return {"chase": chase, "hdfc": hdfc}


def descriptions(client, **params) -> list[str]:
    response = client.get("/api/transactions", params=params)
    assert response.status_code == 200
    return [t["description"] for t in response.json()]


def category_id(client, name: str) -> int:
    return next(c["id"] for c in client.get("/api/categories").json() if c["name"] == name)


def test_date_range_includes_both_ends(client, two_currencies):
    assert descriptions(client, date_from="2026-03-09", date_to="2026-03-12") == [
        "PAYMENT THANK YOU",
        "METRO TRANSIT",
    ]


def test_categories_filter_matches_any_of_them(client, two_currencies):
    params = {"category_ids": [category_id(client, "Groceries"), category_id(client, "Shopping")]}

    assert descriptions(client, **params) == ["EXAMPLE ELECTRONICS", "GREENLEAF GROCERY"]


def test_account_filter(client, two_currencies):
    assert descriptions(client, account_ids=[two_currencies["hdfc"]]) == [
        "ATM WDL EXAMPLE BRANCH",
        "SALARY EXAMPLE CORP",
        "UPI-SHARMA KIRANA STORE",
    ]


def test_currency_filter(client, two_currencies):
    currencies = {t["currency"] for t in client.get("/api/transactions?currency=USD").json()}

    assert currencies == {"USD"}


def test_amount_range_filters_on_size_for_money_in_and_out(client, two_currencies):
    # Between 40 and 1,250 either way: the 42.10 and 1,250.00 charges, the 500.00 payment
    # and the 1,250.00 INR withdrawal; not the 2.75 fare or the larger INR amounts.
    assert descriptions(client, amount_min="40", amount_max="1,250.00") == [
        "UPI-SHARMA KIRANA STORE",
        "EXAMPLE ELECTRONICS",
        "PAYMENT THANK YOU",
        "GREENLEAF GROCERY",
    ]


def test_text_search_ignores_case(client, two_currencies):
    assert descriptions(client, q="example") == [
        "ATM WDL EXAMPLE BRANCH",
        "SALARY EXAMPLE CORP",
        "EXAMPLE ELECTRONICS",
    ]


def test_text_search_treats_percent_as_a_literal(client, two_currencies):
    assert descriptions(client, q="%") == []


def test_filters_combine(client, two_currencies):
    assert descriptions(client, currency="USD", q="t", amount_max="100") == [
        "METRO TRANSIT",
    ]


def test_unreadable_amount_filter_is_rejected(client):
    response = client.get("/api/transactions", params={"amount_min": "lots"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_summary_totals_are_per_currency_never_mixed(client, two_currencies):
    totals = client.get("/api/summary").json()["totals"]

    assert totals == [
        {
            "currency": "INR",
            "money_in_minor": 15000000,
            "money_out_minor": 1125000,
            "transaction_count": 3,
        },
        {
            "currency": "USD",
            "money_in_minor": 50000,
            "money_out_minor": 129485,
            "transaction_count": 4,
        },
    ]


def test_summary_by_month(client, two_currencies):
    months = [
        (m["month"], m["currency"], m["money_out_minor"])
        for m in client.get("/api/summary").json()["by_month"]
    ]

    assert months == [("2026-03", "USD", 129485), ("2026-04", "INR", 1125000)]


def test_summary_by_category_lists_biggest_spending_first(client, two_currencies):
    usd = [
        (c["category_name"], c["money_out_minor"])
        for c in client.get("/api/summary?currency=USD").json()["by_category"]
    ]

    assert usd == [
        ("Shopping", 125000),
        ("Groceries", 4210),
        ("Transport", 275),
        ("Card Payments", 0),
    ]


def test_summary_applies_the_same_filters_as_the_list(client, two_currencies):
    totals = client.get("/api/summary", params={"date_from": "2026-04-01"}).json()["totals"]

    assert [t["currency"] for t in totals] == ["INR"]


def test_uncategorized_transactions_are_grouped_together(client, two_currencies):
    # The INR transactions were never categorized: the mock had no answer for them.
    inr = client.get("/api/summary?currency=INR").json()["by_category"]

    assert [(c["category_id"], c["transaction_count"]) for c in inr] == [(None, 3)]


def test_negative_typed_amount_filters_by_size_too(client, two_currencies):
    assert descriptions(client, amount_min="-1,000", currency="USD") == ["EXAMPLE ELECTRONICS"]


def test_spending_only_leaves_out_card_payments_but_keeps_uncategorized(client, two_currencies):
    totals = client.get("/api/summary", params={"spending_only": "true"}).json()["totals"]

    # USD loses the 500.00 card payment (money in); INR was never categorized and stays.
    assert [(t["currency"], t["money_in_minor"], t["transaction_count"]) for t in totals] == [
        ("INR", 15000000, 3),
        ("USD", 0, 3),
    ]
