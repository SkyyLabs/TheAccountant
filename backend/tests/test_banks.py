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
