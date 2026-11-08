import json
from pathlib import Path

from app.categorize.categorizer import merchant_key
from app.llm.base import LlmUnavailable

FIXTURES = Path(__file__).parent / "fixtures" / "statements"
CHASE_MAPPING = {
    "header_row": 0,
    "date_column": "Transaction Date",
    "description_column": "Description",
    "amount_mode": "signed",
    "amount_column": "Amount",
    "date_format": "MM/DD/YYYY",
}
# chase/card_2026_03.csv, in file order: GREENLEAF GROCERY, METRO TRANSIT,
# PAYMENT THANK YOU (money in), EXAMPLE ELECTRONICS.
MARCH_ANSWER = {
    "items": [
        {"index": 0, "category": "Groceries", "confidence": 0.95},
        {"index": 1, "category": "Transport", "confidence": 0.9},
        {"index": 2, "category": "Card Payments", "confidence": 0.9},
        {"index": 3, "category": "Shopping", "confidence": 0.8},
    ]
}


def chase_account(client) -> int:
    return client.post(
        "/api/accounts", json={"bank_id": "chase", "type": "credit_card", "name": "Card"}
    ).json()["id"]


def upload(client, account_id: int, fixture: str):
    return client.post(
        "/api/statements",
        data={"account_id": str(account_id), "mapping": json.dumps(CHASE_MAPPING)},
        files={"file": (Path(fixture).name, (FIXTURES / fixture).read_bytes(), "text/csv")},
    )


def categories_by_description(client) -> dict[str, tuple]:
    return {
        t["description"]: (t["category_name"], t["category_source"], t["category_needs_review"])
        for t in client.get("/api/transactions").json()
    }


def category_id(client, name: str) -> int:
    return next(c["id"] for c in client.get("/api/categories").json() if c["name"] == name)


def test_merchant_key_drops_reference_numbers_and_punctuation():
    assert merchant_key("UPI/123456/SHARMA KIRANA-STORE") == "upi sharma kirana store"


def test_imported_transactions_are_categorized_by_the_local_model(client):
    client.app.state.llm.script(MARCH_ANSWER)

    statement = upload(client, chase_account(client), "chase/card_2026_03.csv").json()

    assert categories_by_description(client) == {
        "GREENLEAF GROCERY": ("Groceries", "llm", False),
        "METRO TRANSIT": ("Transport", "llm", False),
        "PAYMENT THANK YOU": ("Card Payments", "llm", False),
        "EXAMPLE ELECTRONICS": ("Shopping", "llm", False),
    }
    detail = client.get(f"/api/statements/{statement['id']}").json()
    assert detail["categorization_status"] == "done"


def test_low_confidence_answer_is_uncategorized_and_needs_review(client):
    answer = {"items": [{**item, "confidence": 0.3} for item in MARCH_ANSWER["items"]]}
    client.app.state.llm.script(answer)

    upload(client, chase_account(client), "chase/card_2026_03.csv")

    assert categories_by_description(client)["GREENLEAF GROCERY"] == (
        "Uncategorized",
        "llm",
        True,
    )


def test_answer_outside_the_category_list_is_retried_then_needs_review(client):
    invalid = {"items": [{"index": 0, "category": "Snacks", "confidence": 0.9}]}
    client.app.state.llm.script(invalid, invalid)

    upload(client, chase_account(client), "chase/card_2026_03.csv")

    assert len(client.app.state.llm.prompts) == 2
    assert categories_by_description(client)["GREENLEAF GROCERY"] == (
        "Uncategorized",
        "llm",
        True,
    )


def test_without_the_model_transactions_wait_and_can_be_retried(client):
    statement = upload(client, chase_account(client), "chase/card_2026_03.csv").json()
    detail = client.get(f"/api/statements/{statement['id']}").json()
    assert detail["categorization_status"] == "llm_unavailable"
    assert categories_by_description(client)["GREENLEAF GROCERY"] == (None, None, False)
    client.app.state.llm.script(MARCH_ANSWER)

    response = client.post("/api/transactions/categorize")

    assert response.status_code == 202
    assert categories_by_description(client)["GREENLEAF GROCERY"][0] == "Groceries"
    detail = client.get(f"/api/statements/{statement['id']}").json()
    assert detail["categorization_status"] == "done"


