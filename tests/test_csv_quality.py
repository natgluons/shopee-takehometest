from __future__ import annotations

from pathlib import Path

from receipt_ai.csv_analysis.quality import profile_quality


def test_profile_quality_reports_defects(sample_customers_csv: Path) -> None:
    report = profile_quality(sample_customers_csv)
    assert report["total_rows"] == 4
    assert report["exact_duplicate_rows"] == 0
    assert report["customer_ids"]["duplicate_extra_rows"] == 1
    assert report["customer_ids"]["duplicate_rows"] == 2
    assert report["column_quality"]["Phone 2"]["null_count"] == 3
    assert report["email"]["invalid_count"] == 0


def test_profile_quality_catches_invalid_values(tmp_path: Path) -> None:
    path = tmp_path / "customers.csv"
    path.write_text(
        "Index,Customer Id,First Name,Last Name,Company,City,Country,Phone 1,Phone 2,"
        "Email,Subscription Date,Website\n"
        "1,ABC001, Ada ,Lovelace,Analytical Engines,London,United Kingdom,111-1111,,"
        "not-an-email,2020-13-40,https://example.com\n",
        encoding="utf-8",
    )
    report = profile_quality(path)
    assert report["email"]["invalid_count"] == 1
    assert report["subscription_date"]["invalid_count"] == 1
    assert report["column_quality"]["First Name"]["whitespace_issue_count"] == 1
    assert report["phone_2"]["invalid_count"] == 0
