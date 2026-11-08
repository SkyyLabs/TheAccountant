"""The one interface every LLM provider implements. Business logic never asks which
provider is active. There is no cloud provider and none may be added."""

from typing import Protocol


class LlmError(Exception):
    """The model answered, but not with usable JSON."""


class LlmUnavailable(LlmError):
    """The local model could not be reached (Ollama not running, model not pulled)."""


class LlmProvider(Protocol):
    def complete_json(self, system: str, prompt: str, schema: dict) -> dict:
        """Return the model's answer, constrained to the JSON schema, as a dict. The caller
        still validates it: model output is untrusted input."""
        ...
