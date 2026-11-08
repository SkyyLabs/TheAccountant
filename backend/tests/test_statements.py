import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

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


def create_account(client, bank_id: str, account_type: str = "credit_card") -> int:
    response = client.post(
        "/api/accounts", json={"bank_id": bank_id, "type": account_type, "name": "Main"}
    )
    return response.json()["id"]


def upload(client, account_id: int, fixture: str, mapping: dict | None = None):
    data = {"account_id": str(account_id)}
    if mapping is not None:
        data["mapping"] = json.dumps(mapping)
    content = (FIXTURES / fixture).read_bytes()
    return client.post(
        "/api/statements",
        data=data,
        files={"file": (Path(fixture).name, content, "text/csv")},
    )


def test_first_csv_upload_asks_for_a_mapping_with_a_suggestion(client):
    account_id = create_account(client, "chase")

    response = upload(client, account_id, "chase/card_2026_03.csv")

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "csv_mapping_required"
    assert error["details"]["rows"][0][0] == "Transaction Date"
    assert error["details"]["suggested_mapping"]["amount_column"] == "Amount"
    assert error["details"]["suggested_mapping"]["date_format"] == "MM/DD/YYYY"


def test_mapping_required_response_stores_nothing(client):
    account_id = create_account(client, "chase")

    upload(client, account_id, "chase/card_2026_03.csv")

    assert client.get("/api/statements").json() == []


def test_preview_shows_parsed_transactions_without_storing(client):
    account_id = create_account(client, "hdfc", "bank")
    content = (FIXTURES / "hdfc/savings_2026_04.csv").read_bytes()

    response = client.post(
        "/api/statements/preview",
        data={"account_id": str(account_id), "mapping": json.dumps(HDFC_MAPPING)},
        files={"file": ("savings.csv", content, "text/csv")},
    )

    assert response.status_code == 200
    assert response.json() == {
        "row_count": 3,
        "skipped_row_count": 1,
        "transactions": [
            {
                "date": "2026-04-03",
                "amount_minor": -125000,
                "currency": "INR",
                "description": "UPI-SHARMA KIRANA STORE",
            },
            {
                "date": "2026-04-05",
                "amount_minor": 15000000,
                "currency": "INR",
                "description": "SALARY EXAMPLE CORP",
            },
            {
                "date": "2026-04-11",
                "amount_minor": -1000000,
                "currency": "INR",
                "description": "ATM WDL EXAMPLE BRANCH",
            },
        ],
    }
    assert client.get("/api/statements").json() == []


def test_upload_with_mapping_imports_as_unverifiable(client):
    account_id = create_account(client, "chase")

    response = upload(client, account_id, "chase/card_2026_03.csv", CHASE_MAPPING)

    assert response.status_code == 201
    statement = response.json()
    assert statement["account_id"] == account_id
    assert statement["bank_id"] == "chase"
    assert statement["bank_name"] == "Chase"
    assert statement["filename"] == "card_2026_03.csv"
    assert statement["currency"] == "USD"
    assert statement["period_start"] == "2026-03-04"
    assert statement["period_end"] == "2026-03-20"
    assert statement["reconciliation_status"] == "unverifiable"
    assert statement["row_count"] == 4
    assert statement["imported_count"] == 4
    assert statement["duplicate_count"] == 0


def test_confirmed_mapping_is_reused_for_the_next_upload(client):
    account_id = create_account(client, "chase")
    upload(client, account_id, "chase/card_2026_03.csv", CHASE_MAPPING)

    response = upload(client, account_id, "chase/card_2026_04.csv")

    assert response.status_code == 201


def test_same_file_twice_returns_the_existing_statement(client):
    account_id = create_account(client, "chase")
    first = upload(client, account_id, "chase/card_2026_03.csv", CHASE_MAPPING).json()

    response = upload(client, account_id, "chase/card_2026_03.csv", CHASE_MAPPING)

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "duplicate_statement"
    assert error["details"] == {"statement_id": first["id"]}


def test_overlapping_statement_skips_transactions_already_imported(client):
    account_id = create_account(client, "chase")
    upload(client, account_id, "chase/card_2026_03.csv", CHASE_MAPPING)

    statement = upload(client, account_id, "chase/card_2026_04.csv").json()

    assert statement["row_count"] == 3
    assert statement["imported_count"] == 1
    assert statement["duplicate_count"] == 2


