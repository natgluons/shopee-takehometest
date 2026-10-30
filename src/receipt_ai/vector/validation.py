"""Vector validation helpers using only the standard library."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

Vector = tuple[float, ...]


class VectorValidationError(ValueError):
    """Raised when a vector cannot be stored or compared."""


def validate_vector(
    vector: Sequence[float] | Iterable[float],
    dimension: int | None = None,
    allow_zero: bool = False,
    name: str = "vector",
) -> Vector:
    """Validate and convert a vector to an immutable tuple of floats."""
    if isinstance(vector, (str, bytes)):
        raise VectorValidationError(f"{name} must be a sequence of numbers")
    try:
        values = tuple(float(value) for value in vector)
    except (TypeError, ValueError) as exc:
        raise VectorValidationError(f"{name} must contain only numbers") from exc
    if not values:
        raise VectorValidationError(f"{name} must not be empty")
    if dimension is not None and len(values) != dimension:
        raise VectorValidationError(f"{name} has dimension {len(values)}, expected {dimension}")
    if not all(math.isfinite(value) for value in values):
        raise VectorValidationError(f"{name} must contain only finite values")
    if not allow_zero and not any(value != 0.0 for value in values):
        raise VectorValidationError(f"{name} must not be the zero vector")
    return values


def validate_dimension(dimension: int, name: str = "dimension") -> int:
    """Validate a positive integer dimension."""
    if isinstance(dimension, bool) or not isinstance(dimension, int):
        raise VectorValidationError(f"{name} must be an integer")
    if dimension < 1:
        raise VectorValidationError(f"{name} must be at least 1")
    return dimension


def validate_vectors(
    vectors: Iterable[Sequence[float]], dimension: int | None = None
) -> list[Vector]:
    """Validate a batch of vectors."""
    return [
        validate_vector(vector, dimension=dimension, name=f"vector[{index}]")
        for index, vector in enumerate(vectors)
    ]


def l2_norm(vector: Sequence[float]) -> float:
    """Euclidean norm computed with a stable sum."""
    return math.sqrt(math.fsum(float(value) ** 2 for value in vector))


def normalize_vector(
    vector: Sequence[float], allow_zero: bool = False, name: str = "vector"
) -> Vector:
    """Return a unit-length copy of the vector."""
    values = validate_vector(vector, allow_zero=allow_zero, name=name)
    norm = l2_norm(values)
    if norm == 0.0:
        if allow_zero:
            return values
        raise VectorValidationError(f"{name} must not be the zero vector")
    return tuple(value / norm for value in values)
