import pytest
from pydantic import ValidationError

from app.config import Settings


@pytest.mark.parametrize(
    "url", ["http://127.0.0.1:11434", "http://localhost:11434", "http://[::1]:11434"]
)
def test_loopback_ollama_url_is_accepted(url):
    assert Settings(_env_file=None, ollama_url=url).ollama_url == url


@pytest.mark.parametrize("url", ["https://api.example.com", "http://192.168.1.20:11434"])
def test_non_loopback_ollama_url_is_rejected_at_startup(url):
    with pytest.raises(ValidationError, match="OLLAMA_URL must point to this machine"):
        Settings(_env_file=None, ollama_url=url)


def test_unknown_llm_provider_is_rejected_at_startup():
    with pytest.raises(ValidationError, match="llm_provider"):
        Settings(_env_file=None, llm_provider="openai")