def test_identical_transactions_in_one_statement_are_both_kept(client):
    account_id = create_account(client, "chase")
    content = (
        b"Transaction Date,Description,Amount\n"
        b"03/04/2026,METRO TRANSIT,-2.75\n"
        b"03/04/2026,METRO TRANSIT,-2.75\n"
    )

    response = client.post(
        "/api/statements",
        data={"account_id": str(account_id), "mapping": json.dumps(CHASE_MAPPING)},
        files={"file": ("twice.csv", content, "text/csv")},
    )

    assert response.json()["imported_count"] == 2


def test_unreadable_row_rejects_the_whole_file(client):
    account_id = create_account(client, "chase")
    content = b"Transaction Date,Description,Amount\n03/04/2026,SHOP,1.00\n13/04/2026,SHOP,2.00\n"

    response = client.post(
        "/api/statements",
        data={"account_id": str(account_id), "mapping": json.dumps(CHASE_MAPPING)},
        files={"file": ("bad.csv", content, "text/csv")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "csv_row_invalid"
    assert client.get("/api/statements").json() == []


def test_failed_import_does_not_save_the_mapping(client):
    account_id = create_account(client, "chase")
    content = b"Transaction Date,Description,Amount\n13/04/2026,SHOP,2.00\n"
    client.post(
        "/api/statements",
        data={"account_id": str(account_id), "mapping": json.dumps(CHASE_MAPPING)},
        files={"file": ("bad.csv", content, "text/csv")},
    )

    response = upload(client, account_id, "chase/card_2026_03.csv")

    assert response.json()["error"]["code"] == "csv_mapping_required"


def test_saved_mapping_that_no_longer_fits_asks_again(client):
    account_id = create_account(client, "chase")
    upload(client, account_id, "chase/card_2026_03.csv", CHASE_MAPPING)
    content = b"Date,Details,Value\n04/02/2026,CORNER CAFE,-15.00\n"

    response = client.post(
        "/api/statements",
        data={"account_id": str(account_id)},
        files={"file": ("new_layout.csv", content, "text/csv")},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "csv_mapping_required"


def test_malformed_mapping_is_invalid(client):
    account_id = create_account(client, "chase")
    mapping = {**CHASE_MAPPING, "date_format": "auto"}

    response = upload(client, account_id, "chase/card_2026_03.csv", mapping)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "csv_mapping_invalid"


def test_pdf_upload_is_not_supported_yet(client):
    account_id = create_account(client, "chase")

    response = client.post(
        "/api/statements",
        data={"account_id": str(account_id)},
        files={"file": ("statement.pdf", b"%PDF-1.7\n", "application/pdf")},
    )

    assert response.status_code == 415
    assert response.json()["error"]["code"] == "unsupported_file_type"


def test_upload_to_unknown_account_is_not_found(client):
    response = upload(client, 999, "chase/card_2026_03.csv", CHASE_MAPPING)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "account_not_found"


@pytest.fixture
def small_limit_client(settings):
    with TestClient(create_app(settings.model_copy(update={"max_upload_mb": 1}))) as client:
        yield client


def test_upload_over_the_size_limit_is_rejected(small_limit_client):
    content = b"x" * (1024 * 1024 + 1)

    response = small_limit_client.post(
        "/api/statements",
        data={"account_id": "1"},
        files={"file": ("big.csv", content, "text/csv")},
    )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


def test_uploaded_statements_are_listed_newest_first(client):
    chase_id = create_account(client, "chase")
    hdfc_id = create_account(client, "hdfc", "bank")
    upload(client, chase_id, "chase/card_2026_03.csv", CHASE_MAPPING)
    upload(client, hdfc_id, "hdfc/savings_2026_04.csv", HDFC_MAPPING)

    statements = client.get("/api/statements").json()

    assert [(s["bank_id"], s["currency"]) for s in statements] == [
        ("hdfc", "INR"),
        ("chase", "USD"),
    ]


def test_unknown_statement_is_not_found(client):
    response = client.get("/api/statements/999")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "statement_not_found"


def test_mapping_required_lists_the_date_formats_to_choose_from(client):
    account_id = create_account(client, "chase")

    response = upload(client, account_id, "chase/card_2026_03.csv")

    formats = response.json()["error"]["details"]["date_formats"]
    assert "MM/DD/YYYY" in formats
    assert "DD/MM/YYYY" in formats
