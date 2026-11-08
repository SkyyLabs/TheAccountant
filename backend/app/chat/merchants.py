"""Which merchants a search term means ("coffee" -> the coffee shops): chat's retrieval
step, over merchant names rather than transactions, so every transaction of a matched
merchant is counted afterwards.

- A merchant is found when its embedding is similar enough to the term's and close to the
  best match. Measured on 2026-11-08 with embeddinggemma over 60 synthetic merchants and 12
  terms: precision 0.95, recall 0.90 (see PROJECT_STATE).
- A merchant whose name has the term as a word is always found ("uber" -> "uber eats").

Merchants are embedded once per embedding model; new ones are embedded after each import
and, if that was missed (Ollama off), before the next search.
"""

import logging
import math
from array import array

from app import db
from app.categorize.categorizer import merchant_key
from app.llm.base import LlmProvider

logger = logging.getLogger(__name__)

MIN_SIMILARITY = 0.34
MAX_BELOW_BEST = 0.12
BATCH_SIZE = 100


def embed_new_merchants(connection, provider: LlmProvider) -> int:
    """Embed the merchants that have no vector for the current model yet."""
    keys = db.merchant_keys_without_embedding(connection, provider.embedding_model)
    for start in range(0, len(keys), BATCH_SIZE):
        batch = keys[start : start + BATCH_SIZE]
        vectors = provider.embed(batch, query=False)
        db.add_merchant_embeddings(
            connection,
            provider.embedding_model,
            [
                (key, array("f", _unit(vector)).tobytes())
                for key, vector in zip(batch, vectors, strict=True)
            ],
        )
    if keys:
        logger.info("embedded merchants=%d", len(keys))
    return len(keys)


def find_merchants(connection, provider: LlmProvider, term: str) -> list[str]:
    """Merchant keys the term means, best match first."""
    embed_new_merchants(connection, provider)
    words = merchant_key(term)
    if not words:
        return []
    (query,) = provider.embed([words], query=True)
    query = _unit(query)
    similarity = {
        key: sum(a * b for a, b in zip(query, array("f", vector), strict=True))
        for key, vector in db.merchant_embeddings(connection, provider.embedding_model)
    }
    best = max(similarity.values(), default=0.0)
    found = {
        key: score
        for key, score in similarity.items()
        if score >= MIN_SIMILARITY and score >= best - MAX_BELOW_BEST
    }
    for key in similarity:
        if f" {words} " in f" {key} ":
            found[key] = 1.0  # named outright: always first
    return sorted(found, key=lambda key: (-found[key], key))


def _unit(vector: list[float]) -> list[float]:
    length = math.sqrt(sum(x * x for x in vector))
    return [x / length for x in vector] if length else [0.0] * len(vector)
