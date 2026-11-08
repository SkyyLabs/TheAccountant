import json
import logging
import time
import urllib.error
import urllib.request

from app.llm.base import LlmError, LlmUnavailable

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 180


class OllamaProvider:
    """Local Ollama only: the URL is validated as loopback at startup (config.py)."""

    def __init__(self, base_url: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    def complete_json(self, system: str, prompt: str, schema: dict) -> dict:
        body = json.dumps(
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "format": schema,
                "stream": False,
                "options": {"temperature": 0},
            }
        ).encode()
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                raise LlmUnavailable(
                    f"model {self.model} is not installed: run ollama pull {self.model}"
                ) from None
            raise LlmUnavailable(f"Ollama returned HTTP {error.code}") from None
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            raise LlmUnavailable("Ollama is not running: start it with ollama serve") from None
        # Timings only: prompts and answers contain statement contents and are never logged.
        logger.info("ollama call model=%s seconds=%.1f", self.model, time.monotonic() - started)
        try:
            answer = json.loads(payload["message"]["content"])
        except (KeyError, TypeError, json.JSONDecodeError):
            raise LlmError("the model did not answer with JSON") from None
        if not isinstance(answer, dict):
            raise LlmError("the model did not answer with a JSON object")
        return answer
