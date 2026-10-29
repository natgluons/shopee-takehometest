"""Incremental CSV reading with constant memory.

The reader never loads the full file. It streams rows from disk, validates the row width against the
header, and records defects instead of crashing. The caller chooses the chunk size, so the same
reader supports single-row iteration and batch processing.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CsvReadStats:
    """Counters collected while reading a CSV file."""

    total_rows: int = 0
    blank_rows: int = 0
    malformed_rows: int = 0
    missing_field_rows: int = 0
    extra_field_rows: int = 0
    reader_errors: int = 0
    malformed_examples: list[str] = field(default_factory=list)

    def record_malformed(self, reason: str, line_number: int) -> None:
        self.malformed_rows += 1
        if len(self.malformed_examples) < 5:
            self.malformed_examples.append(f"line {line_number}: {reason}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_rows": self.total_rows,
            "blank_rows": self.blank_rows,
            "malformed_rows": self.malformed_rows,
            "missing_field_rows": self.missing_field_rows,
            "extra_field_rows": self.extra_field_rows,
            "reader_errors": self.reader_errors,
            "malformed_examples": list(self.malformed_examples),
        }


class IncrementalCsvReader:
    """Stream a CSV as dictionaries without holding more than one chunk in memory."""

    def __init__(
        self,
        path: str | Path,
        chunk_size: int = 1000,
        encoding: str = "utf-8-sig",
        delimiter: str | None = None,
        quotechar: str = '"',
        strict: bool = False,
    ) -> None:
        if chunk_size < 1:
            raise ValueError("chunk_size must be at least 1")
        self.path = Path(path)
        self.chunk_size = chunk_size
        self.encoding = encoding
        self.delimiter = delimiter
        self.quotechar = quotechar
        self.strict = strict
        self.stats = CsvReadStats()
        self.fieldnames: list[str] = []
        if not self.path.exists():
            raise FileNotFoundError(f"CSV file not found: {self.path}")

    @property
    def file_size_bytes(self) -> int:
        return self.path.stat().st_size

    def _detect_delimiter(self) -> str:
        if self.delimiter:
            return self.delimiter
        with self.path.open("r", encoding=self.encoding, newline="") as handle:
            sample = handle.read(65536)
        try:
            return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
        except csv.Error:
            return ","

    def _iter_dicts(self) -> Iterator[dict[str, str]]:
        delimiter = self._detect_delimiter()
        with self.path.open("r", encoding=self.encoding, newline="") as handle:
            reader = csv.reader(
                handle,
                delimiter=delimiter,
                quotechar=self.quotechar,
                strict=self.strict,
            )
            try:
                header = next(reader)
            except StopIteration as exc:
                raise ValueError(f"CSV file has no header: {self.path}") from exc
            self.fieldnames = list(header)
            width = len(header)
            while True:
                try:
                    values = next(reader)
                except StopIteration:
                    break
                except csv.Error as error:
                    self.stats.reader_errors += 1
                    self.stats.record_malformed(str(error), reader.line_num)
                    continue
                line_number = reader.line_num
                if not values or all(value.strip() == "" for value in values):
                    self.stats.blank_rows += 1
                    continue
                if len(values) > width:
                    self.stats.extra_field_rows += 1
                    self.stats.record_malformed(
                        f"extra fields: {values[width:]!r}", line_number
                    )
                    continue
                if len(values) < width:
                    missing = header[len(values) :]
                    self.stats.missing_field_rows += 1
                    self.stats.record_malformed(f"missing fields: {missing!r}", line_number)
                    continue
                self.stats.total_rows += 1
                yield dict(zip(header, values, strict=True))

    def iter_rows(self) -> Iterator[dict[str, str]]:
        """Yield one validated row at a time."""
        yield from self._iter_dicts()

    def iter_chunks(self, chunk_size: int | None = None) -> Iterator[list[dict[str, str]]]:
        """Yield validated rows in lists of at most ``chunk_size`` records."""
        size = chunk_size or self.chunk_size
        if size < 1:
            raise ValueError("chunk_size must be at least 1")
        chunk: list[dict[str, str]] = []
        for row in self.iter_rows():
            chunk.append(row)
            if len(chunk) >= size:
                yield chunk
                chunk = []
        if chunk:
            yield chunk

    def close(self) -> None:
        """Compatibility hook. Files are closed by the generators."""

    def __enter__(self) -> IncrementalCsvReader:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()


def read_header(path: str | Path, encoding: str = "utf-8-sig") -> list[str]:
    """Read only the header row."""
    with Path(path).open("r", encoding=encoding, newline="") as handle:
        reader = csv.reader(handle)
        try:
            return next(reader)
        except StopIteration as exc:
            raise ValueError(f"CSV file has no header: {path}") from exc


def iter_csv_rows(
    path: str | Path, chunk_size: int = 1000, delimiter: str | None = None
) -> Iterator[dict[str, str]]:
    """Convenience generator over validated rows."""
    reader = IncrementalCsvReader(path, chunk_size=chunk_size, delimiter=delimiter)
    yield from reader.iter_rows()


def iter_csv_chunks(
    path: str | Path, chunk_size: int = 1000, delimiter: str | None = None
) -> Iterator[Sequence[dict[str, str]]]:
    """Convenience generator over validated chunks."""
    reader = IncrementalCsvReader(path, chunk_size=chunk_size, delimiter=delimiter)
    yield from reader.iter_chunks()
