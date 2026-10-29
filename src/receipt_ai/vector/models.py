"""Data objects for the vector store."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from receipt_ai.vector.validation import Vector


@dataclass(frozen=True)
class Collection:
    id: int
    name: str
    dimension: int
    metric: str
    created_at: str


@dataclass(frozen=True)
class StoredVector:
    id: int
    collection: str
    external_id: str
    content: str
    vector: Vector
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "collection": self.collection,
            "external_id": self.external_id,
            "content": self.content,
            "vector": list(self.vector),
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
