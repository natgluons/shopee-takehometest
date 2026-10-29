"""Descriptive statistics for the customer dataset."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from receipt_ai.csv_analysis.quality import EMAIL_RE

DEFAULT_CATEGORICAL_COLUMNS = ("Country", "City", "Company")


def _round(value: Any, digits: int = 6) -> float | None:
    if pd.isna(value):
        return None
    return round(float(value), digits)


def describe_numeric(frame: pd.DataFrame, columns: tuple[str, ...] = ("Index",)) -> dict[str, Any]:
    """Describe numeric columns that exist in the frame."""
    output: dict[str, Any] = {}
    for column in columns:
        if column not in frame:
            continue
        values = pd.to_numeric(frame[column], errors="coerce").dropna()
        if values.empty:
            continue
        output[column] = {
            "count": int(values.count()),
            "mean": _round(values.mean()),
            "std": _round(values.std()),
            "min": _round(values.min()),
            "p25": _round(values.quantile(0.25)),
            "median": _round(values.median()),
            "p75": _round(values.quantile(0.75)),
            "max": _round(values.max()),
            "sum": _round(values.sum()),
        }
    return output


def subscription_timeline(frame: pd.DataFrame) -> dict[str, Any]:
    """Summarize subscription dates by year and month."""
    if "Subscription Date" not in frame:
        return {}
    dates = pd.to_datetime(frame["Subscription Date"], errors="coerce", format="mixed").dropna()
    if dates.empty:
        return {}
    monthly = dates.dt.to_period("M").value_counts().sort_index()
    yearly = dates.dt.year.value_counts().sort_index()
    return {
        "min_date": dates.min().date().isoformat(),
        "max_date": dates.max().date().isoformat(),
        "span_days": int((dates.max() - dates.min()).days),
        "by_year": {str(key): int(value) for key, value in yearly.items()},
        "by_month": {str(key): int(value) for key, value in monthly.items()},
        "peak_month": str(monthly.idxmax()),
        "peak_month_count": int(monthly.max()),
    }


def categorical_distribution(
    frame: pd.DataFrame, column: str, top_n: int = 15
) -> dict[str, Any]:
    """Return the top values and their share of non-null rows."""
    if column not in frame:
        return {}
    values = frame[column].dropna().astype(str).str.strip()
    if values.empty:
        return {}
    counts = values.value_counts()
    total = int(counts.sum())
    top = counts.head(top_n)
    return {
        "distinct": int(counts.size),
        "total_non_null": total,
        "top": {str(key): int(value) for key, value in top.items()},
        "top_share": {str(key): round(int(value) / total, 6) for key, value in top.items()},
        "concentration_top_10": round(int(counts.head(10).sum()) / total, 6),
    }


def email_domain_distribution(frame: pd.DataFrame, top_n: int = 15) -> dict[str, Any]:
    """Return the most common email domains."""
    if "Email" not in frame:
        return {}
    emails = frame["Email"].dropna().astype(str).str.strip()
    valid = emails[emails.map(lambda value: bool(EMAIL_RE.match(value)))]
    domains = valid.str.split("@").str[-1].str.lower()
    if domains.empty:
        return {}
    counts = domains.value_counts()
    total = int(counts.sum())
    return {
        "distinct": int(counts.size),
        "top": {str(key): int(value) for key, value in counts.head(top_n).items()},
        "free_email_share": round(
            int(counts[counts.index.isin({"gmail.com", "yahoo.com", "hotmail.com", "outlook.com"})].sum())
            / total,
            6,
        ),
    }


def describe_dataset(path: str | Path) -> dict[str, Any]:
    """Return descriptive statistics for a customer CSV file."""
    frame = pd.read_csv(path, dtype=str, low_memory=False)
    categorical = {
        column: categorical_distribution(frame, column)
        for column in DEFAULT_CATEGORICAL_COLUMNS
    }
    return {
        "path": str(path),
        "row_count": int(len(frame)),
        "numeric": describe_numeric(frame),
        "subscription_timeline": subscription_timeline(frame),
        "categorical": categorical,
        "email_domains": email_domain_distribution(frame),
    }
