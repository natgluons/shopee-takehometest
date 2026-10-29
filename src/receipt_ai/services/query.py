"""Natural-language query services backed by deterministic tools."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from receipt_ai.db.models import Receipt
from receipt_ai.db.repository import ReceiptRepository
from receipt_ai.money import cents_to_str

ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
NUMERIC_DATE_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b")
MONTH_NAMES = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}
MONTH_PATTERN = "|".join(MONTH_NAMES)
DAY_MONTH_RE = re.compile(
    rf"\b(?:on\s+|for\s+)?(\d{{1,2}})\s+(?:of\s+)?({MONTH_PATTERN})(?:\s+(\d{{4}}))?\b",
    re.IGNORECASE,
)
MONTH_DAY_RE = re.compile(
    rf"\b(?:on\s+|for\s+)?({MONTH_PATTERN})\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(\d{{4}}))?\b",
    re.IGNORECASE,
)


class DateResolutionError(ValueError):
    """Raised when a date phrase cannot be understood."""


@dataclass(frozen=True)
class ResolvedDateRange:
    start: date
    end: date
    label: str
    raw: str
    warnings: list[str] = field(default_factory=list)

    @property
    def is_single_day(self) -> bool:
        return self.start == self.end

    def to_dict(self) -> dict[str, Any]:
        return {
            "date_from": self.start.isoformat(),
            "date_to": self.end.isoformat(),
            "label": self.label,
            "raw": self.raw,
            "warnings": list(self.warnings),
        }


@dataclass
class ToolResult:
    tool: str
    arguments: dict[str, Any]
    found: bool
    answer: str
    data: dict[str, Any] = field(default_factory=dict)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "arguments": self.arguments,
            "found": self.found,
            "answer": self.answer,
            "data": self.data,
            "evidence": self.evidence,
            "warnings": list(self.warnings),
        }


def _safe_year(year: int | None, month: int, day: int, today: date, warnings: list[str]) -> int:
    if year is not None:
        return 2000 + year if year < 100 else year
    try:
        candidate = date(today.year, month, day)
    except ValueError:
        return today.year
    if candidate > today:
        warnings.append("date had no year and was in the future, using the previous year")
        return today.year - 1
    return today.year


def resolve_date_range(text: str, today: date | None = None) -> ResolvedDateRange:
    """Resolve relative and absolute date phrases into an inclusive range."""
    today = today or date.today()
    raw = text.strip()
    lowered = raw.lower()
    if not lowered:
        raise DateResolutionError("date phrase is empty")
    warnings: list[str] = []

    if "day before yesterday" in lowered:
        target = today - timedelta(days=2)
        return ResolvedDateRange(target, target, target.isoformat(), raw, warnings)
    if "yesterday" in lowered:
        target = today - timedelta(days=1)
        return ResolvedDateRange(target, target, target.isoformat(), raw, warnings)
    if re.search(r"\btoday\b", lowered):
        return ResolvedDateRange(today, today, today.isoformat(), raw, warnings)

    match = re.search(r"\b(?:last|past)\s+(\d{1,3})\s+days?\b", lowered)
    if match:
        days = int(match.group(1))
        if days < 1:
            raise DateResolutionError("day window must be at least one")
        start = today - timedelta(days=days - 1)
        return ResolvedDateRange(
            start, today, f"the last {days} days", raw, warnings
        )
    if "last week" in lowered or "past week" in lowered:
        start = today - timedelta(days=6)
        return ResolvedDateRange(start, today, "the last 7 days", raw, warnings)
    if "this month" in lowered:
        start = today.replace(day=1)
        return ResolvedDateRange(start, today, "this month", raw, warnings)
    if "last month" in lowered:
        first_this_month = today.replace(day=1)
        end = first_this_month - timedelta(days=1)
        start = end.replace(day=1)
        return ResolvedDateRange(start, end, "last month", raw, warnings)

    iso = ISO_DATE_RE.search(raw)
    if iso:
        target = date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        return ResolvedDateRange(target, target, target.isoformat(), raw, warnings)

    day_month = DAY_MONTH_RE.search(raw)
    if day_month:
        day = int(day_month.group(1))
        month = MONTH_NAMES[day_month.group(2).lower()]
        year = _safe_year(
            int(day_month.group(3)) if day_month.group(3) else None,
            month,
            day,
            today,
            warnings,
        )
        target = date(year, month, day)
        return ResolvedDateRange(target, target, target.isoformat(), raw, warnings)

    month_day = MONTH_DAY_RE.search(raw)
    if month_day:
        month = MONTH_NAMES[month_day.group(1).lower()]
        day = int(month_day.group(2))
        year = _safe_year(
            int(month_day.group(3)) if month_day.group(3) else None,
            month,
            day,
            today,
            warnings,
        )
        target = date(year, month, day)
        return ResolvedDateRange(target, target, target.isoformat(), raw, warnings)

    numeric = NUMERIC_DATE_RE.search(raw)
    if numeric:
        first, second = int(numeric.group(1)), int(numeric.group(2))
        year_part = numeric.group(3)
        if first > 12 and second <= 12:
            day, month = first, second
        elif second > 12 and first <= 12:
            month, day = first, second
        else:
            month, day = first, second
            warnings.append("ambiguous numeric date interpreted as month/day")
        year = _safe_year(
            int(year_part) if year_part else None, month, day, today, warnings
        )
        target = date(year, month, day)
        return ResolvedDateRange(target, target, target.isoformat(), raw, warnings)

    raise DateResolutionError(f"could not understand the date phrase: {text!r}")


def _describe_items(receipt: Receipt) -> str:
    parts = []
    for item in receipt.items:
        quantity = int(item.quantity) if item.quantity.is_integer() else item.quantity
        parts.append(f"{item.description} x{quantity}")
    return ", ".join(parts)


class QueryService:
    """Deterministic query tools used by the UI and the optional LLM."""

    def __init__(self, repository: ReceiptRepository) -> None:
        self.repository = repository

    def get_purchases_by_date(
        self, date_phrase: str, as_of: date | None = None
    ) -> ToolResult:
        resolved = resolve_date_range(date_phrase, today=as_of)
        receipts = self.repository.list_receipts(
            date_from=resolved.start.isoformat(),
            date_to=resolved.end.isoformat(),
            status="saved",
            limit=10_000,
        )
        evidence = [
            {
                "type": "receipt",
                "receipt_id": receipt.id,
                "merchant": receipt.merchant,
                "purchase_date": receipt.purchase_date,
                "total": cents_to_str(receipt.total_cents),
                "currency": receipt.currency,
                "items": [item.to_dict() for item in receipt.items],
            }
            for receipt in receipts
        ]
        if not receipts:
            answer = f"I could not find any saved food purchases for {resolved.label}."
        else:
            by_currency: dict[str, int] = {}
            for receipt in receipts:
                by_currency[receipt.currency] = (
                    by_currency.get(receipt.currency, 0) + receipt.total_cents
                )
            totals = ", ".join(
                f"{cents_to_str(total)} {currency}"
                for currency, total in sorted(by_currency.items())
            )
            detail = "; ".join(
                f"{receipt.merchant} on {receipt.purchase_date}: "
                f"{_describe_items(receipt) or 'no items'} ({cents_to_str(receipt.total_cents)} "
                f"{receipt.currency})"
                for receipt in receipts
            )
            answer = (
                f"You bought food {resolved.label}. Receipts: {detail}. Total: {totals}."
            )
        return ToolResult(
            tool="get_purchases_by_date",
            arguments={**resolved.to_dict(), "raw_date": date_phrase},
            found=bool(receipts),
            answer=answer,
            data={
                "receipts": [receipt.to_dict() for receipt in receipts],
                "receipt_count": len(receipts),
                "date_from": resolved.start.isoformat(),
                "date_to": resolved.end.isoformat(),
            },
            evidence=evidence,
            warnings=resolved.warnings,
        )

    def get_food_expenses_by_date(
        self, date_phrase: str, as_of: date | None = None
    ) -> ToolResult:
        resolved = resolve_date_range(date_phrase, today=as_of)
        totals = self.repository.total_expenses(
            resolved.start.isoformat(), resolved.end.isoformat(), status="saved"
        )
        receipts = self.repository.list_receipts(
            date_from=resolved.start.isoformat(),
            date_to=resolved.end.isoformat(),
            status="saved",
            limit=10_000,
        )
        evidence = [
            {
                "type": "receipt",
                "receipt_id": receipt.id,
                "merchant": receipt.merchant,
                "purchase_date": receipt.purchase_date,
                "total": cents_to_str(receipt.total_cents),
                "currency": receipt.currency,
            }
            for receipt in receipts
        ]
        currencies = totals["currencies"]
        if not currencies:
            answer = f"I found no saved food expenses for {resolved.label}."
        else:
            rendered = ", ".join(
                f"{item['total']} {item['currency']} across {item['receipt_count']} receipts"
                for item in currencies
            )
            answer = f"Your total food expenses for {resolved.label} were {rendered}."
        return ToolResult(
            tool="get_food_expenses_by_date",
            arguments={**resolved.to_dict(), "raw_date": date_phrase},
            found=bool(currencies),
            answer=answer,
            data={
                "date_from": resolved.start.isoformat(),
                "date_to": resolved.end.isoformat(),
                "currencies": currencies,
                "receipt_count": totals["receipt_count"],
            },
            evidence=evidence,
            warnings=resolved.warnings,
        )

    def find_merchant_by_item(
        self,
        item: str,
        days: int = 7,
        date_phrase: str | None = None,
        as_of: date | None = None,
    ) -> ToolResult:
        item = item.strip()
        if not item:
            raise ValueError("item must not be empty")
        today = as_of or date.today()
        if date_phrase:
            resolved = resolve_date_range(date_phrase, today=today)
        else:
            if days < 1:
                raise ValueError("days must be at least 1")
            start = today - timedelta(days=days - 1)
            resolved = ResolvedDateRange(
                start=start,
                end=today,
                label=f"the last {days} days",
                raw=f"last {days} days",
            )
        receipts = self.repository.receipts_for_item(
            item,
            resolved.start.isoformat(),
            resolved.end.isoformat(),
            status="saved",
        )
        evidence: list[dict[str, Any]] = []
        merchant_lines: list[str] = []
        seen: set[tuple[str, str]] = set()
        for receipt in receipts:
            matching = [
                item_row
                for item_row in receipt.items
                if item.lower() in item_row.description.lower()
            ]
            for item_row in matching:
                evidence.append(
                    {
                        "type": "item",
                        "receipt_id": receipt.id,
                        "merchant": receipt.merchant,
                        "purchase_date": receipt.purchase_date,
                        "description": item_row.description,
                        "line_total": cents_to_str(item_row.line_total_cents),
                        "currency": receipt.currency,
                    }
                )
            key = (receipt.merchant, receipt.purchase_date)
            if key not in seen:
                seen.add(key)
                matching_total = sum(item_row.line_total_cents for item_row in matching)
                merchant_lines.append(
                    f"{receipt.merchant} on {receipt.purchase_date} "
                    f"({cents_to_str(matching_total)} {receipt.currency})"
                )
        if not receipts:
            answer = (
                f"I could not find any saved purchases containing {item!r} in "
                f"{resolved.label}."
            )
        else:
            answer = f"You bought {item} from " + "; ".join(merchant_lines) + "."
        return ToolResult(
            tool="find_merchant_by_item",
            arguments={
                "item": item,
                "days": days,
                "date_from": resolved.start.isoformat(),
                "date_to": resolved.end.isoformat(),
                "raw_date": date_phrase,
            },
            found=bool(receipts),
            answer=answer,
            data={
                "item": item,
                "date_from": resolved.start.isoformat(),
                "date_to": resolved.end.isoformat(),
                "merchants": sorted({receipt.merchant for receipt in receipts}),
                "receipt_count": len(receipts),
            },
            evidence=evidence,
            warnings=resolved.warnings,
        )
