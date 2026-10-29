"""Validation for normalized receipt extractions."""

from __future__ import annotations

from datetime import date
from typing import Any

from receipt_ai.db.models import ReceiptDraft, ReceiptValidationError
from receipt_ai.ocr.normalize import NormalizedReceipt

TOLERANCE_CENTS = 2
MAX_REASONABLE_TOTAL_CENTS = 10_000_00
MAX_AGE_DAYS = 3650


class ExtractionValidationError(ReceiptValidationError):
    """Raised when an extraction cannot become a trustworthy receipt."""

    def __init__(self, problems: list[str], warnings: list[str] | None = None) -> None:
        self.warnings = warnings or []
        super().__init__(problems)

    def to_dict(self) -> dict[str, Any]:
        return {"problems": self.problems, "warnings": self.warnings}


def validate_extraction(
    normalized: NormalizedReceipt,
    today: date | None = None,
    status: str = "pending",
) -> tuple[ReceiptDraft, list[str]]:
    """Validate a normalized extraction and return a draft plus warnings."""
    today = today or date.today()
    problems: list[str] = []
    warnings = list(normalized.warnings)

    merchant = " ".join(normalized.merchant.split())
    if not merchant:
        problems.append("merchant was not found")
    elif len(merchant) > 200:
        problems.append("merchant name is unreasonably long")

    purchase_date: str | None = normalized.purchase_date
    if not purchase_date:
        problems.append("purchase date was not found or could not be parsed")
    else:
        try:
            parsed = date.fromisoformat(purchase_date)
        except ValueError:
            problems.append("purchase date is not a valid ISO date")
        else:
            if parsed > today:
                problems.append("purchase date is in the future")
            elif (today - parsed).days > MAX_AGE_DAYS:
                warnings.append("receipt is more than ten years old")

    currency = normalized.currency.strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        problems.append("currency is not a three letter code")

    items = normalized.items
    subtotal = normalized.subtotal_cents
    tax = normalized.tax_cents
    total = normalized.total_cents
    items_total = sum(item.line_total_cents for item in items)

    if not items:
        warnings.append("no line items were extracted")
    if subtotal is None and items:
        subtotal = items_total
    if subtotal is None:
        problems.append("subtotal was not found")
    if tax is None:
        tax = 0
    if total is None and subtotal is not None:
        total = subtotal + tax
        warnings.append("total was inferred during validation")

    if total is None:
        problems.append("total was not found")
    elif total <= 0:
        problems.append("total must be greater than zero")
    elif total > MAX_REASONABLE_TOTAL_CENTS:
        warnings.append("total is unusually large")

    if subtotal is not None and items and abs(subtotal - items_total) > TOLERANCE_CENTS:
        problems.append(
            f"subtotal {subtotal / 100:.2f} does not match item total {items_total / 100:.2f}"
        )
    if (
        subtotal is not None
        and total is not None
        and tax is not None
        and abs(total - (subtotal + tax)) > TOLERANCE_CENTS
    ):
        problems.append(
            f"total {total / 100:.2f} does not equal subtotal "
            f"{subtotal / 100:.2f} plus tax {tax / 100:.2f}"
        )

    if problems:
        raise ExtractionValidationError(problems, warnings)

    draft = ReceiptDraft(
        merchant=merchant,
        purchase_date=purchase_date or "",
        currency=currency,
        subtotal_cents=subtotal,
        tax_cents=tax or 0,
        total_cents=total,
        items=items,
        source_image=normalized.source_image,
        raw_text=normalized.raw_text,
        status=status,
    )
    return draft, warnings
