# Benchmarks

## Summary

| Workload | Data | Result | Where |
| --- | --- | --- | --- |
| 100k customer analysis | 100,000 rows, 17 MB | about 2.6 s wall time, 12 columns | `docs/csv-insights.md` |
| Full 2M streaming aggregation | 2,000,000 rows, 349 MB | 17.57 s wall time, 58.7 MB maximum RSS | `docs/benchmark-results.md` |
| 200k strategy comparison | 200,000 rows | naive 223.78 MB traced peak vs 10.81 MB streaming (batch 1,000) | `docs/benchmark-results.md` |
| OCR extraction | 900x500 PNG receipt | about 0.11 s in the container | container smoke run |
| Test suite | 102 tests | all passing locally | `pytest -q` |
| Container smoke test | image | health, readiness, volume persistence passed | `scripts/verify_docker.sh` |

The 200k comparison times in the JSON include `tracemalloc` tracing, which dominates CPU for this
per-row workload. Use the untraced full-file number for throughput and the traced numbers for
relative memory comparison.

## Why the streaming result is bounded

The full 2M run uses:

- a chunk size of 10,000 rows
- a 4 MiB Bloom filter for approximate identifier duplicates
- bounded categorical counters capped at 50,000 keys
- one pass over the file

Peak RSS was 58.7 MB. The same process at 200,000 rows with batch 10,000 showed a 30.11 MB traced
peak, so memory is driven by configured state and batch size, not by row count after steady state.

## Why naive loading is disqualified at this size

The naive strategy materializes every selected row as a Python dictionary, then aggregates.
At 200,000 rows it already peaked at 223.78 MB. Extrapolating linearly to 2,000,000 rows gives a
multi-gigabyte peak, which is inappropriate for a laptop or a small container. The streaming
pipeline is the default for the 2M file.

## Partitioned splitting is not a memory strategy by itself

The partitioned writer measured 0.49 MB traced peak at 200k because it does not aggregate and writes
each row immediately. It is useful when downstream tools need files per partition, but it still
reads and writes the whole dataset. Streaming remains the property that keeps memory flat.

## Reproducing

```bash
python3 -m receipt_ai.csv_analysis.cli --input customers-100000.csv --outdir reports
python3 -m receipt_ai.streaming.cli --input customers-2000000.csv \
  --batch-size 10000 --outdir reports
python3 -m receipt_ai.streaming.cli --input customers-2000000.csv \
  --benchmark --limit 200000 --outdir reports
pytest -q
bash scripts/verify_docker.sh
```

The 2M and 100k files are intentionally not committed. Place them in the repository root before
running the dataset commands.

## Measurement caveats

- Results are from one Apple silicon macOS machine and one Python 3.13.5 interpreter. Absolute
  numbers will vary.
- `tracemalloc` measures Python allocations, not native memory. RSS includes the interpreter,
  libraries, and SQLite.
- The process RSS high-water mark is not reset between benchmark strategies, so the table in
  `docs/benchmark-results.md` uses traced peak for comparison.
- OCR timing excludes upload transfer and image preprocessing in the browser, and depends on image
  quality, resolution, and Tesseract version.
- The 200k benchmark is a prefix, not the full file. It exists so the naive strategy can be measured
  without risking the machine.
