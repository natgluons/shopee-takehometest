from __future__ import annotations

from pathlib import Path

from receipt_ai.csv_analysis.schema import count_rows, infer_value_type, inspect_schema


def test_infer_value_type() -> None:
    assert infer_value_type("42") == "integer"
    assert infer_value_type("42.50") == "float"
    assert infer_value_type("ada@example.com") == "email"
    assert infer_value_type("https://example.com") == "url"
    assert infer_value_type("2024-06-20") == "date"
    assert infer_value_type("+1-555-0100") == "phone"
    assert infer_value_type("Green Bowl") == "text"
    assert infer_value_type("   ") == "empty"


def test_inspect_schema(sample_customers_csv: Path) -> None:
    schema = inspect_schema(sample_customers_csv)
    assert schema.total_rows == 4
    assert schema.delimiter == ","
    columns = {column.name: column for column in schema.columns}
    assert columns["Index"].inferred_type == "integer"
    assert columns["Email"].inferred_type == "email"
    assert columns["Subscription Date"].inferred_type == "date"
    assert columns["Website"].inferred_type == "url"
    assert columns["Phone 2"].null_count == 3


def test_count_rows_ignores_blank_lines(sample_customers_csv: Path) -> None:
    with sample_customers_csv.open("a", encoding="utf-8") as handle:
        handle.write("\n\n")
    assert count_rows(sample_customers_csv) == 4
