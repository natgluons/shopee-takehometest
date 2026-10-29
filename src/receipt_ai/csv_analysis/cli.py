"""Command line entry point for the 100k customer analysis."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from receipt_ai.csv_analysis.charts import generate_charts
from receipt_ai.csv_analysis.quality import profile_quality
from receipt_ai.csv_analysis.schema import inspect_schema
from receipt_ai.csv_analysis.segmentation import segmentation_report
from receipt_ai.csv_analysis.stats import describe_dataset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Analyze the 100k customer CSV")
    parser.add_argument("--input", required=True, help="Path to the customer CSV")
    parser.add_argument("--outdir", default="reports", help="Directory for JSON and charts")
    parser.add_argument("--no-charts", action="store_true", help="Skip chart generation")
    parser.add_argument(
        "--sample-size",
        type=int,
        default=2000,
        help="Rows sampled for schema inference",
    )
    return parser


def run(input_path: str, outdir: str, include_charts: bool = True, sample_size: int = 2000) -> dict:
    output = Path(outdir)
    output.mkdir(parents=True, exist_ok=True)
    figures = output / "figures"

    report = {
        "schema": inspect_schema(input_path, sample_size=sample_size).to_dict(),
        "quality": profile_quality(input_path),
        "statistics": describe_dataset(input_path),
        "segmentation": segmentation_report(input_path),
    }
    if include_charts:
        report["figures"] = generate_charts(input_path, figures)

    report_path = output / "insights.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = run(args.input, args.outdir, not args.no_charts, args.sample_size)
    print(
        json.dumps(
            {
                "input": args.input,
                "rows": report["quality"]["total_rows"],
                "columns": report["quality"]["total_columns"],
                "duplicate_customer_ids": report["quality"]
                .get("customer_ids", {})
                .get("duplicate_extra_rows", 0),
                "countries": report["statistics"]["categorical"]
                .get("Country", {})
                .get("distinct", 0),
                "report": str(Path(args.outdir) / "insights.json"),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
