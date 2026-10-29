"""Dataset quality profiling for the customer CSV.

The profiler is intentionally explicit about what it measures. Data quality findings are more
useful when the definition is visible in the output. It runs on the 100k file comfortably. The 2M
file should use the streaming profiler instead.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
PHONE_RE = re.compile(r"^\+?[\d\s().-]{7,}$")
EXPECTED_COLUMNS = (
    "Index",
    "Customer Id",
    "First Name",
    "Last Name",
    "Company",
    "City",
    "Country",
    "Phone 1",
    "Phone 2",
    "Email",
    "Subscription Date",
    "Website",
)


def _to_int(value: Any) -> int:
    return int(value) if pd.notna(value) else 0


def _to_float(value: Any) -> float:
    return round(float(value), 6) if pd.notna(value) else 0.0


def _column_quality(series: pd.Series) -> dict[str, Any]:
    non_null = series.dropna()
    text = non_null.astype(str)
    whitespace = text[text != text.str.strip()]
    empty_strings = text[text.str.strip() == ""]
    return {
        "null_count": _to_int(series.isna().sum()),
        "null_ratio": _to_float(series.isna().mean()),
        "empty_string_count": int(len(empty_strings)),
        "whitespace_issue_count": int(len(whitespace)),
        "distinct_count": int(text.nunique()),
    }


def _email_quality(series: pd.Series) -> dict[str, Any]:
    text = series.dropna().astype(str).str.strip()
    invalid = text[~text.map(lambda value: bool(EMAIL_RE.match(value)))]
    domains = text[text.map(lambda value: bool(EMAIL_RE.match(value)))].str.split("@").str[-1]
    return {
        "invalid_count": int(len(invalid)),
        "invalid_ratio": _to_float(len(invalid) / len(text)) if len(text) else 0.0,
        "top_domains": {str(k): int(v) for k, v in domains.value_counts().head(10).items()},
    }


def _date_quality(series: pd.Series) -> dict[str, Any]:
    non_null = series.dropna().astype(str).str.strip()
    parsed = pd.to_datetime(non_null, errors="coerce", format="mixed")
    invalid = parsed[parsed.isna()]
    valid = parsed.dropna()
    future = valid[valid > pd.Timestamp.now()]
    return {
        "invalid_count": int(len(invalid)),
        "future_count": int(len(future)),
        "min_date": valid.min().date().isoformat() if len(valid) else None,
        "max_date": valid.max().date().isoformat() if len(valid) else None,
    }


def _phone_quality(series: pd.Series) -> dict[str, Any]:
    text = series.dropna().astype(str).str.strip()
    invalid = text[~text.map(lambda value: bool(PHONE_RE.match(value)))]
    return {"invalid_count": int(len(invalid))}


def profile_quality(path: str | Path) -> dict[str, Any]:
    """Return a JSON-serializable quality profile for a customer CSV file."""
    path = Path(path)
    frame = pd.read_csv(path, dtype=str, low_memory=False)
    report: dict[str, Any] = {
        "path": str(path),
        "total_rows": int(len(frame)),
        "total_columns": int(len(frame.columns)),
        "columns": list(frame.columns),
        "missing_expected_columns": [name for name in EXPECTED_COLUMNS if name not in frame],
        "unexpected_columns": [name for name in frame.columns if name not in EXPECTED_COLUMNS],
        "exact_duplicate_rows": _to_int(frame.duplicated().sum()),
        "rows_with_any_null": _to_int(frame.isna().any(axis=1).sum()),
        "column_quality": {
            column: _column_quality(frame[column]) for column in frame.columns
        },
    }

    if "Customer Id" in frame:
        identifiers = frame["Customer Id"].dropna().astype(str)
        duplicated_rows = identifiers[identifiers.duplicated(keep=False)]
        report["customer_ids"] = {
            "unique": int(identifiers.nunique()),
            "duplicate_rows": int(len(duplicated_rows)),
            "duplicate_extra_rows": int(identifiers.duplicated().sum()),
            "missing": _to_int(frame["Customer Id"].isna().sum()),
            "examples": [str(value) for value in duplicated_rows.unique()[:5]],
        }

    if "Email" in frame:
        report["email"] = _email_quality(frame["Email"])
    if "Subscription Date" in frame:
        report["subscription_date"] = _date_quality(frame["Subscription Date"])
    if "Phone 1" in frame:
        report["phone_1"] = _phone_quality(frame["Phone 1"])
    if "Phone 2" in frame:
        report["phone_2"] = _phone_quality(frame["Phone 2"])

    return report
