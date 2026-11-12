"""Retrieval: a pluggable embedder interface, TF-IDF by default.

The default is deliberately boring: TF-IDF + cosine similarity, offline,
deterministic, no API key, no download. That is the point — the security
experiment (what happens when retrieved text is hostile) must be
reproducible without a paid model or a network call.

A dense embedder is available as an opt-in: see
:class:`SentenceTransformerEmbedder`. It is only imported when used.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np

from .ingest import Chunk


class Embedder(Protocol):
    """Anything that turns a list of texts into a 2-D array of vectors."""

    def embed(self, texts: list[str]) -> np.ndarray: ...


@dataclass
class ScoredChunk:
    chunk: Chunk
    score: float


class TfidfEmbedder:
    """TF-IDF embedder (scikit-learn). Deterministic, offline, no key."""

    def __init__(self) -> None:
        from sklearn.feature_extraction.text import TfidfVectorizer

        self._vectorizer = TfidfVectorizer(stop_words="english")
        self._fitted = False

    def fit(self, texts: list[str]) -> None:
        self._vectorizer.fit(texts)
        self._fitted = True

    def embed(self, texts: list[str]) -> np.ndarray:
        if not self._fitted:
            self.fit(texts)
        return self._vectorizer.transform(texts).toarray()


class SentenceTransformerEmbedder:
    """Optional dense embedder. Requires ``sentence-transformers``.

    Not used by default and never required. Install it only if you want to
    compare dense vs. TF-IDF retrieval on the same evaluation set.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(model_name)

    def embed(self, texts: list[str]) -> np.ndarray:
        return np.asarray(self._model.encode(texts, normalize_embeddings=True))


def _cosine(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    a_norm = a / (np.linalg.norm(a, axis=1, keepdims=True) + 1e-12)
    b_norm = b / (np.linalg.norm(b, axis=1, keepdims=True) + 1e-12)
    return a_norm @ b_norm.T


class Retriever:
    """Top-k retrieval over a fixed set of chunks."""

    def __init__(self, chunks: list[Chunk], embedder: Embedder | None = None) -> None:
        if not chunks:
            raise ValueError("Retriever needs at least one chunk")
        self.chunks = chunks
        self.embedder = embedder or TfidfEmbedder()
        if isinstance(self.embedder, TfidfEmbedder):
            self.embedder.fit([c.text for c in chunks])
        self._vectors = self.embedder.embed([c.text for c in chunks])

    def search(self, query: str, top_k: int = 3) -> list[ScoredChunk]:
        """Return the ``top_k`` chunks by cosine similarity, best first."""
        if not query.strip():
            return []
        q = self.embedder.embed([query])[0]
        scores = _cosine(self._vectors, q.reshape(1, -1)).flatten()
        order = np.argsort(-scores)[:top_k]
        return [ScoredChunk(chunk=self.chunks[i], score=float(scores[i])) for i in order]
