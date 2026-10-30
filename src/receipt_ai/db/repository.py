"""Transactional persistence and querying for receipts."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import date as date_type
from pathlib import Path
from typing import Any

from receipt_ai.db.models import (
    ISO_DATE_RE,
    MonetaryIntegrityError,
    Receipt,
    ReceiptDraft,
    ReceiptItem,
    ReceiptItemInput,
    ReceiptValidationError,
)
from receipt_ai.db.schema import initialize_path
from receipt_ai.money import cents_to_str


class ReceiptNotFoundError(KeyError):
    """Raised when a receipt identifier does not exist."""


def _validate_date(value: str, name: str = "date") -> str:
    value = value.strip()
    if not ISO_DATE_RE.match(value):
        raise ValueError(f"{name} must use YYYY-MM-DD")
    try:
        date_type.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} is not a valid date") from exc
    return value


class ReceiptRepository:
    """SQLite repository for receipts and line items."""

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

    def __enter__(self) -> ReceiptRepository:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    @staticmethod
    def _resolve_totals(
        draft: ReceiptDraft,
    ) -> tuple[list[ReceiptItemInput], int, int, int]:
        normalized = draft.normalized()
        items = normalized.items
        items_subtotal = sum(item.line_total_cents for item in items)
        subtotal = (
            normalized.subtotal_cents if normalized.subtotal_cents is not None else items_subtotal
        )
        tax = normalized.tax_cents
        if items and subtotal != items_subtotal:
            raise MonetaryIntegrityError(
                [f"subtotal {subtotal} does not equal the sum of item totals {items_subtotal}"]
            )
        if normalized.total_cents is None:
            total = subtotal + tax
        else:
            total = normalized.total_cents
            if total != subtotal + tax:
                raise MonetaryIntegrityError(
                    [f"total {total} does not equal subtotal {subtotal} plus tax {tax}"]
                )
        if total < 0:
            raise MonetaryIntegrityError(["total must not be negative"])
        return items, subtotal, tax, total

    def create_receipt(self, draft: ReceiptDraft) -> Receipt:
        items, subtotal, tax, total = self._resolve_totals(draft)
        normalized = draft.normalized()
        with self.connection:
            cursor = self.connection.execute(
                """
                INSERT INTO receipts(
                    merchant, purchase_date, currency, subtotal_cents, tax_cents,
                    total_cents, source_image, raw_text, status
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    normalized.merchant,
                    normalized.purchase_date,
                    normalized.currency,
                    subtotal,
                    tax,
                    total,
                    normalized.source_image,
                    normalized.raw_text,
                    normalized.status,
                ),
            )
            receipt_id = int(cursor.lastrowid)
            self._insert_items(receipt_id, items)
        receipt = self.get_receipt(receipt_id)
        if receipt is None:
            raise RuntimeError("receipt insert failed")
        return receipt

    def update_receipt(self, receipt_id: int, draft: ReceiptDraft) -> Receipt:
        items, subtotal, tax, total = self._resolve_totals(draft)
        normalized = draft.normalized()
        with self.connection:
            cursor = self.connection.execute(
                """
                UPDATE receipts SET
                    merchant = ?, purchase_date = ?, currency = ?, subtotal_cents = ?,
                    tax_cents = ?, total_cents = ?, source_image = ?, raw_text = ?,
                    status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    normalized.merchant,
                    normalized.purchase_date,
                    normalized.currency,
                    subtotal,
                    tax,
                    total,
                    normalized.source_image,
                    normalized.raw_text,
                    normalized.status,
                    receipt_id,
                ),
            )
            if cursor.rowcount == 0:
                raise ReceiptNotFoundError(receipt_id)
            self.connection.execute("DELETE FROM receipt_items WHERE receipt_id = ?", (receipt_id,))
            self._insert_items(receipt_id, items)
        receipt = self.get_receipt(receipt_id)
        if receipt is None:
            raise RuntimeError("receipt update failed")
        return receipt

    def _insert_items(self, receipt_id: int, items: list[ReceiptItemInput]) -> None:
        if not items:
            return
        self.connection.executemany(
            """
            INSERT INTO receipt_items(
                receipt_id, description, quantity, unit_price_cents, line_total_cents, category
            ) VALUES(?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    receipt_id,
                    item.description,
                    item.quantity,
                    item.unit_price_cents or 0,
                    item.line_total_cents,
                    item.category,
                )
                for item in items
            ],
        )

    def get_receipt(self, receipt_id: int, include_items: bool = True) -> Receipt | None:
        row = self.connection.execute(
            "SELECT * FROM receipts WHERE id = ?", (receipt_id,)
        ).fetchone()
        if row is None:
            return None
        items = self._items_for_receipt(receipt_id) if include_items else []
        return self._row_to_receipt(row, items)

    def get_receipt_by_source(self, source_image: str) -> Receipt | None:
        row = self.connection.execute(
            "SELECT * FROM receipts WHERE source_image = ? ORDER BY id DESC LIMIT 1",
            (source_image,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_receipt(row, self._items_for_receipt(int(row["id"])))

    def delete_receipt(self, receipt_id: int) -> bool:
        with self.connection:
            cursor = self.connection.execute("DELETE FROM receipts WHERE id = ?", (receipt_id,))
        return cursor.rowcount > 0

    def list_receipts(
        self,
        date_from: str | None = None,
        date_to: str | None = None,
        merchant: str | None = None,
        item: str | None = None,
        status: str | None = "saved",
        limit: int = 100,
        offset: int = 0,
    ) -> list[Receipt]:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if offset < 0:
            raise ValueError("offset must not be negative")
        clauses: list[str] = []
        parameters: list[Any] = []
        if date_from:
            clauses.append("purchase_date >= ?")
            parameters.append(_validate_date(date_from, "date_from"))
        if date_to:
            clauses.append("purchase_date <= ?")
            parameters.append(_validate_date(date_to, "date_to"))
        if merchant:
            clauses.append("merchant LIKE ? COLLATE NOCASE")
            parameters.append(f"%{merchant.strip()}%")
        if item:
            clauses.append(
                "EXISTS (SELECT 1 FROM receipt_items i WHERE i.receipt_id = receipts.id "
                "AND i.description LIKE ? COLLATE NOCASE)"
            )
            parameters.append(f"%{item.strip()}%")
        if status:
            clauses.append("status = ?")
            parameters.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        parameters.extend([limit, offset])
        rows = self.connection.execute(
            f"SELECT * FROM receipts {where} ORDER BY purchase_date DESC, id DESC LIMIT ? OFFSET ?",
            parameters,
        ).fetchall()
        return [self._row_to_receipt(row, self._items_for_receipt(int(row["id"]))) for row in rows]

    def purchases_on(self, day: str, status: str | None = "saved") -> list[Receipt]:
        day = _validate_date(day, "day")
        return self.list_receipts(date_from=day, date_to=day, status=status, limit=10_000)

    def total_expenses(
        self,
        date_from: str,
        date_to: str,
        status: str | None = "saved",
    ) -> dict[str, Any]:
        date_from = _validate_date(date_from, "date_from")
        date_to = _validate_date(date_to, "date_to")
        if date_from > date_to:
            raise ValueError("date_from must not be after date_to")
        status_clause = "AND status = ?" if status else ""
        parameters: list[Any] = [date_from, date_to]
        if status:
            parameters.append(status)
        rows = self.connection.execute(
            f"""
            SELECT currency, COUNT(*) AS receipt_count, SUM(total_cents) AS total_cents
            FROM receipts
            WHERE purchase_date BETWEEN ? AND ? {status_clause}
            GROUP BY currency
            ORDER BY currency
            """,
            parameters,
        ).fetchall()
        currencies = [
            {
                "currency": row["currency"],
                "receipt_count": int(row["receipt_count"]),
                "total_cents": int(row["total_cents"] or 0),
                "total": cents_to_str(int(row["total_cents"] or 0)),
            }
            for row in rows
        ]
        return {
            "date_from": date_from,
            "date_to": date_to,
            "currencies": currencies,
            "receipt_count": sum(item["receipt_count"] for item in currencies),
            "found": bool(currencies),
        }

    def receipts_for_item(
        self,
        item: str,
        date_from: str,
        date_to: str,
        status: str | None = "saved",
    ) -> list[Receipt]:
        item = item.strip()
        if not item:
            raise ValueError("item must not be empty")
        date_from = _validate_date(date_from, "date_from")
        date_to = _validate_date(date_to, "date_to")
        clauses = [
            "r.purchase_date BETWEEN ? AND ?",
            "i.description LIKE ? COLLATE NOCASE",
        ]
        parameters: list[Any] = [date_from, date_to, f"%{item}%"]
        if status:
            clauses.append("r.status = ?")
            parameters.append(status)
        rows = self.connection.execute(
            f"""
            SELECT DISTINCT r.* FROM receipts r
            JOIN receipt_items i ON i.receipt_id = r.id
            WHERE {" AND ".join(clauses)}
            ORDER BY r.purchase_date DESC, r.id DESC
            """,
            parameters,
        ).fetchall()
        return [self._row_to_receipt(row, self._items_for_receipt(int(row["id"]))) for row in rows]

    def insights(self, status: str | None = "saved") -> dict[str, Any]:
        status_clause = "WHERE status = ?" if status else ""
        parameters: tuple[Any, ...] = (status,) if status else ()
        totals = self.connection.execute(
            f"""
            SELECT currency, COUNT(*) AS receipt_count, SUM(total_cents) AS total_cents
            FROM receipts {status_clause} GROUP BY currency ORDER BY currency
            """,
            parameters,
        ).fetchall()
        by_day = self.connection.execute(
            f"""
            SELECT purchase_date, SUM(total_cents) AS total_cents, COUNT(*) AS receipt_count
            FROM receipts {status_clause}
            GROUP BY purchase_date ORDER BY purchase_date DESC LIMIT 30
            """,
            parameters,
        ).fetchall()
        by_merchant = self.connection.execute(
            f"""
            SELECT merchant, SUM(total_cents) AS total_cents, COUNT(*) AS receipt_count
            FROM receipts {status_clause}
            GROUP BY merchant ORDER BY total_cents DESC LIMIT 10
            """,
            parameters,
        ).fetchall()
        top_items = self.connection.execute(
            f"""
            SELECT i.description, COUNT(*) AS occurrences, SUM(i.line_total_cents) AS total_cents
            FROM receipt_items i JOIN receipts r ON r.id = i.receipt_id
            {status_clause.replace("status", "r.status")}
            GROUP BY LOWER(i.description)
            ORDER BY occurrences DESC, total_cents DESC LIMIT 10
            """,
            parameters,
        ).fetchall()
        by_category = self.connection.execute(
            f"""
            SELECT COALESCE(i.category, 'uncategorized') AS category,
                   SUM(i.line_total_cents) AS total_cents, COUNT(*) AS item_count
            FROM receipt_items i JOIN receipts r ON r.id = i.receipt_id
            {status_clause.replace("status", "r.status")}
            GROUP BY COALESCE(i.category, 'uncategorized')
            ORDER BY total_cents DESC
            """,
            parameters,
        ).fetchall()
        return {
            "totals": [
                {
                    "currency": row["currency"],
                    "receipt_count": int(row["receipt_count"]),
                    "total_cents": int(row["total_cents"] or 0),
                    "total": cents_to_str(int(row["total_cents"] or 0)),
                }
                for row in totals
            ],
            "by_day": [
                {
                    "date": row["purchase_date"],
                    "total_cents": int(row["total_cents"] or 0),
                    "total": cents_to_str(int(row["total_cents"] or 0)),
                    "receipt_count": int(row["receipt_count"]),
                }
                for row in by_day
            ],
            "by_merchant": [
                {
                    "merchant": row["merchant"],
                    "total_cents": int(row["total_cents"] or 0),
                    "total": cents_to_str(int(row["total_cents"] or 0)),
                    "receipt_count": int(row["receipt_count"]),
                }
                for row in by_merchant
            ],
            "top_items": [
                {
                    "description": row["description"],
                    "occurrences": int(row["occurrences"]),
                    "total_cents": int(row["total_cents"] or 0),
                }
                for row in top_items
            ],
            "by_category": [
                {
                    "category": row["category"],
                    "total_cents": int(row["total_cents"] or 0),
                    "item_count": int(row["item_count"]),
                }
                for row in by_category
            ],
            "receipt_count": sum(int(row["receipt_count"]) for row in totals),
        }

    def count_receipts(self, status: str | None = None) -> int:
        if status:
            row = self.connection.execute(
                "SELECT COUNT(*) AS count FROM receipts WHERE status = ?", (status,)
            ).fetchone()
        else:
            row = self.connection.execute("SELECT COUNT(*) AS count FROM receipts").fetchone()
        return int(row["count"]) if row else 0

    def _items_for_receipt(self, receipt_id: int) -> list[ReceiptItem]:
        rows = self.connection.execute(
            "SELECT * FROM receipt_items WHERE receipt_id = ? ORDER BY id", (receipt_id,)
        ).fetchall()
        return [
            ReceiptItem(
                id=int(row["id"]),
                receipt_id=int(row["receipt_id"]),
                description=str(row["description"]),
                quantity=float(row["quantity"]),
                unit_price_cents=int(row["unit_price_cents"]),
                line_total_cents=int(row["line_total_cents"]),
                category=row["category"],
            )
            for row in rows
        ]

    @staticmethod
    def _row_to_receipt(row: sqlite3.Row, items: list[ReceiptItem]) -> Receipt:
        return Receipt(
            id=int(row["id"]),
            merchant=str(row["merchant"]),
            purchase_date=str(row["purchase_date"]),
            currency=str(row["currency"]),
            subtotal_cents=int(row["subtotal_cents"]),
            tax_cents=int(row["tax_cents"]),
            total_cents=int(row["total_cents"]),
            source_image=row["source_image"],
            raw_text=str(row["raw_text"]),
            status=str(row["status"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            items=items,
        )

    def iter_receipts(self, status: str | None = "saved") -> Iterator[Receipt]:
        yield from self.list_receipts(status=status, limit=1_000_000)


__all__ = [
    "ReceiptNotFoundError",
    "ReceiptRepository",
    "ReceiptValidationError",
]
