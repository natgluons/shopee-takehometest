"""Schema inspection for CSV files using only the standard library.

The 100k file is small enough for pandas, but schema inspection is also useful before deciding
whether a file can be loaded safely. This module samples rows, infers logical column types, and
reports basic shape information without requiring the caller to know the dialect up front.
"""

from __future__ import annotations

import csv
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
URL_RE = re.compile(r"^https?://[^\s]+$", re.IGNORECASE)
DATE_RE = re.compile(
    r"^(?:\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|"
    r"\d{4}/\d{2}/\d{2}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4})$",
    re.IGNORECASE,
)
INT_RE = re.compile(r"^-?\d+$")
FLOAT_RE = re.compile(r"^-?\d+[.,]\d+$")
PHONE_RE = re.compile(r"^\+?[\d\s().-]{7,}(?:\s*(?:x|ext\.?)\s*\d+)?$", re.IGNORECASE)


@dataclass(frozen=True)
class ColumnProfile:
    """Inferred profile for one column in a sample."""

    name: str
    inferred_type: str
    non_null: int
    sampled: int
    distinct: int
    examples: tuple[str, ...] = field(default_factory=tuple)

    @property
    def null_count(self) -> int:
        return self.sampled - self.non_null

    @property
    def null_ratio(self) -> float:
        return round(self.null_count / self.sampled, 6) if self.sampled else 0.0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["examples"] = list(self.examples)
        payload["null_count"] = self.null_count
        payload["null_ratio"] = self.null_ratio
        return payload


@dataclass(frozen=True)
class DatasetSchema:
    """Dialect, shape, and column profiles for a CSV file."""

    path: str
    delimiter: str
    quotechar: str
    encoding: str
    sample_rows: int
    total_rows: int | None
    columns: tuple[ColumnProfile, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "delimiter": self.delimiter,
            "quotechar": self.quotechar,
            "encoding": self.encoding,
            "sample_rows": self.sample_rows,
            "total_rows": self.total_rows,
            "columns": [column.to_dict() for column in self.columns],
        }


def detect_dialect(path: str | Path, sample_size: int = 65536) -> tuple[str, str, str]:
    """Return delimiter, quote character, and encoding for a CSV file."""
    path = Path(path)
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        sample = handle.read(sample_size)
    if not sample:
        raise ValueError(f"CSV file is empty: {path}")
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        return dialect.delimiter, dialect.quotechar or '"', "utf-8-sig"
    except csv.Error:
        return ",", '"', "utf-8-sig"


def infer_value_type(value: str) -> str:
    """Infer a logical type for a single non-empty string value."""
    text = value.strip()
    if not text:
        return "empty"
    if EMAIL_RE.match(text):
        return "email"
    if URL_RE.match(text):
        return "url"
    if DATE_RE.match(text):
        return "date"
    if INT_RE.match(text):
        return "integer"
    if FLOAT_RE.match(text):
        return "float"
    if PHONE_RE.match(text) and any(character.isdigit() for character in text):
        return "phone"
    return "text"


def _infer_column_type(values: list[str], name: str = "") -> str:
    if "phone" in name.lower():
        non_empty = [value.strip() for value in values if value.strip()]
        if non_empty and all(PHONE_RE.match(value) for value in non_empty):
            return "phone"
    types = [infer_value_type(value) for value in values if value.strip()]
    if not types:
        return "empty"
    unique = set(types)
    if len(unique) == 1:
        return unique.pop()
    if unique <= {"integer", "float"}:
        return "number"
    return "mixed"


def _sample_rows(
    path: Path, delimiter: str, quotechar: str, encoding: str, sample_size: int
) -> tuple[list[str], list[list[str]]]:
    with path.open("r", encoding=encoding, newline="") as handle:
        reader = csv.reader(handle, delimiter=delimiter, quotechar=quotechar)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(f"CSV file has no header: {path}") from exc
        rows: list[list[str]] = []
        for row in reader:
            if not any(cell.strip() for cell in row):
                continue
            rows.append(row)
            if len(rows) >= sample_size:
                break
    return header, rows


def count_rows(
    path: str | Path, delimiter: str = ",", quotechar: str = '"', encoding: str = "utf-8-sig"
) -> int:
    """Count data rows while streaming, so memory stays constant."""
    total = 0
    with Path(path).open("r", encoding=encoding, newline="") as handle:
        reader = csv.reader(handle, delimiter=delimiter, quotechar=quotechar)
        next(reader, None)
        for row in reader:
            if any(cell.strip() for cell in row):
                total += 1
    return total


def inspect_schema(
    path: str | Path,
    sample_size: int = 1000,
    count_total: bool = True,
    max_examples: int = 3,
) -> DatasetSchema:
    """Inspect a CSV file and infer a profile for each column."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")
    delimiter, quotechar, encoding = detect_dialect(path)
    header, rows = _sample_rows(path, delimiter, quotechar, encoding, sample_size)
    column_count = len(header)
    normalized_rows = [row + [""] * (column_count - len(row)) for row in rows]
    profiles: list[ColumnProfile] = []
    for index, name in enumerate(header):
        values = [row[index] for row in normalized_rows if index < len(row)]
        non_empty = [value.strip() for value in values if value.strip()]
        distinct = len(set(non_empty))
        examples = tuple(dict.fromkeys(non_empty))[:max_examples]
        profiles.append(
            ColumnProfile(
                name=name,
                inferred_type=_infer_column_type(values, name),
                non_null=len(non_empty),
                sampled=len(values),
                distinct=distinct,
                examples=examples,
            )
        )
    total = count_rows(path, delimiter, quotechar, encoding) if count_total else None
    return DatasetSchema(
        path=str(path),
        delimiter=delimiter,
        quotechar=quotechar,
        encoding=encoding,
        sample_rows=len(rows),
        total_rows=total,
        columns=tuple(profiles),
    )
