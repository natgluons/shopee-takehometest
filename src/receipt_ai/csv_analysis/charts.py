"""Exploratory charts for the 100k customer dataset."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from receipt_ai.csv_analysis.quality import EMAIL_RE  # noqa: E402
from receipt_ai.csv_analysis.stats import categorical_distribution  # noqa: E402

plt.rcParams.update({"figure.autolayout": True, "font.size": 10})


def _save(figure: plt.Figure, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=140, bbox_inches="tight")
    plt.close(figure)
    return str(path)


def plot_subscriptions_over_time(frame: pd.DataFrame, output_dir: Path) -> str | None:
    if "Subscription Date" not in frame:
        return None
    dates = pd.to_datetime(frame["Subscription Date"], errors="coerce", format="mixed").dropna()
    if dates.empty:
        return None
    monthly = dates.dt.to_period("M").value_counts().sort_index()
    figure, axis = plt.subplots(figsize=(10, 4.5))
    axis.plot([str(period) for period in monthly.index], monthly.values, color="#2563eb")
    axis.set_title("Subscriptions per month")
    axis.set_xlabel("Month")
    axis.set_ylabel("Customers")
    axis.tick_params(axis="x", rotation=60, labelsize=7)
    every = max(len(monthly) // 18, 1)
    for index, label in enumerate(axis.get_xticklabels()):
        label.set_visible(index % every == 0)
    return _save(figure, output_dir / "subscriptions_over_time.png")


def plot_top_countries(frame: pd.DataFrame, output_dir: Path, top_n: int = 15) -> str | None:
    distribution = categorical_distribution(frame, "Country", top_n=top_n)
    if not distribution:
        return None
    top = distribution["top"]
    figure, axis = plt.subplots(figsize=(9, 5))
    names = list(top.keys())[::-1]
    values = [top[name] for name in names]
    axis.barh(names, values, color="#0f766e")
    axis.set_title(f"Top {len(names)} countries by customer count")
    axis.set_xlabel("Customers")
    return _save(figure, output_dir / "top_countries.png")


def plot_email_domains(frame: pd.DataFrame, output_dir: Path, top_n: int = 12) -> str | None:
    if "Email" not in frame:
        return None
    emails = frame["Email"].dropna().astype(str).str.strip()
    valid = emails[emails.map(lambda value: bool(EMAIL_RE.match(value)))]
    domains = valid.str.split("@").str[-1].str.lower().value_counts().head(top_n)
    if domains.empty:
        return None
    figure, axis = plt.subplots(figsize=(9, 5))
    names = list(domains.index)[::-1]
    values = list(domains.values)[::-1]
    axis.barh(names, values, color="#7c3aed")
    axis.set_title(f"Top {len(names)} email domains")
    axis.set_xlabel("Customers")
    return _save(figure, output_dir / "email_domains.png")


def plot_missing_values(frame: pd.DataFrame, output_dir: Path) -> str:
    ratios = frame.isna().mean().sort_values(ascending=True)
    figure, axis = plt.subplots(figsize=(9, 5))
    axis.barh(list(ratios.index), list(ratios.values * 100), color="#dc2626")
    axis.set_title("Missing values by column")
    axis.set_xlabel("Missing (%)")
    return _save(figure, output_dir / "missing_values.png")


def plot_subscription_cohorts(frame: pd.DataFrame, output_dir: Path) -> str | None:
    if "Subscription Date" not in frame:
        return None
    dates = pd.to_datetime(frame["Subscription Date"], errors="coerce", format="mixed").dropna()
    if dates.empty:
        return None
    yearly = dates.dt.year.value_counts().sort_index()
    figure, axis = plt.subplots(figsize=(8, 4.5))
    axis.bar([str(year) for year in yearly.index], yearly.values, color="#ea580c")
    axis.set_title("Subscription cohort by year")
    axis.set_xlabel("Subscription year")
    axis.set_ylabel("Customers")
    return _save(figure, output_dir / "subscription_cohorts.png")


def generate_charts(path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    """Generate all exploratory charts and return the written paths."""
    frame = pd.read_csv(path, dtype=str, low_memory=False)
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    results = {
        "subscriptions_over_time": plot_subscriptions_over_time(frame, target),
        "top_countries": plot_top_countries(frame, target),
        "email_domains": plot_email_domains(frame, target),
        "missing_values": plot_missing_values(frame, target),
        "subscription_cohorts": plot_subscription_cohorts(frame, target),
    }
    return {key: value for key, value in results.items() if value}
