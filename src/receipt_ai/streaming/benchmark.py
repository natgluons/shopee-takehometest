"""Benchmark harness comparing CSV processing strategies.

The harness records wall time, traced Python allocation peak, and throughput. Traced memory is the
primary comparison because it isolates allocations made by each strategy. Process RSS is included
for context, but it is a high-water mark for the whole process and is not reset between runs.
"""

from __future__ import annotations

import gc
import itertools
import platform
import resource
import sys
import tempfile
import time
import tracemalloc
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from receipt_ai.streaming.aggregations import AggregationConfig, StreamingAggregator
from receipt_ai.streaming.reader import IncrementalCsvReader
from receipt_ai.streaming.writer import partition_by_date_year, stream_and_partition


@dataclass
class BenchmarkResult:
    strategy: str
    rows: int
    seconds: float
    peak_traced_mb: float
    rss_mb: float
    rows_per_second: float
    notes: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _rss_mb() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
    return round(usage / divisor, 2)


def _measure(strategy: str, rows: int, function: Callable[[], Any], notes: str = "") -> tuple[BenchmarkResult, Any]:
    gc.collect()
    tracemalloc.start()
    start = time.perf_counter()
    value = function()
    elapsed = time.perf_counter() - start
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    result = BenchmarkResult(
        strategy=strategy,
        rows=rows,
        seconds=round(elapsed, 4),
        peak_traced_mb=round(peak / (1024 * 1024), 2),
        rss_mb=_rss_mb(),
        rows_per_second=round(rows / elapsed, 1) if elapsed else 0.0,
        notes=notes,
    )
    return result, value


def _take(iterable: Iterable[Any], limit: int | None) -> Iterable[Any]:
    if limit is None:
        return iterable
    return itertools.islice(iterable, limit)


def _aggregate_limited(
    path: str | Path,
    limit: int | None,
    batch_size: int,
    config: AggregationConfig | None = None,
) -> dict[str, Any]:
    reader = IncrementalCsvReader(path, chunk_size=batch_size)
    aggregator = StreamingAggregator(config or AggregationConfig())
    for row in _take(reader.iter_rows(), limit):
        aggregator.add_row(row)
    summary = aggregator.summary()
    summary["reader"] = reader.stats.to_dict()
    return summary


def _naive_load(path: str | Path, limit: int | None) -> list[dict[str, str]]:
    reader = IncrementalCsvReader(path, chunk_size=1000)
    return list(_take(reader.iter_rows(), limit))


def _split_limited(
    path: str | Path, limit: int | None, limit_dir: Path, max_rows_per_file: int = 0
) -> dict[str, Any]:
    reader = IncrementalCsvReader(path, chunk_size=5000)
    from receipt_ai.streaming.writer import PartitionedCsvWriter

    with PartitionedCsvWriter(
        output_dir=limit_dir,
        fieldnames=reader.fieldnames or _header(path),
        partition_by=partition_by_date_year(),
        max_rows_per_file=max_rows_per_file,
    ) as writer:
        for row in _take(reader.iter_rows(), limit):
            writer.write(row)
        manifest = writer.close()
    return manifest.to_dict()


def _header(path: str | Path) -> list[str]:
    import csv

    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return next(csv.reader(handle))


def run_benchmark(
    path: str | Path,
    limit: int | None = 200_000,
    batch_sizes: tuple[int, ...] = (1_000, 10_000, 50_000),
    include_split: bool = True,
    config: AggregationConfig | None = None,
) -> dict[str, Any]:
    """Compare naive loading, streaming, batching, and partitioned splits."""
    path = Path(path)
    results: list[BenchmarkResult] = []
    row_count = min(limit, _count_rows_quick(path)) if limit is not None else _count_rows_quick(path)

    naive_result, naive_rows = _measure(
        "naive_load",
        row_count,
        lambda: _naive_load(path, limit),
        notes="Materializes all selected rows in a list before aggregating.",
    )
    naive_aggregator = StreamingAggregator(config or AggregationConfig())
    naive_aggregator.add_rows(naive_rows)
    results.append(naive_result)
    del naive_rows

    for batch_size in batch_sizes:
        result, _ = _measure(
            f"streaming_batch_{batch_size}",
            row_count,
            lambda size=batch_size: _aggregate_limited(path, limit, size, config),
            notes="Single aggregator, one pass, chunk size equals batch size.",
            )
        result.extra["batch_size"] = batch_size
        results.append(result)

    if include_split:
        with tempfile.TemporaryDirectory(prefix="receipt-ai-split-") as temporary:
            result, manifest = _measure(
                "partitioned_split",
                row_count,
                lambda: _split_limited(path, limit, Path(temporary)),
                notes="Writes partitioned CSV files with a bounded handle pool.",
            )
            result.extra["partition_count"] = manifest["partition_count"]
            results.append(result)

    return {
        "file": str(path),
        "file_size_bytes": path.stat().st_size,
        "limit": limit,
        "row_count": row_count,
        "batch_sizes": list(batch_sizes),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor(),
        },
        "results": [result.to_dict() for result in results],
    }


def _count_rows_quick(path: Path) -> int:
    """Count non-empty data rows without materializing the file."""
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return max(sum(1 for _ in handle) - 1, 0)


def benchmark_csv(
    path: str | Path,
    limit: int | None = 200_000,
    batch_size: int = 10_000,
) -> dict[str, Any]:
    """Run a focused benchmark with one batch size."""
    return run_benchmark(path, limit=limit, batch_sizes=(batch_size,))
