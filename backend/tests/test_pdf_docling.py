"""PDFs without ruled tables, read through Docling. Needs `make models`; run with
`make test-models`. Excluded from `make test` and CI, which have no models."""

import io
import json

import pytest
from fastapi.testclient import TestClient
from fpdf import FPDF
from PIL import Image, ImageDraw, ImageFont

from app.config import REPO_ROOT
from app.main import create_app

pytestmark = pytest.mark.models

HEADER = ("Date", "Narration", "Chq./Ref.No.", "Withdrawal Amt.", "Deposit Amt.", "Balance")
ROWS = [
    ("01/04/26", "UPI-GREENLEAF GROCERY", "0000000001", "1,250.00", "", "98,750.00"),
    ("02/04/26", "SALARY EXAMPLE CORP", "0000000002", "", "1,50,000.00", "2,48,750.00"),
    ("03/04/26", "ATM WDL EXAMPLE BRANCH", "0000000003", "10,000.00", "", "2,38,750.00"),
    ("05/04/26", "UPI-METRO TRANSIT", "0000000004", "40.00", "", "2,38,710.00"),
    ("07/04/26", "NEFT-EXAMPLE LANDLORD", "0000000005", "25,000.00", "", "2,13,710.00"),
    ("09/04/26", "UPI-CORNER CAFE", "0000000006", "180.00", "", "2,13,530.00"),
    ("12/04/26", "INTEREST CREDIT", "0000000007", "", "312.00", "2,13,842.00"),
    ("15/04/26", "UPI-EXAMPLE PHARMACY", "0000000008", "450.00", "", "2,13,392.00"),
    ("18/04/26", "UPI-EXAMPLE BOOKSTORE", "0000000009", "1,200.00", "", "2,12,192.00"),
    ("21/04/26", "CARD PAYMENT EXAMPLE", "0000000010", "5,000.00", "", "2,07,192.00"),
    ("24/04/26", "UPI-GREENLEAF GROCERY", "0000000011", "2,100.00", "", "2,05,092.00"),
    ("28/04/26", "REFUND EXAMPLE STORE", "0000000012", "", "600.00", "2,05,692.00"),
]
MAPPING = {
    "header_row": 0,  # replaced with the detected header line in each test
    "date_column": "Date",
    "description_column": "Narration",
    "amount_mode": "debit_credit",
    "debit_column": "Withdrawal Amt.",
    "credit_column": "Deposit Amt.",
    "date_format": "DD/MM/YY",
}
COLUMN_X = [10, 30, 85, 115, 145, 175]  # millimetres; amounts are right-aligned to x + 25


def text_only_statement(password: str | None = None) -> bytes:
    document = FPDF()
    if password:
        document.set_encryption(owner_password="owner-only", user_password=password)
    document.add_page()
    document.set_font("Helvetica", size=11)
    document.text(10, 12, "EXAMPLE BANK")
    document.set_font("Helvetica", size=7)
    document.text(10, 18, "Statement of account  Period 01/04/26 to 30/04/26")
    document.text(10, 23, "Opening Balance 1,00,000.00")
    for line, row in enumerate([HEADER, *ROWS]):
        document.set_font("Helvetica", "B" if line == 0 else "", 7)
        y = 32 + line * 5
        for column, (x, cell) in enumerate(zip(COLUMN_X, row, strict=True)):
            right_aligned = column >= 3
            document.text(x + 25 - document.get_string_width(cell) if right_aligned else x, y, cell)
        if line == 0:
            document.line(10, y + 1.5, 200, y + 1.5)
    document.text(10, 32 + (len(ROWS) + 2) * 5, "Closing Balance 2,05,692.00")
    return bytes(document.output())


def scanned_statement() -> bytes:
    image = Image.new("RGB", (2480, 1400), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 30)
    for line, row in enumerate([HEADER, *ROWS]):
        for x, cell in zip([100, 400, 1100, 1450, 1800, 2150], row, strict=True):
            draw.text((x, 120 + line * 70), cell, fill="black", font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    document = FPDF()
    document.add_page()
    document.image(buffer, x=0, y=0, w=210)
    return bytes(document.output())


@pytest.fixture
def models_client(settings):
    models = settings.model_copy(update={"docling_models_path": REPO_ROOT / "models" / "docling"})
    with TestClient(create_app(models)) as client:
        yield client


def hdfc_account(client) -> int:
    return client.post(
        "/api/accounts", json={"bank_id": "hdfc", "type": "bank", "name": "Savings"}
    ).json()["id"]


def post(client, account_id, content, **fields):
    data = {"account_id": str(account_id)}
    for name, value in fields.items():
        data[name] = json.dumps(value) if name == "mapping" else str(value)
    return client.post(
        "/api/statements", data=data, files={"file": ("s.pdf", content, "application/pdf")}
    )


def header_line(rows: list[list[str]]) -> int:
    return next(index for index, row in enumerate(rows) if row[:2] == ["Date", "Narration"])


def test_text_only_statement_is_read_into_columns(models_client):
    account_id = hdfc_account(models_client)

    response = post(models_client, account_id, text_only_statement())

    rows = response.json()["error"]["details"]["rows"]
    assert rows[header_line(rows) + 1][:5] == [
        "01/04/26",
        "UPI-GREENLEAF GROCERY",
        "0000000001",
        "1,250.00",
        "",
    ]
    assert ["Opening Balance 1,00,000.00"] in rows


def test_text_only_statement_imports_with_the_confirmed_mapping(models_client):
    account_id = hdfc_account(models_client)
    content = text_only_statement()
    rows = post(models_client, account_id, content).json()["error"]["details"]["rows"]

    response = post(
        models_client, account_id, content, mapping={**MAPPING, "header_row": header_line(rows)}
    )

    assert response.status_code == 201
    assert response.json()["imported_count"] == 12
    amounts = [t["amount_minor"] for t in models_client.get("/api/transactions").json()]
    assert sum(amounts) == 10569200  # closing 2,05,692.00 minus opening 1,00,000.00


def test_encrypted_text_only_statement_is_read_after_unlock(models_client):
    account_id = hdfc_account(models_client)

    response = post(models_client, account_id, text_only_statement("s3cret"), password="s3cret")

    assert response.json()["error"]["code"] == "csv_mapping_required"


def test_scanned_statement_is_read_with_ocr(models_client):
    account_id = hdfc_account(models_client)

    response = post(models_client, account_id, scanned_statement())

    rows = response.json()["error"]["details"]["rows"]
    assert rows[header_line(rows) + 2][:2] == ["02/04/26", "SALARY EXAMPLE CORP"]


def test_scanned_statement_imports_every_amount_in_its_column(models_client):
    account_id = hdfc_account(models_client)
    content = scanned_statement()
    rows = post(models_client, account_id, content).json()["error"]["details"]["rows"]

    response = post(
        models_client, account_id, content, mapping={**MAPPING, "header_row": header_line(rows)}
    )

    assert response.json()["imported_count"] == 12
    amounts = [t["amount_minor"] for t in models_client.get("/api/transactions").json()]
    assert sum(amounts) == 10569200
