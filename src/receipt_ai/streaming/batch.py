"""Configurable batch processing built on the incremental reader."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TypeVar

from receipt_ai.streaming.aggregations import AggregationConfig, StreamingAggregator
from receipt_ai.streaming.reader import IncrementalCsvReader

T = TypeVar("T")
R = TypeVar("R")


@dataclass
class BatchResult:
    """Summary of a batch processing run."""

    batch_size: int
    batch_count: int
    row_count: int
    results: list[Any] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "batch_size": self.batch_size,
            "batch_count": self.batch_count,
            "row_count": self.row_count,
            "result_count": len(self.results),
        }


def chunked(items: Iterable[T], size: int) -> Iterator[list[T]]:
    """Yield lists of at most ``size`` items, including the final partial list."""
    if size < 1:
        raise ValueError("batch size must be at least 1")
    batch: list[T] = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def process_in_batches(
    items: Iterable[T],
    batch_size: int,
    handler: Callable[[list[T]], R],
) -> BatchResult:
    """Apply ``handler`` to each batch and collect the handler results."""
    if batch_size < 1:
        raise ValueError("batch size must be at least 1")
    results: list[Any] = []
    row_count = 0
    batch_count = 0
    for batch in chunked(items, batch_size):
        results.append(handler(batch))
        row_count += len(batch)
        batch_count += 1
    return BatchResult(
        batch_size=batch_size,
        batch_count=batch_count,
        row_count=row_count,
        results=results,
    )


def process_csv_in_batches(
    path: str | Path,
    batch_size: int = 10_000,
    handler: Callable[[list[dict[str, str]]], R] | None = None,
    config: AggregationConfig | None = None,
) -> dict[str, Any]:
    """Read a CSV in configurable batches and optionally call a handler per batch."""
    if batch_size < 1:
        raise ValueError("batch size must be at least 1")
    reader = IncrementalCsvReader(path, chunk_size=batch_size)
    aggregator = StreamingAggregator(config or AggregationConfig())
    handler_results: list[Any] = []
    batch_count = 0
    for batch in reader.iter_chunks():
        batch_count += 1
        aggregator.add_rows(batch)
        if handler is not None:
            handler_results.append(handler(batch))
    summary = aggregator.summary()
    summary["reader"] = reader.stats.to_dict()
    summary["processing"] = {
        "batch_size": batch_size,
        "batch_count": batch_count,
        "handler_result_count": len(handler_results),
    }
    return summary


def iter_csv_batches(
    path: str | Path, batch_size: int = 10_000
) -> Iterator[tuple[IncrementalCsvReader, list[dict[str, str]]]]:
    """Yield the reader and each batch so callers can inspect read statistics."""
    reader = IncrementalCsvReader(path, chunk_size=batch_size)
    for batch in reader.iter_chunks():
        yield reader, batch
