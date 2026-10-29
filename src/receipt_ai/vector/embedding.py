"""Deterministic hashed text embeddings using only the standard library.

This is a feature-hashing bag-of-words embedder. It is not a semantic model. It is intentionally
local and dependency free so the receipt retrieval path works offline and the vector database can be
demonstrated without downloading model weights.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from collections.abc import Iterable

from receipt_ai.vector.validation import Vector, validate_dimension

TOKEN_RE = re.compile(r"[a-z0-9]+")


class HashingEmbedder:
    """Map text to a fixed-size signed feature-hashing vector."""

    def __init__(self, dimension: int = 256) -> None:
        self.dimension = validate_dimension(dimension)
        self.name = f"hashing-{self.dimension}"

    @staticmethod
    def tokenize(text: str) -> list[str]:
        return TOKEN_RE.findall(text.lower())

    def embed(self, text: str) -> Vector:
        tokens = self.tokenize(text)
        if not tokens:
            tokens = ["__empty__"]
        counts = Counter(tokens)
        values = [0.0] * self.dimension
        for token, count in counts.items():
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
            index = int.from_bytes(digest[:8], "big") % self.dimension
            sign = 1.0 if digest[8] & 1 else -1.0
            values[index] += sign * (1.0 + math.log(count))
        norm = math.sqrt(math.fsum(value * value for value in values))
        if norm == 0.0:
            values[0] = 1.0
            return tuple(values)
        return tuple(value / norm for value in values)

    def embed_many(self, texts: Iterable[str]) -> list[Vector]:
        return [self.embed(text) for text in texts]
