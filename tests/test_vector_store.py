from __future__ import annotations

import json
from pathlib import Path

import pytest

from receipt_ai.vector.embedding import HashingEmbedder
from receipt_ai.vector.search import search, search_by_text
from receipt_ai.vector.similarity import cosine_similarity
from receipt_ai.vector.store import CollectionNotFoundError, VectorStore
from receipt_ai.vector.validation import VectorValidationError


@pytest.fixture()
def store(tmp_path: Path) -> VectorStore:
    database = VectorStore(tmp_path / "vectors.db")
    database.create_collection("receipts", 3)
    yield database
    database.close()


def test_create_collection_is_idempotent(store: VectorStore) -> None:
    first = store.create_collection("receipts", 3)
    second = store.create_collection("receipts", 3)
    assert first.id == second.id
    with pytest.raises(ValueError):
        store.create_collection("receipts", 4)


def test_upsert_get_and_update(store: VectorStore) -> None:
    vector_id = store.upsert(
        "receipts", "r1", [1, 2, 3], content="Green Bowl", metadata={"date": "2026-06-20"}
    )
    stored = store.get("receipts", "r1")
    assert stored is not None
    assert stored.id == vector_id
    assert stored.content == "Green Bowl"
    assert stored.metadata == {"date": "2026-06-20"}

    updated_id = store.upsert(
        "receipts", "r1", [3, 2, 1], content="Green Bowl updated", metadata={"date": "2026-06-21"}
    )
    assert updated_id == vector_id
    updated = store.get("receipts", "r1")
    assert updated is not None
    assert updated.content == "Green Bowl updated"
    assert updated.vector == (3.0, 2.0, 1.0)
    assert store.count("receipts") == 1


def test_delete_and_missing_collection(store: VectorStore) -> None:
    store.upsert("receipts", "r1", [1, 0, 0])
    assert store.delete("receipts", "r1") is True
    assert store.delete("receipts", "r1") is False
    with pytest.raises(CollectionNotFoundError):
        store.get("missing", "r1")


def test_validation_errors(store: VectorStore) -> None:
    with pytest.raises(VectorValidationError):
        store.upsert("receipts", "r1", [1, 2])
    with pytest.raises(VectorValidationError):
        store.upsert("receipts", "r1", [0, 0, 0])
    with pytest.raises(ValueError):
        store.upsert("receipts", "  ", [1, 2, 3])
    with pytest.raises(ValueError):
        store.upsert("receipts", "r1", [1, 2, 3], metadata={"bad": object()})


def test_persistence_across_connections(tmp_path: Path) -> None:
    path = tmp_path / "vectors.db"
    first = VectorStore(path)
    first.create_collection("receipts", 2)
    first.upsert("receipts", "r1", [1, 1], content="persisted", metadata={"kind": "food"})
    first.close()

    second = VectorStore(path)
    stored = second.get("receipts", "r1")
    assert stored is not None
    assert stored.content == "persisted"
    assert second.list_collections()[0].name == "receipts"
    second.close()


def test_drop_collection_cascades_vectors(store: VectorStore) -> None:
    store.upsert("receipts", "r1", [1, 0, 0])
    assert store.drop_collection("receipts") is True
    assert store.get_collection("receipts") is None
    row = store.connection.execute("SELECT COUNT(*) AS count FROM vectors").fetchone()
    assert row["count"] == 0


def test_persisted_top_k_search(tmp_path: Path) -> None:
    path = tmp_path / "vectors.db"
    first = VectorStore(path)
    first.create_collection("receipts", 3)
    first.upsert("receipts", "burger", [1, 0, 0], content="burger", metadata={"merchant": "A"})
    first.upsert("receipts", "salad", [0.8, 0.2, 0], content="salad", metadata={"merchant": "B"})
    first.upsert("receipts", "coffee", [0, 1, 0], content="coffee", metadata={"merchant": "C"})
    first.close()

    second = VectorStore(path)
    results = search(second, "receipts", [1, 0, 0], k=2)
    assert [result.external_id for result in results] == ["burger", "salad"]
    assert results[0].score == pytest.approx(1.0)
    assert results[0].metadata == {"merchant": "A"}

    filtered = search(second, "receipts", [1, 0, 0], k=3, metadata_filter={"merchant": "C"})
    assert [result.external_id for result in filtered] == ["coffee"]

    assert search(second, "receipts", [1, 0, 0], k=3, min_score=0.5)[-1].external_id == "salad"
    assert search(second, "receipts", [1, 0, 0], k=3, min_score=2.0) == []
    second.close()


def test_search_rejects_non_cosine_metric(store: VectorStore) -> None:
    store.create_collection("dots", 3, metric="dot")
    store.upsert("dots", "r1", [1, 0, 0])
    with pytest.raises(ValueError):
        search(store, "dots", [1, 0, 0])


def test_search_with_zero_query(store: VectorStore) -> None:
    store.upsert("receipts", "b", [1, 0, 0])
    store.upsert("receipts", "a", [0, 1, 0])
    results = search(store, "receipts", [0, 0, 0], k=2)
    assert [result.external_id for result in results] == ["a", "b"]
    assert all(result.score == 0.0 for result in results)


def test_hashing_embedder_is_deterministic_and_similarity_aware() -> None:
    embedder = HashingEmbedder(dimension=128)
    first = embedder.embed("Green Bowl hamburger and fries")
    second = embedder.embed("Green Bowl hamburger and fries")
    related = embedder.embed("hamburger fries Green Bowl")
    unrelated = embedder.embed("monthly electricity invoice payment")
    assert first == second
    assert cosine_similarity(first, related) > cosine_similarity(first, unrelated)
    assert any(value != 0.0 for value in embedder.embed(""))


def test_search_by_text(store: VectorStore) -> None:
    embedder = HashingEmbedder(dimension=3)
    store.upsert("receipts", "burger", embedder.embed("Green Bowl burger"), "Green Bowl burger")
    store.upsert("receipts", "coffee", embedder.embed("Blue Cafe coffee"), "Blue Cafe coffee")
    results = search_by_text(store, "receipts", "Green Bowl burger", embedder, k=1)
    assert results[0].external_id == "burger"


def test_metadata_is_json_serializable(store: VectorStore) -> None:
    store.upsert("receipts", "r1", [1, 0, 0], metadata={"items": ["burger", "fries"], "n": 2})
    stored = store.get("receipts", "r1")
    assert stored is not None
    assert json.loads(json.dumps(stored.metadata)) == {"items": ["burger", "fries"], "n": 2}
