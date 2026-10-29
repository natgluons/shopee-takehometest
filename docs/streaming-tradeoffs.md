# Processing trade-offs: small files, large files, streaming, batching, and splitting

## The short version

For a small file you can afford to load everything, compute, and be done. For a large file you
should stream rows through a fixed amount of state. Splitting a large file into smaller files is a
pragmatic workaround when a downstream tool can only handle small inputs, but it costs extra disk
I/O and it does not by itself guarantee low memory. Streaming is the property that matters. Batching
is a knob on top of streaming that trades memory for fewer per-row calls.

## Small files

A file is "small" when loading it into memory is cheaper than the engineering effort to avoid it.
The 100k customer file is small. It is about 17 MB, and pandas can read it in well under a second.
The analysis pipeline loads it, profiles it, computes statistics, and writes charts. Simplicity wins
and random access is available for grouping, sorting, and plotting.

The risk with small-file code is that it quietly becomes large-file code. A function that assumes
`read_csv` returns the whole frame will fail or swap when someone points it at 2M rows. That is why
this repository keeps the exploratory analysis and the streaming pipeline separate and makes the
boundary explicit.

## Large files

The 2M file is about 349 MB and has 2,000,000 rows. A naive load creates a Python object per row or
a pandas frame with string columns, and peak memory can reach multiple gigabytes. On a laptop that
means swapping or an out-of-memory kill. Even when it fits, the memory is wasted because most
aggregations need counts, sums, and a few group keys, not every row.

The large-file pipeline therefore uses an incremental reader. It opens the file, reads the header,
and yields one row at a time or one bounded batch at a time. The aggregator keeps only running
moments, bounded counters, and a fixed-size Bloom filter. The file size is irrelevant after the
stream is warm.

## Streaming versus splitting

Splitting means copying the file into several smaller files, often partitioned by date, country, or
a hash. Each split can then be processed independently, possibly in parallel. This is useful when:

- the downstream tool requires a file per partition
- you want parallel workers
- you want to retry one partition without reprocessing everything
- the data is naturally partitioned, such as by day

Splitting has real costs:

- it reads the entire input and writes the entire output, so I/O roughly doubles
- it needs free disk space
- too many small files hurt filesystem and object-store performance
- a poor partition key creates skew, where one file is huge and the rest are tiny
- splitting alone does not bound the memory of the consumer. A 200 MB split still needs 200 MB if
  loaded naively.

Streaming means never holding more than a chunk of the file. It is the right default for
aggregation, filtering, validation, and conversion. It does not need extra disk space and memory is
constant. It cannot do arbitrary random access, sorting a whole file, or multi-pass joins without
extra machinery. If you need those, you either use an external sort, a database, or a distributed
engine.

In this repository the partitioned writer is an optional output stage, not the memory strategy.
`stream_and_partition` uses the same incremental reader and writes bounded chunks. The 200k
benchmark shows it at 0.49 MB traced peak because it performs no aggregation. The streaming
aggregator is the low-memory path for analytics.

## Batching

Batching groups rows into lists of a configured size. It reduces Python call overhead and can make
vectorized or bulk operations efficient. The trade-off is direct: a larger batch holds more rows in
memory. In the benchmark, a batch of 1,000 used about 10.8 MB traced peak, a batch of 10,000 used
about 30.1 MB, and a batch of 50,000 used about 116 MB. Choose a batch size that fits the memory
budget and keeps throughput acceptable. Measure instead of guessing.

The reader always emits the final partial batch. Boundary bugs usually appear when a file size is
not a multiple of the batch size, so the tests cover 5 rows with batches of 2.

## Comparing the two source files

| Concern | 100k file | 2M file |
| --- | --- | --- |
| Size | about 17 MB | about 349 MB |
| Strategy | load with pandas | incremental reader plus aggregator |
| Peak memory observed | a few hundred MB including pandas and charts | 58.7 MB RSS for the full streaming run |
| Random access | fine | avoid |
| Charts | direct from frame | aggregate first, chart the summaries |
| Duplicate detection | exact with a set or pandas | approximate with a Bloom filter |
| Output | JSON report and PNG charts | JSON summary and optional partitions |

## Decision guide

1. If the file is small enough that loading it does not threaten the process, load it. Keep the
   code simple.
2. If the file is large or unbounded, stream. Use one pass and bounded state.
3. If a downstream system needs files per partition, stream and split at the same time.
4. If per-row overhead is too high, increase the batch size until memory or latency becomes the
   limit.
5. If you need exact deduplication or a global sort at scale, use an external index or database.
   A fixed-memory approximation is a deliberate trade.
6. Always measure with the real file on the real machine. File size alone is a poor predictor
   because row width, string length, and object overhead matter.

## Why this matters for AI

The same reasoning applies to receipts, embeddings, and model inputs. Streaming a million receipts
through OCR or embedding generation keeps the worker memory flat. Batching controls GPU utilization
and memory. Splitting makes retries and parallel workers possible. The best design usually combines
all three: stream the source, batch for the model, and partition the output for downstream jobs.
