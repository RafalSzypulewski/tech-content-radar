"""Multilingual embeddings and topic similarity.

Vectors are plain lists of floats so this module works without numpy; only
SentenceTransformerEmbedder needs the [local] extras.
"""

import math
from typing import Protocol

from radar.models import RawItem
from radar.store import Store

MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"
# The model reads at most 128 tokens, so longer text adds nothing.
ITEM_TEXT_CHARS = 500


class Embedder(Protocol):
    """Anything that turns texts into vectors (the real model or a test fake)."""

    model_name: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class SentenceTransformerEmbedder:
    """The real multilingual model, loaded on first use."""

    def __init__(self, model_name: str = MODEL_NAME) -> None:
        self.model_name = model_name
        self._model = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
        return self._model.encode(texts, normalize_embeddings=True).tolist()


def item_text(item: RawItem) -> str:
    """The text that represents an item: title plus the start of its text."""
    return f"{item.title}\n{item.text[:ITEM_TEXT_CHARS]}"


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two vectors."""
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def embed_items(store: Store, embedder: Embedder, items: list[RawItem]) -> dict[str, list[float]]:
    """Vectors for `items`, computing and caching only the ones not cached yet."""
    ids = [item.id for item in items]
    vectors = store.get_embeddings(embedder.model_name, ids)
    missing = [item for item in items if item.id not in vectors]
    if missing:
        new = dict(
            zip(
                [item.id for item in missing],
                embedder.embed([item_text(item) for item in missing]),
                strict=True,
            )
        )
        store.put_embeddings(embedder.model_name, new)
        vectors.update(new)
    return vectors


def relevance(vector: list[float], profile_vectors: list[list[float]]) -> float:
    """Max cosine similarity to any topic profile, clamped to 0..1."""
    return max(0.0, max((cosine(vector, p) for p in profile_vectors), default=0.0))
