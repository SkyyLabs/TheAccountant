def test_account_is_created_under_a_bank(client):
    response = client.post(
        "/api/accounts", json={"bank_id": "chase", "type": "credit_card", "name": "Freedom 1234"}
    )

    assert response.status_code == 201
    assert response.json() == {
        "id": 1,
        "bank_id": "chase",
        "bank_name": "Chase",
        "type": "credit_card",
        "name": "Freedom 1234",
    }


def test_accounts_can_be_filtered_by_bank(client):
    client.post("/api/accounts", json={"bank_id": "chase", "type": "bank", "name": "Checking"})
    client.post("/api/accounts", json={"bank_id": "hdfc", "type": "bank", "name": "Savings"})

    response = client.get("/api/accounts", params={"bank_id": "hdfc"})

    assert [account["name"] for account in response.json()] == ["Savings"]


def test_account_for_unknown_bank_is_not_found(client):
    response = client.post(
        "/api/accounts", json={"bank_id": "no_such_bank", "type": "bank", "name": "Checking"}
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "bank_not_found"


def test_same_account_name_twice_in_one_bank_is_a_conflict(client):
    body = {"bank_id": "chase", "type": "bank", "name": "Checking"}
    client.post("/api/accounts", json=body)

    response = client.post("/api/accounts", json=body)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "account_exists"


def test_same_account_name_in_two_banks_is_allowed(client):
    client.post("/api/accounts", json={"bank_id": "chase", "type": "bank", "name": "Checking"})

    response = client.post(
        "/api/accounts", json={"bank_id": "sofi", "type": "bank", "name": "Checking"}
    )

    assert response.status_code == 201


def test_unknown_account_type_is_rejected(client):
    response = client.post(
        "/api/accounts", json={"bank_id": "chase", "type": "brokerage", "name": "Invest"}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
