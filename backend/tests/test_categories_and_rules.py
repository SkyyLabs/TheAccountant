def category_id(client, name: str) -> int:
    return next(c["id"] for c in client.get("/api/categories").json() if c["name"] == name)


def test_default_categories_include_both_regions_and_uncategorized_last(client):
    categories = client.get("/api/categories").json()

    names = [c["name"] for c in categories]
    assert names[-1] == "Uncategorized"
    assert "Groceries" in names
    regions = {c["name"]: c["region"] for c in categories}
    assert regions["Domestic Help"] == "IN"
    assert regions["Groceries"] == "both"


def test_category_is_created(client):
    response = client.post("/api/categories", json={"name": "Pets", "region": "both"})

    assert response.status_code == 201
    assert response.json()["name"] == "Pets"
    assert response.json()["is_default"] is False


def test_duplicate_category_is_a_conflict(client):
    response = client.post("/api/categories", json={"name": "Groceries"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "category_exists"


def test_category_is_renamed(client):
    response = client.patch(
        f"/api/categories/{category_id(client, 'Dining')}", json={"name": "Eating Out"}
    )

    assert response.json()["name"] == "Eating Out"


def test_uncategorized_cannot_be_renamed_or_deleted(client):
    uncategorized = category_id(client, "Uncategorized")

    renamed = client.patch(f"/api/categories/{uncategorized}", json={"name": "Other"})
    deleted = client.delete(f"/api/categories/{uncategorized}")

    assert renamed.json()["error"]["code"] == "category_protected"
    assert deleted.json()["error"]["code"] == "category_protected"


def test_unused_category_is_deleted(client):
    pets = client.post("/api/categories", json={"name": "Pets"}).json()["id"]

    response = client.delete(f"/api/categories/{pets}")

    assert response.status_code == 204
    assert "Pets" not in [c["name"] for c in client.get("/api/categories").json()]


def test_category_used_by_a_rule_cannot_be_deleted(client):
    dining = category_id(client, "Dining")
    client.post(
        "/api/rules", json={"match_type": "exact", "pattern": "cafe", "category_id": dining}
    )

    response = client.delete(f"/api/categories/{dining}")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "category_in_use"


def test_rule_pattern_is_stored_as_a_merchant_key(client):
    response = client.post(
        "/api/rules",
        json={
            "match_type": "exact",
            "pattern": "UPI/991/Corner-Cafe",
            "category_id": category_id(client, "Dining"),
        },
    )

    assert response.status_code == 201
    assert response.json()["rule"]["pattern"] == "upi corner cafe"


def test_rules_are_listed_by_priority(client):
    dining = category_id(client, "Dining")
    client.post("/api/rules", json={"match_type": "exact", "pattern": "a", "category_id": dining})
    client.post(
        "/api/rules",
        json={"match_type": "exact", "pattern": "b", "category_id": dining, "priority": 5},
    )

    patterns = [rule["pattern"] for rule in client.get("/api/rules").json()]

    assert patterns == ["b", "a"]


def test_rule_is_updated(client):
    dining = category_id(client, "Dining")
    rule = client.post(
        "/api/rules", json={"match_type": "exact", "pattern": "cafe", "category_id": dining}
    ).json()["rule"]

    response = client.patch(f"/api/rules/{rule['id']}", json={"match_type": "contains"})

    assert response.json()["match_type"] == "contains"
    assert response.json()["pattern"] == "cafe"


def test_rule_is_deleted(client):
    dining = category_id(client, "Dining")
    rule = client.post(
        "/api/rules", json={"match_type": "exact", "pattern": "cafe", "category_id": dining}
    ).json()["rule"]

    response = client.delete(f"/api/rules/{rule['id']}")

    assert response.status_code == 204
    assert client.get("/api/rules").json() == []


def test_unknown_rule_is_not_found(client):
    response = client.delete("/api/rules/999")

    assert response.json()["error"]["code"] == "rule_not_found"


def test_rule_pattern_without_letters_is_rejected(client):
    response = client.post(
        "/api/rules",
        json={
            "match_type": "exact",
            "pattern": "12345",
            "category_id": category_id(client, "Dining"),
        },
    )

    assert response.status_code == 422
