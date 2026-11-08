from conftest import (
    CHASE_MARCH_ACCOUNT,
    CHASE_MARCH_CSV,
    CHASE_MARCH_TRANSACTIONS,
    transaction_answer,
)

from app.categorize.categorizer import merchant_key
from app.llm.base import LlmUnavailable

# CHASE_MARCH in order: GREENLEAF GROCERY, METRO TRANSIT, PAYMENT THANK YOU (money in),
# EXAMPLE ELECTRONICS.
MARCH_ANSWER = {
    "items": [
        {"index": 0, "category": "Groceries", "confidence": 0.95},
        {"index": 1, "category": "Transport", "confidence": 0.9},
        {"index": 2, "category": "Card Payments", "confidence": 0.9},
        {"index": 3, "category": "Shopping", "confidence": 0.8},
    ]
}


def import_march(upload, categories=MARCH_ANSWER) -> dict:
    return upload(
        CHASE_MARCH_CSV,
        accounts=[CHASE_MARCH_ACCOUNT],
        transactions=CHASE_MARCH_TRANSACTIONS,
        categories=categories,
    )


def by_description(client) -> dict[str, tuple]:
    return {
        t["description"]: (t["category_name"], t["category_source"], t["category_needs_review"])
        for t in client.get("/api/transactions").json()
    }


def category_questions(client) -> list[str]:
    return [p for p in client.app.state.llm.prompts if p.startswith("Allowed categories")]


def category_id(client, name: str) -> int:
    return next(c["id"] for c in client.get("/api/categories").json() if c["name"] == name)


def test_merchant_key_drops_reference_numbers_and_punctuation():
    assert merchant_key("UPI/123456/SHARMA KIRANA-STORE") == "upi sharma kirana store"


def test_imported_transactions_are_categorized_by_the_local_model(client, upload):
    result = import_march(upload)

    assert by_description(client) == {
        "GREENLEAF GROCERY": ("Groceries", "llm", False),
        "METRO TRANSIT": ("Transport", "llm", False),
        "PAYMENT THANK YOU": ("Card Payments", "llm", False),
        "EXAMPLE ELECTRONICS": ("Shopping", "llm", False),
    }
    assert result["statements"][0]["categorization_status"] == "done"


def test_low_confidence_answer_is_uncategorized_and_needs_review(client, upload):
    import_march(upload, {"items": [{**i, "confidence": 0.3} for i in MARCH_ANSWER["items"]]})

    assert by_description(client)["GREENLEAF GROCERY"] == ("Uncategorized", "llm", True)


def test_answer_outside_the_category_list_is_retried_then_needs_review(client, upload):
    invalid = {"items": [{"index": 0, "category": "Snacks", "confidence": 0.9}]}

    import_march(upload, [invalid, invalid])

    assert len(category_questions(client)) == 2
    assert by_description(client)["GREENLEAF GROCERY"] == ("Uncategorized", "llm", True)


def test_without_the_model_transactions_wait_and_can_be_retried(client, upload):
    result = import_march(upload, categories=None)
    assert result["statements"][0]["categorization_status"] == "llm_unavailable"
    assert by_description(client)["GREENLEAF GROCERY"] == (None, None, False)
    client.app.state.llm.script(MARCH_ANSWER)

    response = client.post("/api/transactions/categorize")

    assert response.status_code == 202
    assert by_description(client)["GREENLEAF GROCERY"][0] == "Groceries"


def test_stored_result_for_a_merchant_is_reused_without_asking_the_model(client, upload):
    import_march(upload)
    april = CHASE_MARCH_CSV + b"04/10/2026,GREENLEAF GROCERY,-18.00\n04/11/2026,CORNER CAFE,-6.50\n"

    upload(
        april,
        accounts=[CHASE_MARCH_ACCOUNT],
        transactions=[
            transaction_answer("2026-04-10", "GREENLEAF GROCERY", "18.00", "out"),
            transaction_answer("2026-04-11", "CORNER CAFE", "6.50", "out"),
        ],
        categories={"items": [{"index": 0, "category": "Dining", "confidence": 0.9}]},
    )

    second = category_questions(client)[1]
    assert "CORNER CAFE" in second
    assert "GREENLEAF" not in second
    april_grocery = next(
        t for t in client.get("/api/transactions").json() if t["date"] == "2026-04-10"
    )
    assert (april_grocery["category_name"], april_grocery["category_source"]) == (
        "Groceries",
        "cache",
    )


def test_rule_beats_the_stored_result_and_the_model(client, upload):
    client.post(
        "/api/rules",
        json={
            "match_type": "contains",
            "pattern": "greenleaf",
            "category_id": category_id(client, "Dining"),
        },
    )

    import_march(upload)

    assert by_description(client)["GREENLEAF GROCERY"] == ("Dining", "rule", False)
    assert "GREENLEAF" not in category_questions(client)[0]


def test_rule_amount_range_limits_what_it_matches(client, upload):
    client.post(
        "/api/rules",
        json={
            "match_type": "contains",
            "pattern": "example electronics",
            "amount_min_minor": -50000,
            "category_id": category_id(client, "Gifts and Donations"),
        },
    )

    import_march(upload)

    # The -1,250.00 charge is below the rule's -500.00 minimum, so the model decides.
    assert by_description(client)["EXAMPLE ELECTRONICS"][1] == "llm"


def test_correction_is_kept_and_offers_a_rule(client, upload):
    import_march(upload)
    grocery = next(
        t for t in client.get("/api/transactions").json() if t["description"] == "GREENLEAF GROCERY"
    )

    response = client.patch(
        f"/api/transactions/{grocery['id']}", json={"category_id": category_id(client, "Dining")}
    )

    body = response.json()
    assert body["transaction"]["category_name"] == "Dining"
    assert body["transaction"]["category_source"] == "user"
    assert body["suggested_rule"] == {
        "match_type": "exact",
        "pattern": "greenleaf grocery",
        "category_id": category_id(client, "Dining"),
    }


def test_new_rule_recategorizes_existing_transactions_but_not_user_choices(client, upload):
    import_march(upload)
    ids = {t["description"]: t["id"] for t in client.get("/api/transactions").json()}
    client.patch(
        f"/api/transactions/{ids['METRO TRANSIT']}",
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

    assert response.json()["applied_count"] == 3
    assert by_description(client)["METRO TRANSIT"][0] == "Travel"
    assert by_description(client)["GREENLEAF GROCERY"] == ("Health", "rule", False)


def test_indian_categories_are_offered_only_for_indian_accounts(client, upload):
    import_march(upload, LlmUnavailable("off"))

    assert "Domestic Help" not in category_questions(client)[0]
    assert "Groceries" in category_questions(client)[0]


def test_correction_to_unknown_category_is_not_found(client, upload):
    import_march(upload)
    transaction_id = client.get("/api/transactions").json()[0]["id"]

    response = client.patch(f"/api/transactions/{transaction_id}", json={"category_id": 999})

    assert response.json()["error"]["code"] == "category_not_found"
