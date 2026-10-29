"""Cosine similarity and top-k ranking without a numerical library.

The implementation uses ``math.fsum`` for a stable sum and validates dimensions and finite values.
A zero vector has no direction, so cosine similarity with a zero vector is defined as 0.0 here.
"""

from __future__ import annotations

import heapq
import math
from collections.abc import Iterable, Sequence

from receipt_ai.vector.validation import (
    Vector,
    VectorValidationError,
    l2_norm,
    validate_vector,
)


def dot_product(left: Sequence[float], right: Sequence[float]) -> float:
    """Return the dot product of two equal-length vectors."""
    if len(left) != len(right):
        raise VectorValidationError(
            f"dimension mismatch: {len(left)} and {len(right)}"
        )
    return math.fsum(float(a) * float(b) for a, b in zip(left, right, strict=True))


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    """Return cosine similarity in the range [-1.0, 1.0]."""
    first = validate_vector(left, allow_zero=True, name="left vector")
    second = validate_vector(right, allow_zero=True, name="right vector")
    if len(first) != len(second):
        raise VectorValidationError(
            f"dimension mismatch: {len(first)} and {len(second)}"
        )
    first_norm = l2_norm(first)
    second_norm = l2_norm(second)
    if first_norm == 0.0 or second_norm == 0.0:
        return 0.0
    similarity = math.fsum(a * b for a, b in zip(first, second, strict=True))
    similarity /= first_norm * second_norm
    return max(-1.0, min(1.0, similarity))


def euclidean_distance(left: Sequence[float], right: Sequence[float]) -> float:
    """Return Euclidean distance between two equal-length vectors."""
    if len(left) != len(right):
        raise VectorValidationError(
            f"dimension mismatch: {len(left)} and {len(right)}"
        )
    return math.sqrt(math.fsum((float(a) - float(b)) ** 2 for a, b in zip(left, right, strict=True)))


def top_k_cosine(
    query: Sequence[float],
    candidates: Iterable[tuple[str, Sequence[float]]],
    k: int = 5,
) -> list[tuple[str, float]]:
    """Return the top ``k`` candidates ordered by cosine score then identifier."""
    if k < 1:
        raise ValueError("k must be at least 1")
    query_vector: Vector = validate_vector(query, allow_zero=True, name="query vector")

    def score_candidate(
        item: tuple[str, Sequence[float]],
    ) -> tuple[str, float]:
        identifier, vector = item
        score = cosine_similarity(query_vector, vector)
        return str(identifier), score

    best = heapq.nlargest(k, (score_candidate(item) for item in candidates), key=lambda x: x[1])
    return sorted(best, key=lambda item: (-item[1], item[0]))
