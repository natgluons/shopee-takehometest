"""Normalize OCR date and monetary strings into canonical values."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from receipt_ai.db.models import ReceiptItemInput
from receipt_ai.money import MoneyParseError, cents_to_str, parse_amount_to_cents
from receipt_ai.ocr.extract import RawItem, RawReceipt

MONTH_DAY_YEAR_FORMATS = (
    "%d %B %Y",
    "%d %b %Y",
    "%B %d, %Y",
    "%b %d, %Y",
    "%B %d %Y",
    "%b %d %Y",
)
MONTH_DAY_FORMATS = ("%d %B", "%d %b", "%B %d", "%b %d")
NUMERIC_DATE_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b")
ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


class NormalizationError(ValueError):
    """Raised when a required field cannot be normalized."""


@dataclass(frozen=True)
class NormalizedReceipt:
    merchant: str
    purchase_date: str | None
    currency: str
    subtotal_cents: int | None
    tax_cents: int | None
    total_cents: int | None
    items: list[ReceiptItemInput] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw_text: str = ""
    source_image: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "merchant": self.merchant,
            "purchase_date": self.purchase_date,
            "currency": self.currency,
            "subtotal_cents": self.subtotal_cents,
            "subtotal": cents_to_str(self.subtotal_cents)
            if self.subtotal_cents is not None
            else None,
            "tax_cents": self.tax_cents,
            "tax": cents_to_str(self.tax_cents) if self.tax_cents is not None else None,
            "total_cents": self.total_cents,
            "total": cents_to_str(self.total_cents) if self.total_cents is not None else None,
            "items": [
                {
                    "description": item.description,
                    "quantity": item.quantity,
                    "unit_price_cents": item.unit_price_cents,
                    "line_total_cents": item.line_total_cents,
                    "category": item.category,
                }
                for item in self.items
            ],
            "warnings": list(self.warnings),
            "raw_text": self.raw_text,
            "source_image": self.source_image,
        }


def _coerce_year(year: int) -> int:
    if year < 100:
        return 2000 + year
    return year


def _normalize_month_date(value: str, today: date, warnings: list[str]) -> date | None:
    cleaned = " ".join(value.replace(",", " ").split())
    for fmt in MONTH_DAY_YEAR_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    for fmt in MONTH_DAY_FORMATS:
        try:
            parsed = datetime.strptime(f"{cleaned} {today.year}", f"{fmt} %Y")
        except ValueError:
            continue
        candidate = parsed.date()
        if candidate > today:
            candidate = candidate.replace(year=today.year - 1)
            warnings.append(f"no year in date {value!r}, using previous year {candidate.year}")
        else:
            warnings.append(f"no year in date {value!r}, using {today.year}")
        return candidate
    return None


def parse_receipt_date(value: str, today: date | None = None) -> tuple[str, list[str]]:
    """Return an ISO date and any ambiguity warnings."""
    today = today or date.today()
    text = value.strip()
    if not text:
        raise NormalizationError("date is empty")
    warnings: list[str] = []
    iso_match = ISO_DATE_RE.search(text)
    if iso_match:
        year, month, day = (int(part) for part in iso_match.groups())
        return date(year, month, day).isoformat(), warnings

    month_date = _normalize_month_date(text, today, warnings)
    if month_date is not None:
        return month_date.isoformat(), warnings

    numeric = NUMERIC_DATE_RE.search(text)
    if numeric:
        first, second, year = (int(part) for part in numeric.groups())
        year = _coerce_year(year)
        if first > 12 and second <= 12:
            day, month = first, second
        elif second > 12 and first <= 12:
            month, day = first, second
        else:
            month, day = first, second
            warnings.append(f"ambiguous numeric date {text!r} interpreted as month/day")
        return date(year, month, day).isoformat(), warnings

    raise NormalizationError(f"could not parse date: {value!r}")


def parse_quantity(value: str | int | float) -> float:
    if isinstance(value, (int, float)):
        quantity = float(value)
    else:
        text = str(value).strip().replace(",", ".")
        try:
            quantity = float(text)
        except ValueError as exc:
            raise NormalizationError(f"invalid quantity: {value!r}") from exc
    if quantity <= 0:
        raise NormalizationError("quantity must be positive")
    return quantity


def normalize_item(raw: RawItem, warnings: list[str]) -> ReceiptItemInput | None:
    try:
        line_total = parse_amount_to_cents(raw.amount)
        quantity = parse_quantity(raw.quantity)
    except (MoneyParseError, NormalizationError) as exc:
        warnings.append(f"skipped item {raw.description!r}: {exc}")
        return None
    if line_total < 0:
        warnings.append(f"skipped item {raw.description!r}: negative amount")
        return None
    return ReceiptItemInput(
        description=raw.description,
        line_total_cents=line_total,
        quantity=quantity,
        unit_price_cents=round(line_total / quantity),
    )


def _parse_optional_money(value: str | None, label: str, warnings: list[str]) -> int | None:
    if value is None:
        return None
    try:
        cents = parse_amount_to_cents(value)
    except MoneyParseError as exc:
        warnings.append(f"could not parse {label}: {exc}")
        return None
    if cents < 0:
        warnings.append(f"{label} was negative and has been ignored")
        return None
    return cents


def normalize_receipt(
    raw: RawReceipt,
    default_currency: str = "USD",
    today: date | None = None,
    source_image: str | None = None,
) -> NormalizedReceipt:
    """Normalize raw extraction output without deciding whether it is valid."""
    today = today or date.today()
    warnings: list[str] = []
    merchant = " ".join(raw.merchant.split())
    purchase_date: str | None = None
    if raw.date:
        try:
            purchase_date, date_warnings = parse_receipt_date(raw.date, today=today)
            warnings.extend(date_warnings)
        except (NormalizationError, ValueError) as exc:
            warnings.append(str(exc))
    else:
        warnings.append("purchase date was not found")

    currency = (raw.currency or default_currency).upper()
    items = [
        item for raw_item in raw.items if (item := normalize_item(raw_item, warnings)) is not None
    ]
    subtotal = _parse_optional_money(raw.subtotal, "subtotal", warnings)
    tax = _parse_optional_money(raw.tax, "tax", warnings)
    total = _parse_optional_money(raw.total, "total", warnings)
    if total is None and items:
        items_total = sum(item.line_total_cents for item in items)
        inferred_tax = tax or 0
        total = items_total + inferred_tax
        warnings.append("total was inferred from line items and tax")
    if subtotal is None and items:
        subtotal = sum(item.line_total_cents for item in items)
    if subtotal is None and total is not None:
        assumed_tax = tax or 0
        if total >= assumed_tax:
            subtotal = total - assumed_tax
            tax = assumed_tax
            warnings.append("subtotal was inferred from total minus tax")
    if tax is None and total is not None and subtotal is not None:
        difference = total - subtotal
        if difference > 0:
            tax = difference
            warnings.append("tax was inferred from total minus subtotal")
        elif difference == 0:
            tax = 0
        else:
            warnings.append("total is lower than subtotal, tax could not be inferred")

    return NormalizedReceipt(
        merchant=merchant,
        purchase_date=purchase_date,
        currency=currency,
        subtotal_cents=subtotal,
        tax_cents=tax,
        total_cents=total,
        items=items,
        warnings=warnings,
        raw_text=raw.raw_text,
        source_image=source_image,
    )


def normalize_date_days_ago(days: int, today: date | None = None) -> str:
    today = today or date.today()
    return (today - timedelta(days=days)).isoformat()
