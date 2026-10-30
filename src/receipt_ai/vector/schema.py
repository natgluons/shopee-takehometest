"""SQLite schema for the self-hosted vector database.

Vectors are stored as JSON text. SQLite is used as an embedded, durable store. Brute-force search is
performed in Python, so the schema optimizes metadata filtering and key lookup rather than vector
distance indexes.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Iterator

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS collections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    dimension INTEGER NOT NULL CHECK (dimension > 0),
    metric TEXT NOT NULL DEFAULT 'cosine'
        CHECK (metric IN ('cosine', 'dot', 'euclidean')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS vectors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    collection_id INTEGER NOT NULL,
    external_id TEXT NOT NULL,
    content TEXT NOT NULL DEFAULT '',
    vector TEXT NOT NULL,
    metadata TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE,
    UNIQUE (collection_id, external_id)
);

CREATE INDEX IF NOT EXISTS idx_vectors_collection ON vectors(collection_id);
CREATE INDEX IF NOT EXISTS idx_vectors_external ON vectors(collection_id, external_id);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    """Open a SQLite connection with the pragmas used by the vector store."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def initialize(connection: sqlite3.Connection) -> None:
    """Create the vector schema if it does not exist."""
    connection.executescript(SCHEMA_SQL)
    connection.execute(
        "INSERT OR REPLACE INTO schema_meta(key, value) VALUES('version', ?)",
        (str(SCHEMA_VERSION),),
    )
    connection.commit()


def initialize_path(path: str | Path) -> sqlite3.Connection:
    """Open and initialize a vector database file, returning the connection."""
    connection = connect(path)
    initialize(connection)
    return connection


@contextmanager
def open_database(path: str | Path) -> Iterator[sqlite3.Connection]:
    """Context manager that initializes and closes a vector database."""
    connection = initialize_path(path)
    try:
        yield connection
    finally:
        connection.close()
