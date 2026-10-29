"""Observable customer segmentation.

The source data has no transaction history, so revenue style RFM segmentation is not possible. These
segments use fields that actually exist: subscription recency, subscription cohort, geography,
email domain type, and contact completeness. The output labels are descriptive, not predictive.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from receipt_ai.csv_analysis.quality import EMAIL_RE

FREE_EMAIL_DOMAINS = {"gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "aol.com"}


def _bucket_recency(days: int) -> str:
    if days <= 90:
        return "new_0_90_days"
    if days <= 365:
        return "active_91_365_days"
    if days <= 730:
        return "lapsing_366_730_days"
    return "dormant_over_730_days"


def recency_segments(frame: pd.DataFrame, reference_date: str | None = None) -> dict[str, Any]:
    """Group customers by days since subscription relative to a reference date."""
    if "Subscription Date" not in frame:
        return {}
    dates = pd.to_datetime(frame["Subscription Date"], errors="coerce", format="mixed").dropna()
    if dates.empty:
        return {}
    reference = pd.Timestamp(reference_date) if reference_date else dates.max()
    days = (reference - dates).dt.days
    labels = days.map(_bucket_recency)
    counts = labels.value_counts()
    total = int(counts.sum())
    return {
        "reference_date": reference.date().isoformat(),
        "total": total,
        "segments": {
            str(key): {"count": int(value), "share": round(int(value) / total, 6)}
            for key, value in counts.items()
        },
    }


def cohort_segments(frame: pd.DataFrame) -> dict[str, Any]:
    """Group customers by subscription year."""
    if "Subscription Date" not in frame:
        return {}
    dates = pd.to_datetime(frame["Subscription Date"], errors="coerce", format="mixed").dropna()
    if dates.empty:
        return {}
    counts = dates.dt.year.value_counts().sort_index()
    total = int(counts.sum())
    return {
        "total": total,
        "cohorts": {
            str(key): {"count": int(value), "share": round(int(value) / total, 6)}
            for key, value in counts.items()
        },
    }


def geographic_segments(frame: pd.DataFrame, top_n: int = 10) -> dict[str, Any]:
    """Group customers by country, folding the long tail into Other."""
    if "Country" not in frame:
        return {}
    countries = frame["Country"].dropna().astype(str).str.strip()
    if countries.empty:
        return {}
    counts = countries.value_counts()
    total = int(counts.sum())
    top = counts.head(top_n)
    other = int(counts.iloc[top_n:].sum())
    segments = {
        str(key): {"count": int(value), "share": round(int(value) / total, 6)}
        for key, value in top.items()
    }
    if other:
        segments["Other"] = {"count": other, "share": round(other / total, 6)}
    return {
        "distinct_countries": int(counts.size),
        "total": total,
        "segments": segments,
    }


def email_type_segments(frame: pd.DataFrame) -> dict[str, Any]:
    """Split customers by free, corporate, and invalid email domains."""
    if "Email" not in frame:
        return {}
    emails = frame["Email"].dropna().astype(str).str.strip().str.lower()
    valid = emails[emails.map(lambda value: bool(EMAIL_RE.match(value)))]
    domains = valid.str.split("@").str[-1]
    buckets: dict[str, int] = {
        "free_email": int(domains.isin(FREE_EMAIL_DOMAINS).sum()),
        "corporate_email": int((~domains.isin(FREE_EMAIL_DOMAINS)).sum()),
        "missing_or_invalid": int(len(frame) - len(valid)),
    }
    total = max(len(frame), 1)
    return {
        "total": int(len(frame)),
        "segments": {
            key: {"count": value, "share": round(value / total, 6)}
            for key, value in buckets.items()
        },
    }


def contactability_segments(frame: pd.DataFrame) -> dict[str, Any]:
    """Split customers by whether there is a usable email and phone number."""
    total = int(len(frame))
    if total == 0:
        return {"total": 0, "segments": {}}
    emails = (
        frame["Email"].dropna().astype(str).str.strip()
        if "Email" in frame
        else pd.Series(dtype=str)
    )
    has_email = emails.map(lambda value: bool(EMAIL_RE.match(value)))
    has_phone = (
        frame["Phone 1"].notna() if "Phone 1" in frame else pd.Series(False, index=frame.index)
    )
    segments = {
        "email_and_phone": int((has_email & has_phone).sum()),
        "email_only": int((has_email & ~has_phone).sum()),
        "phone_only": int((~has_email & has_phone).sum()),
        "no_contact": int((~has_email & ~has_phone).sum()),
    }
    return {
        "total": total,
        "segments": {
            key: {"count": value, "share": round(value / total, 6)}
            for key, value in segments.items()
        },
    }


def segmentation_report(
    path: str | Path, reference_date: str | None = None
) -> dict[str, Any]:
    """Return all segmentation views for a customer CSV file."""
    frame = pd.read_csv(path, dtype=str, low_memory=False)
    return {
        "path": str(path),
        "row_count": int(len(frame)),
        "recency": recency_segments(frame, reference_date),
        "cohort": cohort_segments(frame),
        "geography": geographic_segments(frame),
        "email_type": email_type_segments(frame),
        "contactability": contactability_segments(frame),
        "caveat": (
            "Segments are descriptive. The dataset has no transactions, so no monetary value or "
            "churn outcome is inferred."
        ),
    }
