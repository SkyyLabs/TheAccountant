from app.llm.base import LlmError, LlmUnavailable


class MockProvider:
    """Deterministic stand-in used by tests. Script answers with `script`; each call takes
    the next one. An exception instance is raised instead of returned. With nothing
    scripted, the provider behaves as if Ollama were not running.

    Embeddings come from `vectors` (text -> vector, set by a test); any other text gets a
    vector that is similar to nothing."""

    embedding_model = "mock"

    def __init__(self) -> None:
        self.answers: list[dict | Exception] = []
        self.prompts: list[str] = []
        self.vectors: dict[str, list[float]] = {}
        self.embedded: list[str] = []

    def script(self, *answers: dict | Exception) -> None:
        self.answers.extend(answers)

    def complete_json(self, system: str, prompt: str, schema: dict) -> dict:
        self.prompts.append(prompt)
        if not self.answers:
            raise LlmUnavailable("mock provider has no scripted answer")
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        if not isinstance(answer, dict):
            raise LlmError("scripted answer is not an object")
        return answer

    def embed(self, texts: list[str], *, query: bool) -> list[list[float]]:
        self.embedded.extend(texts)
        return [self.vectors.get(text, [0.0, 0.0, 0.0]) for text in texts]
