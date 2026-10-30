"""Top-k similarity search over persisted vectors."""

from __future__ import annotations

import heapq
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any

from receipt_ai.vector.similarity import cosine_similarity
from receipt_ai.vector.store import VectorStore
from receipt_ai.vector.validation import validate_vector


@dataclass(frozen=True)
class SearchResult:
    external_id: str
    score: float
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    vector_id: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "external_id": self.external_id,
            "score": round(self.score, 6),
            "content": self.content,
            "metadata": self.metadata,
            "vector_id": self.vector_id,
        }


def _matches_filter(metadata: dict[str, Any], metadata_filter: dict[str, Any] | None) -> bool:
    if not metadata_filter:
        return True
    return all(metadata.get(key) == value for key, value in metadata_filter.items())


def search(
    store: VectorStore,
    collection: str,
    query_vector: Sequence[float],
    k: int = 5,
    min_score: float | None = None,
    metadata_filter: dict[str, Any] | None = None,
) -> list[SearchResult]:
    """Return the top-k persisted vectors by cosine similarity."""
    if k < 1:
        raise ValueError("k must be at least 1")
    record = store.require_collection(collection)
    if record.metric != "cosine":
        raise ValueError(f"collection {collection!r} uses metric {record.metric!r}, not cosine")
    query = validate_vector(
        query_vector, dimension=record.dimension, allow_zero=True, name="query vector"
    )

    def candidates() -> Iterator[SearchResult]:
        for stored in store.list_vectors(collection):
            if not _matches_filter(stored.metadata, metadata_filter):
                continue
            score = cosine_similarity(query, stored.vector)
            if min_score is not None and score < min_score:
                continue
            yield SearchResult(
                external_id=stored.external_id,
                score=score,
                content=stored.content,
                metadata=stored.metadata,
                vector_id=stored.id,
            )

    best = heapq.nlargest(k, candidates(), key=lambda result: result.score)
    return sorted(best, key=lambda result: (-result.score, result.external_id))


def search_by_text(
    store: VectorStore,
    collection: str,
    text: str,
    embedder: Any,
    k: int = 5,
    min_score: float | None = None,
    metadata_filter: dict[str, Any] | None = None,
) -> list[SearchResult]:
    """Embed text with the provided embedder and run similarity search."""
    vector = embedder.embed(text)
    return search(
        store,
        collection,
        vector,
        k=k,
        min_score=min_score,
        metadata_filter=metadata_filter,
    )
