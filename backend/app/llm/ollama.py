import json
import logging
import time
import urllib.error
import urllib.request

from app.llm.base import LlmError, LlmUnavailable

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 180

# embeddinggemma is trained with these task prefixes; without them it matches far worse
# (measured 2026-11-08). Other models get the text as is.
EMBEDDING_PREFIXES = {
    "embeddinggemma": ("task: search result | query: ", "title: none | text: "),
}


class OllamaProvider:
    """Local Ollama only: the URL is validated as loopback at startup (config.py)."""

    def __init__(self, base_url: str, model: str, embedding_model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.embedding_model = embedding_model

    def complete_json(self, system: str, prompt: str, schema: dict) -> dict:
        payload = self._post(
            "/api/chat",
            {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "format": schema,
                "stream": False,
                # Reasoning models (qwen3) answer directly; the schema already constrains them.
                "think": False,
                "options": {"temperature": 0},
            },
            self.model,
        )
        try:
            answer = json.loads(payload["message"]["content"])
        except (KeyError, TypeError, json.JSONDecodeError):
            raise LlmError("the model did not answer with JSON") from None
        if not isinstance(answer, dict):
            raise LlmError("the model did not answer with a JSON object")
        return answer

    def embed(self, texts: list[str], *, query: bool) -> list[list[float]]:
        query_prefix, text_prefix = EMBEDDING_PREFIXES.get(
            self.embedding_model.split(":")[0], ("", "")
        )
        prefix = query_prefix if query else text_prefix
        payload = self._post(
            "/api/embed",
            {"model": self.embedding_model, "input": [prefix + text for text in texts]},
            self.embedding_model,
        )
        vectors = payload.get("embeddings") if isinstance(payload, dict) else None
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise LlmError("the embedding model did not return one vector per text")
        return vectors

    def _post(self, path: str, body: dict, model: str) -> dict:
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=json.dumps(body).encode(),
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
                    f"model {model} is not installed: run ollama pull {model}"
                ) from None
            raise LlmUnavailable(f"Ollama returned HTTP {error.code}") from None
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            raise LlmUnavailable("Ollama is not running: start it with ollama serve") from None
        # Timings only: prompts and answers contain statement contents and are never logged.
        logger.info("ollama %s model=%s seconds=%.1f", path, model, time.monotonic() - started)
        return payload
