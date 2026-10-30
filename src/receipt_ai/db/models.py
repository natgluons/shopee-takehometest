"""Receipt domain models."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date as date_type
from typing import Any

from receipt_ai.money import cents_to_str

ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VALID_STATUSES = frozenset({"pending", "saved"})


class ReceiptValidationError(ValueError):
    """Raised when a receipt payload violates a domain rule."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("; ".join(problems))


class MonetaryIntegrityError(ReceiptValidationError):
    """Raised when subtotal, tax, and total do not add up."""


@dataclass(frozen=True)
class ReceiptItemInput:
    description: str
    line_total_cents: int
    quantity: float = 1.0
    unit_price_cents: int | None = None
    category: str | None = None

    def normalized(self) -> ReceiptItemInput:
        description = " ".join(self.description.split())
        if not description:
            raise ReceiptValidationError(["item description must not be empty"])
        if self.line_total_cents < 0:
            raise ReceiptValidationError(["item line total must not be negative"])
        if self.quantity <= 0:
            raise ReceiptValidationError(["item quantity must be positive"])
        unit_price = self.unit_price_cents
        if unit_price is None:
            unit_price = round(self.line_total_cents / self.quantity)
        if unit_price < 0:
            raise ReceiptValidationError(["item unit price must not be negative"])
        return ReceiptItemInput(
            description=description,
            line_total_cents=int(self.line_total_cents),
            quantity=float(self.quantity),
            unit_price_cents=int(unit_price),
            category=self.category.strip() if self.category else None,
        )


@dataclass(frozen=True)
class ReceiptItem:
    id: int
    receipt_id: int
    description: str
    quantity: float
    unit_price_cents: int
    line_total_cents: int
    category: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "receipt_id": self.receipt_id,
            "description": self.description,
            "quantity": self.quantity,
            "unit_price_cents": self.unit_price_cents,
            "unit_price": cents_to_str(self.unit_price_cents),
            "line_total_cents": self.line_total_cents,
            "line_total": cents_to_str(self.line_total_cents),
            "category": self.category,
        }


@dataclass(frozen=True)
class ReceiptDraft:
    merchant: str
    purchase_date: str
    currency: str = "USD"
    subtotal_cents: int | None = None
    tax_cents: int = 0
    total_cents: int | None = None
    items: list[ReceiptItemInput] = field(default_factory=list)
    source_image: str | None = None
    raw_text: str = ""
    status: str = "pending"

    def normalized(self) -> ReceiptDraft:
        problems: list[str] = []
        merchant = " ".join(self.merchant.split())
        if not merchant:
            problems.append("merchant must not be empty")
        purchase_date = self.purchase_date.strip()
        if not ISO_DATE_RE.match(purchase_date):
            problems.append("purchase_date must use YYYY-MM-DD")
        else:
            try:
                date_type.fromisoformat(purchase_date)
            except ValueError:
                problems.append("purchase_date is not a valid date")
        currency = self.currency.strip().upper()
        if len(currency) != 3 or not currency.isalpha():
            problems.append("currency must be a three letter code")
        if self.tax_cents < 0:
            problems.append("tax must not be negative")
        if self.subtotal_cents is not None and self.subtotal_cents < 0:
            problems.append("subtotal must not be negative")
        if self.total_cents is not None and self.total_cents < 0:
            problems.append("total must not be negative")
        if self.status not in VALID_STATUSES:
            problems.append(f"status must be one of {sorted(VALID_STATUSES)}")
        items = [item.normalized() for item in self.items]
        if problems:
            raise ReceiptValidationError(problems)
        return ReceiptDraft(
            merchant=merchant,
            purchase_date=purchase_date,
            currency=currency,
            subtotal_cents=self.subtotal_cents,
            tax_cents=int(self.tax_cents),
            total_cents=self.total_cents,
            items=items,
            source_image=self.source_image,
            raw_text=self.raw_text,
            status=self.status,
        )


@dataclass(frozen=True)
class Receipt:
    id: int
    merchant: str
    purchase_date: str
    currency: str
    subtotal_cents: int
    tax_cents: int
    total_cents: int
    source_image: str | None
    raw_text: str
    status: str
    created_at: str
    updated_at: str
    items: list[ReceiptItem] = field(default_factory=list)

    @property
    def item_count(self) -> int:
        return len(self.items)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "merchant": self.merchant,
            "purchase_date": self.purchase_date,
            "currency": self.currency,
            "subtotal_cents": self.subtotal_cents,
            "subtotal": cents_to_str(self.subtotal_cents),
            "tax_cents": self.tax_cents,
            "tax": cents_to_str(self.tax_cents),
            "total_cents": self.total_cents,
            "total": cents_to_str(self.total_cents),
            "source_image": self.source_image,
            "raw_text": self.raw_text,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "items": [item.to_dict() for item in self.items],
        }
