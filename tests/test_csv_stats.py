from __future__ import annotations

from pathlib import Path

import pandas as pd

from receipt_ai.csv_analysis.stats import describe_dataset, describe_numeric


def test_describe_numeric() -> None:
    frame = pd.DataFrame({"Index": ["1", "2", "3", "not-a-number"]})
    result = describe_numeric(frame)
    assert result["Index"]["count"] == 3
    assert result["Index"]["mean"] == 2.0
    assert result["Index"]["sum"] == 6.0


def test_describe_dataset(sample_customers_csv: Path) -> None:
    report = describe_dataset(sample_customers_csv)
    assert report["row_count"] == 4
    assert report["numeric"]["Index"]["max"] == 4.0
    assert report["subscription_timeline"]["min_date"] == "2020-01-15"
    assert report["subscription_timeline"]["max_date"] == "2022-03-01"
    assert report["categorical"]["Country"]["top"]["United Kingdom"] == 3
    assert report["email_domains"]["top"]["example.org"] == 2