def test_stored_result_for_a_merchant_is_reused_without_asking_the_model(client):
    account_id = chase_account(client)
    client.app.state.llm.script(MARCH_ANSWER)
    upload(client, account_id, "chase/card_2026_03.csv")
    client.app.state.llm.script({"items": [{"index": 0, "category": "Dining", "confidence": 0.9}]})
    april = (
        b"Transaction Date,Description,Amount\n"
        b"04/10/2026,GREENLEAF GROCERY,-18.00\n"
        b"04/11/2026,CORNER CAFE,-6.50\n"
    )

    client.post(
        "/api/statements",
        data={"account_id": str(account_id)},
        files={"file": ("april.csv", april, "text/csv")},
    )

    assert "CORNER CAFE" in client.app.state.llm.prompts[1]
    assert "GREENLEAF" not in client.app.state.llm.prompts[1]
    april_grocery = next(
        t for t in client.get("/api/transactions").json() if t["date"] == "2026-04-10"
    )
    assert (april_grocery["category_name"], april_grocery["category_source"]) == (
        "Groceries",
        "cache",
    )


def test_rule_beats_the_stored_result_and_the_model(client):
    account_id = chase_account(client)
    client.post(
        "/api/rules",
        json={
            "match_type": "contains",
            "pattern": "greenleaf",
            "category_id": category_id(client, "Dining"),
        },
    )
    client.app.state.llm.script(MARCH_ANSWER)

    upload(client, account_id, "chase/card_2026_03.csv")

    assert categories_by_description(client)["GREENLEAF GROCERY"] == ("Dining", "rule", False)
    assert "GREENLEAF" not in client.app.state.llm.prompts[0]


def test_rule_amount_range_limits_what_it_matches(client):
    client.post(
        "/api/rules",
        json={
            "match_type": "contains",
            "pattern": "example electronics",
            "amount_min_minor": -50000,
            "category_id": category_id(client, "Gifts and Donations"),
        },
    )
    client.app.state.llm.script(MARCH_ANSWER)

    upload(client, chase_account(client), "chase/card_2026_03.csv")

    # The -1,250.00 charge is below the rule's -500.00 minimum, so the model decides.
    assert categories_by_description(client)["EXAMPLE ELECTRONICS"][1] == "llm"


def test_correction_is_kept_and_offers_a_rule(client):
    client.app.state.llm.script(MARCH_ANSWER)
    upload(client, chase_account(client), "chase/card_2026_03.csv")
    grocery = next(
        t for t in client.get("/api/transactions").json() if t["description"] == "GREENLEAF GROCERY"
    )

    response = client.patch(
        f"/api/transactions/{grocery['id']}", json={"category_id": category_id(client, "Dining")}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["transaction"]["category_name"] == "Dining"
    assert body["transaction"]["category_source"] == "user"
    assert body["suggested_rule"] == {
        "match_type": "exact",
        "pattern": "greenleaf grocery",
        "category_id": category_id(client, "Dining"),
    }


def test_new_rule_recategorizes_existing_transactions_but_not_user_choices(client):
    client.app.state.llm.script(MARCH_ANSWER)
    upload(client, chase_account(client), "chase/card_2026_03.csv")
    transactions = {t["description"]: t["id"] for t in client.get("/api/transactions").json()}
    client.patch(
        f"/api/transactions/{transactions['METRO TRANSIT']}",
        json={"category_id": category_id(client, "Travel")},
    )

    response = client.post(
        "/api/rules",
        json={
            "match_type": "contains",
            "pattern": "e",
            "category_id": category_id(client, "Health"),
        },
    )

    # Every merchant contains "e"; METRO TRANSIT was set by hand and keeps Travel.
    assert response.json()["applied_count"] == 3
    assert categories_by_description(client)["METRO TRANSIT"][0] == "Travel"
    assert categories_by_description(client)["GREENLEAF GROCERY"] == ("Health", "rule", False)


def test_indian_categories_are_offered_only_for_indian_banks(client):
    chase_id = chase_account(client)
    client.app.state.llm.script(LlmUnavailable("off"))

    upload(client, chase_id, "chase/card_2026_03.csv")

    assert "Domestic Help" not in client.app.state.llm.prompts[0]
    assert "Groceries" in client.app.state.llm.prompts[0]


def test_correction_to_unknown_category_is_not_found(client):
    client.app.state.llm.script(MARCH_ANSWER)
    upload(client, chase_account(client), "chase/card_2026_03.csv")
    transaction_id = client.get("/api/transactions").json()[0]["id"]

    response = client.patch(f"/api/transactions/{transaction_id}", json={"category_id": 999})

    assert response.json()["error"]["code"] == "category_not_found"
