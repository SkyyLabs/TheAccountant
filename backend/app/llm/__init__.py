from app.config import Settings
from app.llm.base import LlmProvider
from app.llm.mock import MockProvider
from app.llm.ollama import OllamaProvider


def get_llm_provider(settings: Settings) -> LlmProvider:
    if settings.llm_provider == "mock":
        return MockProvider()
    return OllamaProvider(settings.ollama_url, settings.llm_model)
