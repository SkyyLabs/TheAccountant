from pathlib import Path

import pytest
from fastapi.testclient import TestClient

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
