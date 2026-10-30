"""Command line entry point for streaming reports and benchmarks."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from receipt_ai.streaming.aggregations import AggregationConfig, aggregate_csv
from receipt_ai.streaming.benchmark import run_benchmark

PARTITION_CHOICES = ("year", "country")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Stream the large customer CSV")
    parser.add_argument("--input", required=True, help="Path to the customer CSV")
    parser.add_argument("--batch-size", type=int, default=10_000)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument(
        "--categories",
        default="Country",
        help="Comma separated low-cardinality columns to aggregate",
    )
    parser.add_argument("--outdir", default="reports")
    parser.add_argument("--benchmark", action="store_true", help="Run the comparison harness")
    parser.add_argument(
        "--limit",
        type=int,
        default=200_000,
        help="Rows to process in benchmark mode. Use 0 for the full file.",
    )
    parser.add_argument(
        "--batch-sizes",
        default="1000,10000,50000",
        help="Comma separated batch sizes for benchmark mode",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    if args.benchmark:
        limit = None if args.limit == 0 else args.limit
        batch_sizes = tuple(int(value) for value in args.batch_sizes.split(",") if value)
        report = run_benchmark(args.input, limit=limit, batch_sizes=batch_sizes)
        path = outdir / "streaming-benchmark.json"
        path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({"report": str(path), "results": report["results"]}, indent=2))
        return 0

    categories = tuple(name.strip() for name in args.categories.split(",") if name.strip())
    config = AggregationConfig(top_n=args.top_n, categorical_columns=categories)
    summary = aggregate_csv(args.input, batch_size=args.batch_size, config=config)
    path = outdir / "streaming-summary.json"
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "rows": summary["rows"],
                "batch_size": summary["batch_size"],
                "reader": summary["reader"],
                "top_countries": summary["categorical"]["Country"]["top"],
                "identifiers": summary["identifiers"],
                "report": str(path),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
