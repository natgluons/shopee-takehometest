"""SQLite schema for receipts and line items."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    merchant TEXT NOT NULL CHECK (length(trim(merchant)) > 0),
    purchase_date TEXT NOT NULL
        CHECK (purchase_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
    currency TEXT NOT NULL DEFAULT 'USD' CHECK (length(currency) = 3),
    subtotal_cents INTEGER NOT NULL DEFAULT 0 CHECK (subtotal_cents >= 0),
    tax_cents INTEGER NOT NULL DEFAULT 0 CHECK (tax_cents >= 0),
    total_cents INTEGER NOT NULL CHECK (total_cents >= 0),
    source_image TEXT,
    raw_text TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'saved')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (total_cents = subtotal_cents + tax_cents)
);

CREATE TABLE IF NOT EXISTS receipt_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_id INTEGER NOT NULL,
    description TEXT NOT NULL CHECK (length(trim(description)) > 0),
    quantity REAL NOT NULL DEFAULT 1 CHECK (quantity > 0),
    unit_price_cents INTEGER NOT NULL DEFAULT 0 CHECK (unit_price_cents >= 0),
    line_total_cents INTEGER NOT NULL DEFAULT 0 CHECK (line_total_cents >= 0),
    category TEXT,
    FOREIGN KEY (receipt_id) REFERENCES receipts(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_receipts_date ON receipts(purchase_date);
CREATE INDEX IF NOT EXISTS idx_receipts_merchant ON receipts(merchant COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_receipts_status ON receipts(status);
CREATE INDEX IF NOT EXISTS idx_items_receipt ON receipt_items(receipt_id);
CREATE INDEX IF NOT EXISTS idx_items_description ON receipt_items(description COLLATE NOCASE);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    """Open the receipt database with the application pragmas."""
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
    connection.executescript(SCHEMA_SQL)
    connection.execute(
        "INSERT OR REPLACE INTO schema_meta(key, value) VALUES('version', ?)",
        (str(SCHEMA_VERSION),),
    )
    connection.commit()


def initialize_path(path: str | Path) -> sqlite3.Connection:
    connection = connect(path)
    initialize(connection)
    return connection


@contextmanager
def open_database(path: str | Path) -> Iterator[sqlite3.Connection]:
    connection = initialize_path(path)
    try:
        yield connection
    finally:
        connection.close()
