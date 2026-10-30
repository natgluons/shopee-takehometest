"""Partitioned CSV writer for streaming exports.

Rows are written to one file per partition key with an optional row cap per file. Open file handles
are bounded, so partitioning by a high-cardinality column does not exhaust file descriptors.
"""

from __future__ import annotations

import csv
import re
from collections import OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, TextIO

from receipt_ai.streaming.aggregations import parse_date
from receipt_ai.streaming.reader import IncrementalCsvReader

SLUG_RE = re.compile(r"[^A-Za-z0-9._-]+")


def slugify(value: str, fallback: str = "unknown", max_length: int = 80) -> str:
    slug = SLUG_RE.sub("_", value.strip()).strip("._-")
    return (slug or fallback)[:max_length]


def partition_by_field(field_name: str) -> Callable[[dict[str, str]], str]:
    def partition(row: dict[str, str]) -> str:
        return row.get(field_name, "") or "unknown"

    return partition


def partition_by_date_year(
    field_name: str = "Subscription Date", fallback: str = "unknown"
) -> Callable[[dict[str, str]], str]:
    def partition(row: dict[str, str]) -> str:
        value = row.get(field_name, "")
        parsed = parse_date(value) if value else None
        return str(parsed.year) if parsed else fallback

    return partition


def partition_by_first_letter(field_name: str = "Country") -> Callable[[dict[str, str]], str]:
    def partition(row: dict[str, str]) -> str:
        value = (row.get(field_name, "") or "").strip()
        return value[0].upper() if value else "unknown"

    return partition


@dataclass
class _PartitionHandle:
    handle: TextIO
    writer: csv.DictWriter
    part: int
    rows: int = 0


@dataclass
class PartitionManifest:
    partitions: dict[str, dict[str, Any]] = field(default_factory=dict)
    total_rows: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_rows": self.total_rows,
            "partition_count": len(self.partitions),
            "partitions": self.partitions,
        }


class PartitionedCsvWriter:
    """Write rows into partition directories with bounded open handles."""

    def __init__(
        self,
        output_dir: str | Path,
        fieldnames: Sequence[str],
        partition_by: Callable[[dict[str, str]], str],
        max_rows_per_file: int = 0,
        max_open_files: int = 64,
        partition_prefix: str = "partition",
    ) -> None:
        if max_rows_per_file < 0:
            raise ValueError("max_rows_per_file cannot be negative")
        if max_open_files < 1:
            raise ValueError("max_open_files must be at least 1")
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.fieldnames = list(fieldnames)
        self.partition_by = partition_by
        self.max_rows_per_file = max_rows_per_file
        self.max_open_files = max_open_files
        self.partition_prefix = partition_prefix
        self._handles: OrderedDict[str, _PartitionHandle] = OrderedDict()
        self._current_part: dict[str, int] = {}
        self.manifest = PartitionManifest()

    def _partition_dir(self, partition: str) -> Path:
        return self.output_dir / f"{self.partition_prefix}={slugify(partition)}"

    def _open_partition(self, partition: str) -> _PartitionHandle:
        part = self._current_part.get(partition, 1)
        directory = self._partition_dir(partition)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"part-{part:05d}.csv"
        is_new = not path.exists()
        handle = path.open("a", encoding="utf-8", newline="")
        writer = csv.DictWriter(
            handle, fieldnames=self.fieldnames, extrasaction="ignore", lineterminator="\n"
        )
        if is_new:
            writer.writeheader()
        record = self.manifest.partitions.setdefault(partition, {"rows": 0, "files": []})
        if str(path) not in record["files"]:
            record["files"].append(str(path))
        return _PartitionHandle(handle=handle, writer=writer, part=part)

    def _close_oldest(self) -> None:
        if not self._handles:
            return
        partition, record = self._handles.popitem(last=False)
        record.handle.close()

    def write(self, row: dict[str, str]) -> None:
        partition = self.partition_by(row) or "unknown"
        record = self._handles.get(partition)
        if record is None:
            if len(self._handles) >= self.max_open_files:
                self._close_oldest()
            record = self._open_partition(partition)
            self._handles[partition] = record
        else:
            self._handles.move_to_end(partition)
        record.writer.writerow(row)
        record.rows += 1
        record_entry = self.manifest.partitions.setdefault(partition, {"rows": 0, "files": []})
        record_entry["rows"] += 1
        self.manifest.total_rows += 1
        if self.max_rows_per_file and record.rows >= self.max_rows_per_file:
            record.handle.close()
            del self._handles[partition]
            self._current_part[partition] = record.part + 1

    def write_rows(self, rows: Sequence[dict[str, str]]) -> int:
        for row in rows:
            self.write(row)
        return len(rows)

    def close(self) -> PartitionManifest:
        for record in self._handles.values():
            record.handle.close()
        self._handles.clear()
        return self.manifest

    def __enter__(self) -> PartitionedCsvWriter:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()


def stream_and_partition(
    path: str | Path,
    output_dir: str | Path,
    partition_by: Callable[[dict[str, str]], str],
    max_rows_per_file: int = 0,
    max_open_files: int = 64,
    batch_size: int = 5000,
) -> dict[str, Any]:
    """Stream a CSV into partitioned files and return a manifest."""
    reader = IncrementalCsvReader(path, chunk_size=batch_size)
    with PartitionedCsvWriter(
        output_dir=output_dir,
        fieldnames=reader.fieldnames or _peek_header(path),
        partition_by=partition_by,
        max_rows_per_file=max_rows_per_file,
        max_open_files=max_open_files,
    ) as writer:
        for batch in reader.iter_chunks():
            writer.write_rows(batch)
        manifest = writer.close()
    return {
        "manifest": manifest.to_dict(),
        "reader": reader.stats.to_dict(),
        "output_dir": str(output_dir),
    }


def _peek_header(path: str | Path) -> list[str]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return next(csv.reader(handle))
