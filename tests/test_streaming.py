from __future__ import annotations

import csv
from pathlib import Path

import pytest

from receipt_ai.streaming.aggregations import (
    AggregationConfig,
    BloomFilter,
    NumericStats,
    StreamingAggregator,
    aggregate_csv,
)
from receipt_ai.streaming.batch import chunked, process_csv_in_batches, process_in_batches
from receipt_ai.streaming.reader import IncrementalCsvReader
from receipt_ai.streaming.writer import (
    partition_by_date_year,
    partition_by_field,
    stream_and_partition,
)

HEADER = "Index,Customer Id,Country,Email,Subscription Date\n"


def write_csv(path: Path, rows: list[str]) -> Path:
    path.write_text(HEADER + "\n".join(rows) + "\n", encoding="utf-8")
    return path


@pytest.fixture()
def clean_csv(tmp_path: Path) -> Path:
    rows = [
        "1,C001,United Kingdom,ada@example.com,2020-01-15",
        "2,C002,United States,grace@navy.mil,2021-06-20",
        "3,C003,United Kingdom,alan@example.org,2022-03-01",
        "4,C003,United Kingdom,alan@example.org,2022-03-01",
        "5,C004,France,jean@example.fr,2022-04-02",
    ]
    return write_csv(tmp_path / "clean.csv", rows)


@pytest.fixture()
def malformed_csv(tmp_path: Path) -> Path:
    rows = [
        "1,C001,United Kingdom,ada@example.com,2020-01-15",
        "",
        "2,C002,United States,grace@navy.mil",
        "3,C003,France,alan@example.org,2022-03-01,EXTRA",
        "4,C004,France,jean@example.fr,2022-04-02",
    ]
    return write_csv(tmp_path / "malformed.csv", rows)


def test_reader_chunks_incrementally(clean_csv: Path) -> None:
    reader = IncrementalCsvReader(clean_csv, chunk_size=2)
    chunks = list(reader.iter_chunks())
    assert [len(chunk) for chunk in chunks] == [2, 2, 1]
    assert reader.stats.total_rows == 5
    assert reader.stats.malformed_rows == 0


def test_reader_counts_malformed_rows(malformed_csv: Path) -> None:
    reader = IncrementalCsvReader(malformed_csv, chunk_size=10)
    rows = list(reader.iter_rows())
    assert len(rows) == 2
    assert reader.stats.total_rows == 2
    assert reader.stats.blank_rows == 1
    assert reader.stats.missing_field_rows == 1
    assert reader.stats.extra_field_rows == 1
    assert reader.stats.malformed_rows == 2
    assert len(reader.stats.malformed_examples) == 2


def test_reader_rejects_invalid_chunk_size(clean_csv: Path) -> None:
    with pytest.raises(ValueError):
        IncrementalCsvReader(clean_csv, chunk_size=0)


def test_numeric_stats_is_stable() -> None:
    stats = NumericStats()
    for value in (1.0, 2.0, 3.0, 4.0):
        stats.add(value)
    assert stats.count == 4
    assert stats.mean == 2.5
    assert stats.minimum == 1.0
    assert stats.maximum == 4.0
    assert round(stats.std, 6) == 1.290994


def test_bloom_filter_detects_probable_duplicate() -> None:
    bloom = BloomFilter(bits=1 << 16)
    assert bloom.check_and_add("customer-1") is False
    assert bloom.check_and_add("customer-1") is True
    assert bloom.probable_duplicates == 1


def test_streaming_aggregator(clean_csv: Path) -> None:
    reader = IncrementalCsvReader(clean_csv, chunk_size=2)
    aggregator = StreamingAggregator(
        AggregationConfig(
            numeric_columns=("Index",),
            categorical_columns=("Country",),
            bloom_bits=1 << 16,
        )
    )
    aggregator.add_rows(reader.iter_rows())
    summary = aggregator.summary()
    assert summary["rows"] == 5
    assert summary["numeric"]["Index"]["mean"] == 3.0
    assert summary["categorical"]["Country"]["top"]["United Kingdom"] == 3
    assert summary["dates"]["min"] == "2020-01-15"
    assert summary["dates"]["max"] == "2022-04-02"
    assert summary["identifiers"]["probable_duplicates"] == 1


def test_aggregate_csv_includes_reader_stats(clean_csv: Path) -> None:
    summary = aggregate_csv(clean_csv, batch_size=2)
    assert summary["rows"] == 5
    assert summary["reader"]["total_rows"] == 5
    assert summary["batch_size"] == 2


def test_batch_boundaries() -> None:
    assert [len(batch) for batch in chunked(range(5), 2)] == [2, 2, 1]
    assert [len(batch) for batch in chunked(range(4), 2)] == [2, 2]
    with pytest.raises(ValueError):
        list(chunked(range(3), 0))


def test_process_in_batches_partial_final_batch() -> None:
    seen: list[int] = []

    def handler(batch: list[int]) -> int:
        seen.append(len(batch))
        return sum(batch)

    result = process_in_batches(range(5), 2, handler)
    assert seen == [2, 2, 1]
    assert result.batch_count == 3
    assert result.row_count == 5
    assert result.results == [1, 5, 4]


def test_process_csv_in_batches_counts_batches(clean_csv: Path) -> None:
    summary = process_csv_in_batches(clean_csv, batch_size=2)
    assert summary["processing"]["batch_count"] == 3
    assert summary["processing"]["batch_size"] == 2


def test_partitioned_writer_splits_by_year(clean_csv: Path, tmp_path: Path) -> None:
    result = stream_and_partition(
        clean_csv,
        tmp_path / "partitioned",
        partition_by_date_year(),
        max_rows_per_file=1,
        batch_size=2,
    )
    manifest = result["manifest"]
    assert manifest["total_rows"] == 5
    assert set(manifest["partitions"]) == {"2020", "2021", "2022"}
    for partition, record in manifest["partitions"].items():
        expected = {"2020": 1, "2021": 1, "2022": 3}[partition]
        assert record["rows"] == expected
        assert len(record["files"]) == expected
        total = 0
        for file_name in record["files"]:
            with Path(file_name).open(encoding="utf-8", newline="") as handle:
                total += sum(1 for _ in csv.DictReader(handle))
        assert total == expected


def test_partitioned_writer_handles_high_cardinality(
    clean_csv: Path, tmp_path: Path
) -> None:
    result = stream_and_partition(
        clean_csv,
        tmp_path / "partitioned",
        partition_by_field("Customer Id"),
        max_open_files=2,
        batch_size=2,
    )
    assert result["manifest"]["partition_count"] == 4
    assert result["manifest"]["total_rows"] == 5
