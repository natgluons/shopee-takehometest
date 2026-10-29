from __future__ import annotations

import json
from pathlib import Path

from receipt_ai.csv_analysis.charts import generate_charts
from receipt_ai.csv_analysis.cli import run


def test_generate_charts(sample_customers_csv: Path, tmp_path: Path) -> None:
    figures = generate_charts(sample_customers_csv, tmp_path / "figures")
    assert "missing_values" in figures
    for path in figures.values():
        assert Path(path).exists()


def test_cli_run_writes_report(sample_customers_csv: Path, tmp_path: Path) -> None:
    report = run(str(sample_customers_csv), str(tmp_path), include_charts=False)
    assert report["quality"]["total_rows"] == 4
    assert report["schema"]["columns"]
    saved = json.loads((tmp_path / "insights.json").read_text(encoding="utf-8"))
    assert saved["statistics"]["row_count"] == 4
