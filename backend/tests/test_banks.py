def test_default_banks_are_listed_with_currency_and_date_format(client):
    response = client.get("/api/banks")

    assert response.status_code == 200
    banks = {bank["id"]: bank for bank in response.json()}
    assert sorted(banks) == [
        "axis",
        "capital_one",
        "chase",
        "discover",
        "hdfc",
        "icici",
        "sbi",
        "sofi",
    ]
    assert banks["chase"] == {
        "id": "chase",
        "name": "Chase",
        "country": "US",
        "currency": "USD",
        "default_date_format": "MM/DD/YYYY",
        "is_default": True,
    }
    assert banks["hdfc"]["currency"] == "INR"


def test_other_bank_gets_a_slug_and_its_country_currency(client):
    response = client.post("/api/banks", json={"name": "Kotak Mahindra Bank", "country": "IN"})

    assert response.status_code == 201
    assert response.json() == {
        "id": "kotak_mahindra_bank",
        "name": "Kotak Mahindra Bank",
        "country": "IN",
        "currency": "INR",
        "default_date_format": "DD/MM/YYYY",
        "is_default": False,
    }


def test_other_bank_keeps_an_explicit_date_format(client):
    response = client.post(
        "/api/banks",
        json={"name": "Example Credit Union", "country": "US", "default_date_format": "YYYY-MM-DD"},
    )

    assert response.json()["default_date_format"] == "YYYY-MM-DD"


def test_added_bank_appears_in_the_list(client):
    client.post("/api/banks", json={"name": "Example Credit Union", "country": "US"})

    ids = [bank["id"] for bank in client.get("/api/banks").json()]

    assert "example_credit_union" in ids


def test_unknown_date_format_is_rejected(client):
    response = client.post(
        "/api/banks",
        json={"name": "Example Credit Union", "country": "US", "default_date_format": "auto"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_bank_whose_slug_matches_a_default_is_a_conflict(client):
    response = client.post("/api/banks", json={"name": "HDFC", "country": "IN"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "bank_exists"


def test_bank_name_without_letters_or_digits_is_rejected(client):
    response = client.post("/api/banks", json={"name": " -- ", "country": "US"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
