# Streaming benchmark results

## Environment

| Item | Value |
| --- | --- |
| Machine | Apple silicon, macOS 27.0 arm64 |
| Python | 3.13.5 |
| Input file | `customers-2000000.csv`, 349,416,788 bytes |
| Rows | 2,000,000 |
| Columns | 12 |

Published numbers are local measurements. They are included so a reviewer can compare relative
behavior, not so they can be treated as universal constants.

## Full-file streaming run

Command:

```bash
/usr/bin/time -l python3 -m receipt_ai.streaming.cli \
  --input customers-2000000.csv --batch-size 10000 --outdir reports
```

| Metric | Value |
| --- | --- |
| Rows processed | 2,000,000 |
| Wall time | 17.57 s |
| Throughput | about 113,800 rows/s |
| Maximum resident set size | 58.7 MB |
| Peak memory footprint | 50.8 MB |
| Malformed rows | 0 |
| Blank rows | 0 |
| Reader errors | 0 |
| Countries observed | 243 |
| Identifiers observed | 2,000,000 |
| Probable duplicate identifiers | 861 (Bloom estimate, 0.2% false positive rate) |
| Date range | 2020-01-01 to 2022-05-30 |

The Bloom filter is 4 MiB and the categorical counters are capped at 50,000 keys. The top results
are therefore exact for observed keys and the counters report how many observations were dropped
when the cap is reached. The memory number is bounded by the configured state, not by the file size.

## Strategy comparison at 200,000 rows

The harness is run on a 200,000 row prefix so the naive strategy can be measured on the development
machine without exhausting memory. All strategies process the same prefix.

```bash
python3 -m receipt_ai.streaming.cli \
  --input customers-2000000.csv --benchmark --limit 200000 --outdir reports
```

| Strategy | Traced peak | Relative memory |
| --- | --- | --- |
| Naive load into a list | 223.78 MB | 20.7 times the smallest streaming run |
| Streaming, batch 1,000 | 10.81 MB | 1.0 |
| Streaming, batch 10,000 | 30.11 MB | 2.8 |
| Streaming, batch 50,000 | 115.98 MB | 10.7 |
| Partitioned split | 0.49 MB | 0.05 |

All measured times include `tracemalloc` tracing, which dominates CPU for this per-row workload.
Traced times clustered around 14 to 20 seconds for the 200,000 row prefix and are useful only for
relative comparison inside the harness. The untraced full-file run above is the throughput number to
cite.

## Interpretation

- The naive strategy grows with the file. At 200,000 rows it already allocates more than 220 MB, and
  a full 2M load would be roughly ten times larger.
- Streaming memory is set by batch size, the Bloom filter, and the category caps. It does not grow
  with the number of rows after steady state.
- Larger batches reduce per-row overhead but increase peak memory. A batch of 50,000 is more than
  ten times heavier than a batch of 1,000 for a modest throughput difference under tracing.
- The partitioned writer is the lightest strategy because it never aggregates. It trades CPU for
  disk and produces files that downstream jobs can process independently.
- The 861 probable duplicates in the full run are mostly Bloom false positives. The filter is
  intentionally approximate to keep memory fixed. Exact duplicate detection requires a disk-backed
  index or a sort step.

## Reproducing

```bash
pip install -e ".[dev,analysis]"
python3 -m receipt_ai.streaming.cli \
  --input customers-2000000.csv --batch-size 10000 --outdir reports
python3 -m receipt_ai.streaming.cli \
  --input customers-2000000.csv --benchmark --limit 200000 --outdir reports
```

The JSON artifacts are written to `reports/streaming-summary.json` and
`reports/streaming-benchmark.json`. The `reports/` directory is intentionally ignored by git because
it contains generated output. This document records the results from a run.
