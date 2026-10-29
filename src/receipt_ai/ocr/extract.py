"""Extract receipt fields from raw OCR text.

The extractor is deliberately conservative. It returns raw strings and a best-effort set of items.
Normalization and validation happen in later modules so each concern can be tested independently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

AMOUNT = r"[-+]?(?:[$€£¥]\s*)?\d[\d.,]*(?:\s*(?:USD|EUR|GBP|JPY|SGD|IDR|AUD|CAD))?"
AMOUNT_RE = re.compile(AMOUNT, re.IGNORECASE)
ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
NUMERIC_DATE_RE = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b")
MONTH_DATE_RE = re.compile(
    r"\b(?:\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4}|"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{2,4})\b",
    re.IGNORECASE,
)
ITEM_PATTERNS = (
    re.compile(
        rf"^(?P<qty>\d+(?:[.,]\d+)?)\s*[xX]\s*(?P<name>.+?)\s+(?P<amount>{AMOUNT})\s*$"
    ),
    re.compile(rf"^(?P<name>[^\d].+?)\s+(?P<amount>{AMOUNT})\s*$"),
)
SKIP_KEYWORDS = (
    "subtotal",
    "sub total",
    "total",
    "tax",
    "vat",
    "gst",
    "tip",
    "cash",
    "change",
    "balance",
    "card",
    "payment",
    "paid",
    "discount",
    "thank",
    "receipt",
    "invoice",
    "date",
    "time",
    "phone",
    "address",
    "server",
    "table",
    "order",
    "www.",
    "http",
)
CURRENCY_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY"}
CURRENCY_CODES = ("USD", "EUR", "GBP", "JPY", "SGD", "IDR", "AUD", "CAD")


@dataclass(frozen=True)
class RawItem:
    description: str
    amount: str
    quantity: str = "1"


@dataclass(frozen=True)
class RawReceipt:
    merchant: str
    date: str | None
    total: str | None
    subtotal: str | None = None
    tax: str | None = None
    currency: str | None = None
    items: list[RawItem] = field(default_factory=list)
    raw_text: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "merchant": self.merchant,
            "date": self.date,
            "total": self.total,
            "subtotal": self.subtotal,
            "tax": self.tax,
            "currency": self.currency,
            "items": [
                {
                    "description": item.description,
                    "amount": item.amount,
                    "quantity": item.quantity,
                }
                for item in self.items
            ],
            "raw_text": self.raw_text,
        }


def _clean_lines(text: str) -> list[str]:
    lines = []
    for raw in text.splitlines():
        line = " ".join(raw.split())
        if line:
            lines.append(line)
    return lines


def _looks_like_header(line: str) -> bool:
    lowered = line.lower()
    if any(keyword in lowered for keyword in ("receipt", "invoice", "order", "tax invoice")):
        return True
    if len(line) < 3:
        return True
    if re.fullmatch(r"[\d\W]+", line):
        return True
    return False


def extract_merchant(lines: list[str]) -> str:
    for line in lines[:8]:
        candidate = re.sub(r"^(?:merchant|store|shop|seller)\s*[:\-]\s*", "", line, flags=re.I)
        if candidate and not _looks_like_header(candidate):
            return candidate
    return lines[0] if lines else ""


def extract_date(text: str) -> str | None:
    for pattern in (ISO_DATE_RE, MONTH_DATE_RE, NUMERIC_DATE_RE):
        match = pattern.search(text)
        if match:
            return match.group(0)
    return None


def _amount_from_line(line: str) -> str | None:
    matches = AMOUNT_RE.findall(line)
    if not matches:
        return None
    return matches[-1]


def _find_labelled_amount(lines: list[str], labels: tuple[str, ...]) -> str | None:
    for line in lines:
        lowered = line.lower()
        if any(label in lowered for label in labels):
            amount = _amount_from_line(line)
            if amount:
                return amount
    return None


def extract_total(lines: list[str]) -> str | None:
    for line in lines:
        lowered = line.lower()
        if "subtotal" in lowered or "sub total" in lowered:
            continue
        if "grand total" in lowered or re.search(r"\btotal\b", lowered):
            amount = _amount_from_line(line)
            if amount:
                return amount
    return None


def extract_subtotal(lines: list[str]) -> str | None:
    return _find_labelled_amount(lines, ("subtotal", "sub total"))


def extract_tax(lines: list[str]) -> str | None:
    return _find_labelled_amount(lines, ("tax", "vat", "gst"))


def extract_currency(text: str) -> str | None:
    for symbol, code in CURRENCY_SYMBOLS.items():
        if symbol in text:
            return code
    upper = text.upper()
    for code in CURRENCY_CODES:
        if re.search(rf"\b{code}\b", upper):
            return code
    return None


def extract_items(lines: list[str]) -> list[RawItem]:
    items: list[RawItem] = []
    for line in lines:
        lowered = line.lower()
        if any(keyword in lowered for keyword in SKIP_KEYWORDS):
            continue
        for pattern in ITEM_PATTERNS:
            match = pattern.match(line)
            if not match:
                continue
            name = match.group("name").strip(" .:-")
            amount = match.group("amount").strip()
            quantity = match.groupdict().get("qty") or "1"
            if len(name) < 2 or not any(character.isalpha() for character in name):
                break
            if AMOUNT_RE.fullmatch(name):
                break
            items.append(RawItem(description=name, amount=amount, quantity=quantity))
            break
    return items


def extract_receipt(text: str) -> RawReceipt:
    lines = _clean_lines(text)
    joined = "\n".join(lines)
    return RawReceipt(
        merchant=extract_merchant(lines),
        date=extract_date(joined),
        total=extract_total(lines),
        subtotal=extract_subtotal(lines),
        tax=extract_tax(lines),
        currency=extract_currency(joined),
        items=extract_items(lines),
        raw_text=text,
    )
