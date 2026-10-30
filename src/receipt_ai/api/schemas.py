"""Pydantic request and response schemas for the API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from receipt_ai.db.models import ReceiptDraft, ReceiptItemInput


class ItemPayload(BaseModel):
    description: str = Field(min_length=1, max_length=300)
    line_total_cents: int = Field(ge=0)
    quantity: float = Field(default=1.0, gt=0)
    unit_price_cents: int | None = Field(default=None, ge=0)
    category: str | None = None

    def to_input(self) -> ReceiptItemInput:
        return ReceiptItemInput(
            description=self.description,
            line_total_cents=self.line_total_cents,
            quantity=self.quantity,
            unit_price_cents=self.unit_price_cents,
            category=self.category,
        )


class ReceiptPayload(BaseModel):
    merchant: str
    purchase_date: str
    currency: str = "USD"
    subtotal_cents: int | None = None
    tax_cents: int = 0
    total_cents: int | None = None
    items: list[ItemPayload] = Field(default_factory=list)
    source_image: str | None = None
    raw_text: str = ""
    status: Literal["pending", "saved"] = "saved"

    def to_draft(self) -> ReceiptDraft:
        return ReceiptDraft(
            merchant=self.merchant,
            purchase_date=self.purchase_date,
            currency=self.currency,
            subtotal_cents=self.subtotal_cents,
            tax_cents=self.tax_cents,
            total_cents=self.total_cents,
            items=[item.to_input() for item in self.items],
            source_image=self.source_image,
            raw_text=self.raw_text,
            status=self.status,
        )
