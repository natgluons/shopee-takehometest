from __future__ import annotations

import math

import pytest

from receipt_ai.vector.similarity import (
    cosine_similarity,
    dot_product,
    euclidean_distance,
    top_k_cosine,
)
from receipt_ai.vector.validation import VectorValidationError


def test_identical_vectors_have_similarity_one() -> None:
    assert cosine_similarity([1, 2, 3], [1, 2, 3]) == pytest.approx(1.0)


def test_orthogonal_vectors_have_similarity_zero() -> None:
    assert cosine_similarity([1, 0], [0, 1]) == 0.0


def test_opposite_vectors_have_similarity_negative_one() -> None:
    assert cosine_similarity([1, 2], [-1, -2]) == pytest.approx(-1.0)


def test_scaled_vectors_have_similarity_one() -> None:
    assert cosine_similarity([1, 2, 3], [10, 20, 30]) == pytest.approx(1.0)


def test_zero_vector_similarity_is_zero() -> None:
    assert cosine_similarity([0, 0], [1, 2]) == 0.0
    assert cosine_similarity([0, 0], [0, 0]) == 0.0


def test_single_element_vectors() -> None:
    assert cosine_similarity([5], [2]) == pytest.approx(1.0)
    assert cosine_similarity([5], [-2]) == pytest.approx(-1.0)


def test_negative_values() -> None:
    assert cosine_similarity([-1, 0], [-1, 0]) == pytest.approx(1.0)


def test_mismatched_dimensions_raise() -> None:
    with pytest.raises(VectorValidationError):
        cosine_similarity([1, 2], [1, 2, 3])
    with pytest.raises(VectorValidationError):
        dot_product([1, 2], [1, 2, 3])
    with pytest.raises(VectorValidationError):
        euclidean_distance([1, 2], [1, 2, 3])


def test_empty_vector_raises() -> None:
    with pytest.raises(VectorValidationError):
        cosine_similarity([], [])


def test_non_finite_values_raise() -> None:
    with pytest.raises(VectorValidationError):
        cosine_similarity([1, math.nan], [1, 2])
    with pytest.raises(VectorValidationError):
        cosine_similarity([1, math.inf], [1, 2])


def test_dot_product_and_euclidean_distance() -> None:
    assert dot_product([1, 2, 3], [4, 5, 6]) == 32.0
    assert euclidean_distance([0, 0], [3, 4]) == pytest.approx(5.0)


def test_top_k_orders_by_score_then_identifier() -> None:
    candidates = [
        ("b", [1, 0]),
        ("a", [1, 0]),
        ("c", [0, 1]),
        ("d", [-1, 0]),
    ]
    results = top_k_cosine([1, 0], candidates, k=3)
    assert [identifier for identifier, _ in results] == ["a", "b", "c"]
    assert results[0][1] == pytest.approx(1.0)
    assert results[1][1] == pytest.approx(1.0)
    assert results[2][1] == pytest.approx(0.0)


def test_top_k_handles_fewer_candidates_than_k() -> None:
    results = top_k_cosine([1, 0], [("only", [1, 0])], k=5)
    assert results == [("only", pytest.approx(1.0))]


def test_top_k_rejects_invalid_k() -> None:
    with pytest.raises(ValueError):
        top_k_cosine([1, 0], [], k=0)


def test_top_k_with_zero_query_scores_everything_zero() -> None:
    results = top_k_cosine([0, 0], [("b", [1, 0]), ("a", [0, 1])], k=2)
    assert [identifier for identifier, _ in results] == ["a", "b"]
    assert all(score == 0.0 for _, score in results)
