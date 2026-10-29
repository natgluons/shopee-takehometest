"""Monetary helpers that keep stored values as integer cents."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")
CURRENCY_RE = re.compile(r"[^0-9.,()\-]")


class MoneyParseError(ValueError):
    """Raised when an amount cannot be parsed."""


def cents_to_decimal(cents: int) -> Decimal:
    return (Decimal(int(cents)) / 100).quantize(CENT)


def cents_to_str(cents: int) -> str:
    return f"{cents_to_decimal(cents):.2f}"


def decimal_to_cents(amount: Decimal | str | int | float) -> int:
    try:
        value = Decimal(str(amount))
    except (InvalidOperation, ValueError) as exc:
        raise MoneyParseError(f"invalid amount: {amount!r}") from exc
    return int((value.quantize(CENT, rounding=ROUND_HALF_UP) * 100).to_integral_value())


def parse_amount_to_cents(value: str | int | float | Decimal) -> int:
    """Parse a formatted amount such as ``$1,234.56`` or ``1.234,56`` into cents."""
    if isinstance(value, int):
        return value * 100
    if isinstance(value, (float, Decimal)):
        return decimal_to_cents(value)
    raw = str(value).strip()
    if not raw:
        raise MoneyParseError("amount is empty")
    negative = raw.startswith("(") and raw.endswith(")")
    if negative:
        raw = raw[1:-1]
    cleaned = CURRENCY_RE.sub("", raw).strip()
    if not cleaned or cleaned in {"-", ".", ","}:
        raise MoneyParseError(f"invalid amount: {value!r}")
    if cleaned.startswith("-"):
        negative = True
        cleaned = cleaned[1:]
    has_comma = "," in cleaned
    has_dot = "." in cleaned
    if has_comma and has_dot:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif has_comma:
        parts = cleaned.split(",")
        if len(parts) == 2 and len(parts[1]) in {1, 2}:
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif has_dot:
        parts = cleaned.split(".")
        if len(parts) > 2:
            cleaned = "".join(parts[:-1]) + "." + parts[-1]
    try:
        amount = Decimal(cleaned)
    except InvalidOperation as exc:
        raise MoneyParseError(f"invalid amount: {value!r}") from exc
    if amount < 0:
        negative = True
    cents = decimal_to_cents(abs(amount))
    return -cents if negative else cents
