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
    return Settings(_env_file=None, database_path=tmp_path / "test.db", llm_provider="mock")


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
