from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    database_path: Path = REPO_ROOT / "data" / "accountant.db"
    ollama_url: str = "http://127.0.0.1:11434"
    llm_provider: Literal["ollama", "mock"] = "ollama"
    llm_model: str = "qwen3:8b"
    port: int = 8765
    max_upload_mb: int = 25
    # Downloaded once by `make models`; Docling never fetches anything at runtime.
    docling_models_path: Path = REPO_ROOT / "models" / "docling"

    @field_validator("ollama_url")
    @classmethod
    def ollama_must_be_local(cls, value: str) -> str:
        # The product promise: nothing leaves the machine. Fail at startup, not on first call.
        host = urlparse(value).hostname
        if host not in LOOPBACK_HOSTS:
            raise ValueError(f"OLLAMA_URL must point to this machine, got host {host!r}")
        return value
