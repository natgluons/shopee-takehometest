"""Persistent vector CRUD operations on SQLite."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

from receipt_ai.vector.models import Collection, StoredVector
from receipt_ai.vector.schema import initialize_path
from receipt_ai.vector.validation import Vector, validate_dimension, validate_vector

VALID_METRICS = frozenset({"cosine", "dot", "euclidean"})


class CollectionNotFoundError(KeyError):
    """Raised when a collection does not exist."""


class VectorStore:
    """A small self-hosted vector database backed by SQLite."""

    def __init__(
        self, path: str | Path | None = None, connection: sqlite3.Connection | None = None
    ):
        if connection is not None:
            self.connection = connection
            self._owns_connection = False
        elif path is not None:
            self.connection = initialize_path(path)
            self._owns_connection = True
        else:
            raise ValueError("either path or connection is required")

    def close(self) -> None:
        if self._owns_connection:
            self.connection.close()

    def __enter__(self) -> VectorStore:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def create_collection(self, name: str, dimension: int, metric: str = "cosine") -> Collection:
        name = name.strip()
        if not name:
            raise ValueError("collection name must not be empty")
        validate_dimension(dimension)
        if metric not in VALID_METRICS:
            raise ValueError(f"metric must be one of {sorted(VALID_METRICS)}")
        with self.connection:
            self.connection.execute(
                "INSERT OR IGNORE INTO collections(name, dimension, metric) VALUES(?, ?, ?)",
                (name, dimension, metric),
            )
        collection = self.get_collection(name)
        if collection is None:
            raise RuntimeError(f"collection {name!r} could not be created")
        if collection.dimension != dimension or collection.metric != metric:
            raise ValueError(
                f"collection {name!r} already exists with dimension "
                f"{collection.dimension} and metric {collection.metric!r}"
            )
        return collection

    def get_collection(self, name: str) -> Collection | None:
        row = self.connection.execute(
            "SELECT id, name, dimension, metric, created_at FROM collections WHERE name = ?",
            (name,),
        ).fetchone()
        return None if row is None else Collection(**dict(row))

    def require_collection(self, name: str) -> Collection:
        collection = self.get_collection(name)
        if collection is None:
            raise CollectionNotFoundError(name)
        return collection

    def list_collections(self) -> list[Collection]:
        rows = self.connection.execute(
            "SELECT id, name, dimension, metric, created_at FROM collections ORDER BY name"
        ).fetchall()
        return [Collection(**dict(row)) for row in rows]

    def drop_collection(self, name: str) -> bool:
        with self.connection:
            cursor = self.connection.execute("DELETE FROM collections WHERE name = ?", (name,))
        return cursor.rowcount > 0

    def upsert(
        self,
        collection: str,
        external_id: str,
        vector: Sequence[float],
        content: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> int:
        record = self.require_collection(collection)
        external_id = external_id.strip()
        if not external_id:
            raise ValueError("external_id must not be empty")
        values = validate_vector(vector, dimension=record.dimension, name="vector")
        metadata = metadata or {}
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be a dictionary")
        try:
            metadata_json = json.dumps(metadata, sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise ValueError("metadata must be JSON serializable") from exc
        vector_json = json.dumps(list(values))
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO vectors(collection_id, external_id, content, vector, metadata)
                VALUES(?, ?, ?, ?, ?)
                ON CONFLICT(collection_id, external_id) DO UPDATE SET
                    content = excluded.content,
                    vector = excluded.vector,
                    metadata = excluded.metadata,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (record.id, external_id, content, vector_json, metadata_json),
            )
        row = self.connection.execute(
            "SELECT id FROM vectors WHERE collection_id = ? AND external_id = ?",
            (record.id, external_id),
        ).fetchone()
        if row is None:
            raise RuntimeError("vector upsert failed")
        return int(row["id"])

    def add(
        self,
        collection: str,
        external_id: str,
        vector: Sequence[float],
        content: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Alias for upsert used by callers that prefer create semantics."""
        return self.upsert(collection, external_id, vector, content, metadata)

    def get(self, collection: str, external_id: str) -> StoredVector | None:
        record = self.require_collection(collection)
        row = self.connection.execute(
            """
            SELECT id, collection_id, external_id, content, vector, metadata, created_at, updated_at
            FROM vectors WHERE collection_id = ? AND external_id = ?
            """,
            (record.id, external_id.strip()),
        ).fetchone()
        return None if row is None else self._row_to_vector(row, record.name)

    def get_by_id(self, vector_id: int) -> StoredVector | None:
        row = self.connection.execute(
            """
            SELECT v.id, v.collection_id, v.external_id, v.content, v.vector, v.metadata,
                   v.created_at, v.updated_at, c.name AS collection_name
            FROM vectors v JOIN collections c ON c.id = v.collection_id
            WHERE v.id = ?
            """,
            (vector_id,),
        ).fetchone()
        return None if row is None else self._row_to_vector(row, row["collection_name"])

    def delete(self, collection: str, external_id: str) -> bool:
        record = self.require_collection(collection)
        with self.connection:
            cursor = self.connection.execute(
                "DELETE FROM vectors WHERE collection_id = ? AND external_id = ?",
                (record.id, external_id.strip()),
            )
        return cursor.rowcount > 0

    def list_vectors(self, collection: str, batch_size: int = 1000) -> Iterator[StoredVector]:
        record = self.require_collection(collection)
        cursor = self.connection.execute(
            """
            SELECT id, collection_id, external_id, content, vector, metadata, created_at, updated_at
            FROM vectors WHERE collection_id = ? ORDER BY id
            """,
            (record.id,),
        )
        while True:
            rows = cursor.fetchmany(batch_size)
            if not rows:
                break
            for row in rows:
                yield self._row_to_vector(row, record.name)

    def count(self, collection: str) -> int:
        record = self.require_collection(collection)
        row = self.connection.execute(
            "SELECT COUNT(*) AS count FROM vectors WHERE collection_id = ?",
            (record.id,),
        ).fetchone()
        return int(row["count"]) if row else 0

    def clear(self, collection: str) -> int:
        record = self.require_collection(collection)
        with self.connection:
            cursor = self.connection.execute(
                "DELETE FROM vectors WHERE collection_id = ?", (record.id,)
            )
        return cursor.rowcount

    @staticmethod
    def _row_to_vector(row: sqlite3.Row, collection_name: str) -> StoredVector:
        raw_vector: Vector = tuple(float(value) for value in json.loads(row["vector"]))
        try:
            metadata = json.loads(row["metadata"])
        except (TypeError, ValueError):
            metadata = {}
        return StoredVector(
            id=int(row["id"]),
            collection=collection_name,
            external_id=str(row["external_id"]),
            content=str(row["content"]),
            vector=raw_vector,
            metadata=metadata if isinstance(metadata, dict) else {},
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
