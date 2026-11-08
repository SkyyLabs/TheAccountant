from pathlib import Path

import keyring
import pytest
from fastapi.testclient import TestClient
from fpdf import FPDF
from keyring.backend import KeyringBackend

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    # Every test gets its own database file; tests never touch data/accountant.db.
    # Docling models are absent unless a test is marked `models` (see models_settings).
    return Settings(
        _env_file=None,
        database_path=tmp_path / "test.db",
        llm_provider="mock",
        docling_models_path=tmp_path / "no-models",
    )


@pytest.fixture
def client(settings: Settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


class MemoryKeyring(KeyringBackend):
    priority = 1

    def __init__(self) -> None:
        super().__init__()
        self.passwords: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.passwords.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.passwords[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        self.passwords.pop((service, username), None)


@pytest.fixture(autouse=True)
def memory_keychain():
    # Tests never touch the real macOS Keychain.
    previous = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(previous)


@pytest.fixture
def statement_pdf():
    """Build a synthetic PDF statement: a title line, then each page's rows as a ruled table."""

    def build(pages: list[list[tuple[str, ...]]], password: str | None = None) -> bytes:
        document = FPDF()
        document.set_font("Helvetica", size=8)
        if password:
            document.set_encryption(owner_password="owner-only", user_password=password)
        for rows in pages:
            document.add_page()
            document.cell(0, 6, "EXAMPLE BANK STATEMENT", new_x="LMARGIN", new_y="NEXT")
            document.ln(4)
            with document.table() as table:
                for row in rows:
                    cells = table.row()
                    for cell in row:
                        cells.cell(cell)
        return bytes(document.output())

    return build


def account_answer(
    *,
    bank_name=None,
    last4=None,
    account_type="bank",
    currency="USD",
    opening=None,
    closing=None,
) -> dict:
    """One account as the mock LLM reports it from a statement."""
    return {
        "bank_name": bank_name,
        "account_last4": last4,
        "account_type": account_type,
        "currency": currency,
        "opening_balance": opening,
        "closing_balance": closing,
    }


def transaction_answer(date, description, amount, direction, last4=None) -> dict:
    return {
        "date": date,
        "description": description,
        "amount": amount,
        "direction": direction,
        "account_last4": last4,
    }


@pytest.fixture
def upload(client):
    """Upload `content` with the mock LLM scripted to read it as given: accounts and
    period first, then the transactions (one chunk), then category answers if any. The
    background work runs before the call returns (TestClient). Returns the import."""

    def run(
        content: bytes,
        *,
        accounts: list[dict],
        transactions: list[dict],
        period=(None, None),
        categories: dict | list | None = None,
        filename: str = "statement.csv",
        password: str | None = None,
    ) -> dict:
        client.app.state.llm.script(
            {"accounts": accounts, "period_start": period[0], "period_end": period[1]},
            {"transactions": transactions},
        )
        if categories is not None:
            client.app.state.llm.script(
                *(categories if isinstance(categories, list) else [categories])
            )
        mime = "application/pdf" if content.startswith(b"%PDF") else "text/csv"
        data = {"password": password} if password else {}
        response = client.post("/api/imports", data=data, files={"file": (filename, content, mime)})
        assert response.status_code == 202, response.text
        return client.get(f"/api/imports/{response.json()['id']}").json()

    return run


# A credit card statement in USD, March 2026, as CSV text.
CHASE_MARCH_CSV = (
    b"Chase card ending 4410\n"
    b"Transaction Date,Description,Amount\n"
    b"03/04/2026,GREENLEAF GROCERY,-42.10\n"
    b"03/09/2026,METRO TRANSIT,-2.75\n"
    b"03/12/2026,PAYMENT THANK YOU,500.00\n"
    b'03/20/2026,EXAMPLE ELECTRONICS,"-1,250.00"\n'
)
CHASE_MARCH_ACCOUNT = account_answer(
    bank_name="Chase", last4="4410", account_type="credit_card", currency="USD"
)
CHASE_MARCH_TRANSACTIONS = [
    transaction_answer("2026-03-04", "GREENLEAF GROCERY", "42.10", "out"),
    transaction_answer("2026-03-09", "METRO TRANSIT", "2.75", "out"),
    transaction_answer("2026-03-12", "PAYMENT THANK YOU", "500.00", "in"),
    transaction_answer("2026-03-20", "EXAMPLE ELECTRONICS", "1,250.00", "out"),
]
# A savings account in INR, April 2026.
HDFC_APRIL_CSV = (
    b"HDFC BANK Ltd. Account No XXXXXXXX4821\n"
    b"Opening Balance 1,24,706.78\n"
    b"Date,Narration,Withdrawal Amt.,Deposit Amt.,Closing Balance\n"
    b'03/04/26,UPI-SHARMA KIRANA STORE,"1,250.00",,"1,23,456.78"\n'
    b'05/04/26,SALARY EXAMPLE CORP,,"1,50,000.00","2,73,456.78"\n'
    b'11/04/26,ATM WDL EXAMPLE BRANCH,"10,000.00",,"2,63,456.78"\n'
    b"Closing Balance 2,63,456.78\n"
)
HDFC_APRIL_ACCOUNT = account_answer(
    bank_name="HDFC BANK Ltd.",
    last4="4821",
    currency="INR",
    opening="1,24,706.78",
    closing="2,63,456.78",
)
HDFC_APRIL_TRANSACTIONS = [
    transaction_answer("2026-04-03", "UPI-SHARMA KIRANA STORE", "1,250.00", "out"),
    transaction_answer("2026-04-05", "SALARY EXAMPLE CORP", "1,50,000.00", "in"),
    transaction_answer("2026-04-11", "ATM WDL EXAMPLE BRANCH", "10,000.00", "out"),
]
