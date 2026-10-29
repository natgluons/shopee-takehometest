"""Single-pass, bounded-state aggregations for large CSV files.

Every structure in this module has a fixed or configurable upper bound. Numeric moments use
Welford's algorithm. Categorical counters stop accepting new keys after a cap and report how many
observations were not tracked. Duplicate identifiers use a Bloom filter, so the duplicate count is
explicitly approximate and memory stays at a few megabytes.
"""

from __future__ import annotations

import hashlib
import math
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y", "%Y/%m/%d")


def parse_date(value: str) -> date | None:
    """Parse a limited set of date formats without pandas."""
    text = value.strip()
    if not text:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


@dataclass
class NumericStats:
    """Numerically stable running mean and variance."""

    count: int = 0
    mean: float = 0.0
    m2: float = 0.0
    minimum: float | None = None
    maximum: float | None = None
    total: float = 0.0
    invalid: int = 0

    def add(self, value: float) -> None:
        self.count += 1
        delta = value - self.mean
        self.mean += delta / self.count
        self.m2 += delta * (value - self.mean)
        self.total += value
        self.minimum = value if self.minimum is None else min(self.minimum, value)
        self.maximum = value if self.maximum is None else max(self.maximum, value)

    @property
    def variance(self) -> float:
        return self.m2 / (self.count - 1) if self.count > 1 else 0.0

    @property
    def std(self) -> float:
        return math.sqrt(self.variance)

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "invalid": self.invalid,
            "mean": round(self.mean, 6),
            "std": round(self.std, 6),
            "min": self.minimum,
            "max": self.maximum,
            "sum": round(self.total, 6),
        }


class BoundedCounter:
    """Count values with a hard cap on the number of tracked keys."""

    def __init__(self, max_keys: int = 200_000) -> None:
        if max_keys < 1:
            raise ValueError("max_keys must be at least 1")
        self.max_keys = max_keys
        self.counts: Counter[str] = Counter()
        self.dropped_observations = 0

    def add(self, key: str, amount: int = 1) -> None:
        if key in self.counts:
            self.counts[key] += amount
            return
        if len(self.counts) < self.max_keys:
            self.counts[key] = amount
            return
        self.dropped_observations += amount

    def top(self, n: int = 10) -> dict[str, int]:
        return {str(key): int(value) for key, value in self.counts.most_common(n)}

    @property
    def distinct_observed(self) -> int:
        return len(self.counts)


