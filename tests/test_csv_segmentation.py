from __future__ import annotations

from pathlib import Path

from receipt_ai.csv_analysis.segmentation import segmentation_report


def test_segmentation_report(sample_customers_csv: Path) -> None:
    report = segmentation_report(sample_customers_csv, reference_date="2022-03-01")
    assert report["row_count"] == 4
    assert report["recency"]["reference_date"] == "2022-03-01"
    assert report["recency"]["segments"]["new_0_90_days"]["count"] == 2
    assert report["recency"]["segments"]["dormant_over_730_days"]["count"] == 1
    assert report["cohort"]["cohorts"]["2020"]["count"] == 1
    assert report["cohort"]["cohorts"]["2021"]["count"] == 1
    assert report["geography"]["segments"]["United Kingdom"]["count"] == 3
    assert report["email_type"]["segments"]["free_email"]["count"] == 0
    assert report["contactability"]["segments"]["email_and_phone"]["count"] == 4
    assert report["contactability"]["segments"]["email_only"]["count"] == 0