class BloomFilter:
    """Fixed-size approximate membership filter for duplicate detection."""

    def __init__(self, bits: int = 1 << 26, hashes: int = 4) -> None:
        if bits < 8:
            raise ValueError("bits must be at least 8")
        self.bits = bits
        self.hashes = hashes
        self._buffer = bytearray(bits // 8)
        self.insertions = 0
        self.probable_duplicates = 0

    def _positions(self, value: str) -> list[int]:
        digest = hashlib.blake2b(value.encode("utf-8"), digest_size=16).digest()
        first = int.from_bytes(digest[:8], "big")
        second = int.from_bytes(digest[8:], "big") | 1
        return [(first + index * second) % self.bits for index in range(self.hashes)]

    def check_and_add(self, value: str) -> bool:
        """Return True when the value was probably seen before, then add it."""
        positions = self._positions(value)
        present = all(
            self._buffer[position // 8] & (1 << (position % 8)) for position in positions
        )
        for position in positions:
            self._buffer[position // 8] |= 1 << (position % 8)
        self.insertions += 1
        if present:
            self.probable_duplicates += 1
        return present

    @property
    def memory_bytes(self) -> int:
        return len(self._buffer)

    @property
    def false_positive_rate(self) -> float:
        if self.bits == 0:
            return 0.0
        load = self.insertions / self.bits
        return round((1 - math.exp(-self.hashes * load)) ** self.hashes, 9)


@dataclass
class AggregationConfig:
    numeric_columns: tuple[str, ...] = ("Index",)
    categorical_columns: tuple[str, ...] = ("Country",)
    email_column: str = "Email"
    date_column: str = "Subscription Date"
    id_column: str = "Customer Id"
    top_n: int = 10
    max_categories: int = 50_000
    bloom_bits: int = 1 << 25


@dataclass
class StreamingAggregator:
    """Accumulate statistics over rows in one pass with bounded memory."""

    config: AggregationConfig = field(default_factory=AggregationConfig)
    rows: int = 0
    null_counts: Counter[str] = field(default_factory=Counter)
    numeric: dict[str, NumericStats] = field(default_factory=dict)
    categories: dict[str, BoundedCounter] = field(default_factory=dict)
    email_domains: BoundedCounter = field(init=False)
    dates_by_year: Counter[int] = field(default_factory=Counter)
    date_min: date | None = None
    date_max: date | None = None
    invalid_dates: int = 0
    ids: BloomFilter = field(init=False)
    duplicate_ids: int = 0
    missing_ids: int = 0

    def __post_init__(self) -> None:
        self.numeric = {name: NumericStats() for name in self.config.numeric_columns}
        self.categories = {
            name: BoundedCounter(self.config.max_categories)
            for name in self.config.categorical_columns
        }
        self.email_domains = BoundedCounter(self.config.max_categories)
        self.ids = BloomFilter(self.config.bloom_bits)

    def add_row(self, row: dict[str, str]) -> None:
        self.rows += 1
        for key, value in row.items():
            if value is None or not str(value).strip():
                self.null_counts[key] += 1

        for column, stats in self.numeric.items():
            raw = row.get(column)
            if raw is None or not str(raw).strip():
                continue
            try:
                stats.add(float(str(raw).replace(",", "")))
            except ValueError:
                stats.invalid += 1

        for column, counter in self.categories.items():
            raw = row.get(column)
            if raw is not None and str(raw).strip():
                counter.add(str(raw).strip())

        email = row.get(self.config.email_column)
        if email and "@" in email:
            domain = email.rsplit("@", 1)[-1].strip().lower()
            if domain:
                self.email_domains.add(domain)

        raw_date = row.get(self.config.date_column)
        if raw_date and str(raw_date).strip():
            parsed = parse_date(str(raw_date))
            if parsed is None:
                self.invalid_dates += 1
            else:
                self.dates_by_year[parsed.year] += 1
                self.date_min = parsed if self.date_min is None else min(self.date_min, parsed)
                self.date_max = parsed if self.date_max is None else max(self.date_max, parsed)

        identifier = row.get(self.config.id_column)
        if identifier and str(identifier).strip():
            if self.ids.check_and_add(str(identifier).strip()):
                self.duplicate_ids += 1
        else:
            self.missing_ids += 1

    def add_rows(self, rows: Iterable[dict[str, str]]) -> int:
        count = 0
        for row in rows:
            self.add_row(row)
            count += 1
        return count

    def summary(self) -> dict[str, Any]:
        return {
            "rows": self.rows,
            "null_counts": {key: int(value) for key, value in self.null_counts.items()},
            "numeric": {key: stats.to_dict() for key, stats in self.numeric.items()},
            "categorical": {
                key: {
                    "distinct_observed": counter.distinct_observed,
                    "dropped_observations": counter.dropped_observations,
                    "top": counter.top(self.config.top_n),
                }
                for key, counter in self.categories.items()
            },
            "email_domains": {
                "distinct_observed": self.email_domains.distinct_observed,
                "dropped_observations": self.email_domains.dropped_observations,
                "top": self.email_domains.top(self.config.top_n),
            },
            "dates": {
                "min": self.date_min.isoformat() if self.date_min else None,
                "max": self.date_max.isoformat() if self.date_max else None,
                "by_year": {str(key): int(value) for key, value in sorted(self.dates_by_year.items())},
                "invalid": self.invalid_dates,
            },
            "identifiers": {
                "observed": self.ids.insertions,
                "missing": self.missing_ids,
                "probable_duplicates": self.duplicate_ids,
                "bloom_memory_bytes": self.ids.memory_bytes,
                "bloom_false_positive_rate": self.ids.false_positive_rate,
                "note": "Duplicate count is approximate because a Bloom filter is used.",
            },
        }


def aggregate_csv(
    path: str | Path,
    batch_size: int = 10_000,
    config: AggregationConfig | None = None,
) -> dict[str, Any]:
    """Stream a CSV and return bounded-memory aggregates plus reader diagnostics."""
    from receipt_ai.streaming.reader import IncrementalCsvReader

    reader = IncrementalCsvReader(path, chunk_size=batch_size)
    aggregator = StreamingAggregator(config or AggregationConfig())
    for chunk in reader.iter_chunks():
        aggregator.add_rows(chunk)
    summary = aggregator.summary()
    summary["reader"] = reader.stats.to_dict()
    summary["file_size_bytes"] = reader.file_size_bytes
    summary["batch_size"] = batch_size
    return summary
