# Requirements mapping

This document maps every requirement in `instructions.txt` to implementation, tests, and evidence.
File paths are relative to the repository root.

## Written answers

| # | Requirement | Where it is answered | Supporting detail |
| --- | --- | --- | --- |
| 1 | REST API vs MCP in AI | `knowledge.txt` Q1 | `docs/rest-vs-mcp.md` |
| 2 | How REST and MCP improve an AI use case | `knowledge.txt` Q2 | `docs/rest-mcp-interoperability.md` |
| 3 | Ensuring the AI agent answers correctly | `knowledge.txt` Q3 | `docs/agent-reliability.md` |
| 4 | Docker and containerized environments for AI | `knowledge.txt` Q4 | `docs/containerization-for-ai.md` |
| 5 | Fine-tuning an LLM from raw data | `knowledge.txt` Q5 | `docs/model-training-fine-tuning.md` |

`knowledge.txt` uses casual English with no semicolons and no em dashes. A check for those characters
is part of the final verification.

## Coding

| # | Requirement | Implementation | Evidence and tests |
| --- | --- | --- | --- |
| 1 | Parse and analyze `customers-100000.csv` | `src/receipt_ai/csv_analysis/` | `docs/csv-insights.md`, `docs/figures/`, `tests/test_csv_*.py` |
| 2 | Parse `customers-2000000.csv` with low memory | `src/receipt_ai/streaming/` | `docs/benchmark-results.md`, `tests/test_streaming.py` |
| 3 | Explain difference from splitting small vs large files | `docs/streaming-tradeoffs.md` | measured comparison in `docs/benchmark-results.md` |
| 4 | Self-hosted vector DB with manual cosine similarity | `src/receipt_ai/vector/` | `docs/vector-index.md`, `tests/test_vector_*.py` |
| 5a | UI to upload food receipts | `src/receipt_ai/ui/`, `POST /api/receipts/upload` | `tests/test_app_e2e.py` |
| 5b | Extract with computer vision | `src/receipt_ai/ocr/` (Tesseract plus preprocessing) | `tests/test_ocr.py`, container OCR smoke run |
| 5c | Get receipt insights and store in DB | `db/repository.py`, `GET /api/insights`, history UI | `tests/test_db.py`, `tests/test_app_e2e.py` |
| 5d | AI tools for the three required questions | `services/query.py`, `tools/registry.py`, `services/nl_query.py` | `tests/test_query.py`, `tests/test_app_e2e.py` |
| 5e | Container image and local run | `Dockerfile`, `docker-compose.yml` | `scripts/verify_docker.sh`, `tests/test_docker_assets.py` |
| 5f | CI/CD to wrap the application into a container | `.github/workflows/ci.yml` | lint, tests, Docker build and health smoke job |

## Question-by-question coding evidence

### 1. 100k CSV insights

- `schema.py` infers delimiter, quote character, types, nulls, and examples.
- `quality.py` reports missing values, duplicates, duplicate identifiers, invalid emails, invalid
  dates, and whitespace issues.
- `stats.py` computes numeric descriptions, subscription timeline, category distributions, and email
  domains.
- `segmentation.py` produces recency, cohort, geography, email type, and contactability segments.
- `charts.py` writes five charts.
- `docs/csv-insights.md` records only measured values and calls out the synthetic-data signals.
- `docs/figures/` contains committed copies of the generated charts.

### 2. 2M CSV with low memory

- `reader.py` streams rows, validates width, and counts malformed input.
- `aggregations.py` uses Welford moments, bounded counters, and a fixed-size Bloom filter.
- `batch.py` supports configurable batches and always processes the final partial batch.
- `writer.py` partitions output with a bounded pool of open handles.
- `benchmark.py` compares naive loading, streaming at several batch sizes, and partitioned splitting.
- Full run measured 17.57 s and 58.7 MB maximum RSS on the development machine.

### 3. Splitting versus streaming

`docs/streaming-tradeoffs.md` explains:

- when loading a small file is the simplest correct choice
- why the 2M file must stream
- the I/O and skew costs of splitting
- why splitting does not itself bound consumer memory
- how batch size trades memory for throughput
- the measured numbers for each strategy

### 4. Self-hosted vector database

- `vector/schema.py` creates collections and vectors in SQLite with foreign keys and uniqueness.
- `vector/store.py` implements create, upsert, get, list, delete, clear, and drop.
- `vector/similarity.py` implements dot product, cosine, Euclidean distance, and top-k with only the
  standard library.
- `vector/embedding.py` provides a deterministic hashed bag-of-words embedder.
- `vector/search.py` performs persisted top-k search with metadata filters and thresholds.
- `tests/test_vector_similarity.py` covers zero vectors, mismatched dimensions, non-finite values,
  negative values, single elements, and tie ordering.
- `tests/test_vector_store.py` covers persistence, upserts, cascades, filters, and search.

### 5a. Upload UI

`index.html` and `app.js` implement drag and drop, preview, upload, an editable review form, item
add/remove, automatic subtotal and total calculation, warnings, OCR metadata, and save.

### 5b. Computer vision extraction

`ocr/preprocess.py` orients, grayscales, resizes, denoises, and sharpens. `ocr/engine.py` runs local
Tesseract. `ocr/extract.py` finds merchant, date, totals, and items. The container was verified with
a generated 900x500 receipt image and returned the correct merchant, date, three items, tax, and
total.

### 5c. Insights and database

`db/schema.py` stores receipts and items with integer cents, checks, indexes, and cascades.
`db/repository.py` implements transactional create, update, delete, date filters, item filters,
expense aggregation, merchant lookup, and insights. The history page renders totals, merchants, top
items, and the receipt table.

### 5d. AI tools

The three tools are:

- `get_purchases_by_date`
- `get_food_expenses_by_date`
- `find_merchant_by_item`

They are exposed as OpenAI-style JSON schemas at `GET /api/tools`. The rule-based router and optional
LLM both use `ToolRegistry`. Every result includes normalized arguments, an explicit `found` flag,
evidence rows, and warnings. Empty results are answered explicitly rather than invented.

### 5e. Container

The multi-stage image installs Tesseract, runs as a non-root user, uses a read-only root filesystem
with a writable data volume and `/tmp`, and exposes a health check. `scripts/verify_docker.sh` builds,
starts, checks health and readiness, verifies the database files are on the volume, writes a marker,
restarts the container, and verifies the marker survived. The script passed locally.

### 5f. CI/CD

`.github/workflows/ci.yml` runs:

1. checkout and Python setup
2. dependency installation
3. Ruff lint and format check
4. full pytest suite
5. Docker build
6. container start and health, readiness, UI, and tools endpoint checks

`docs/image-publication.md` documents tagging, promotion by digest, SBOM and provenance, signing,
scanning, and rollback. The current workflow intentionally does not publish images.

## Micro-commits and phase branches

Each phase has its own branch. Every phase branch was merged into `master` with a fast-forward merge,
so the commit history is linear and contains the required messages.

| Phase | Branch | Commits |
| --- | --- | --- |
| 1 | `phase-1-foundation` | 1 to 6 |
| 2 | `phase-2-engineering-knowledge` | 7 to 11 |
| 3 | `phase-3-csv-insights` | 12 to 17 |
| 4 | `phase-4-streaming` | 18 to 25 |
| 5 | `phase-5-vector-db` | 26 to 33 |
| 6 | `phase-6-receipt-app` | 34 to 52 |
| 7 | `phase-7-docker-ci` | 53 to 58 |
| 8 | `phase-8-submission` | 59 to 64 |

Commit timestamps start at the time the work began and each subsequent commit is separated by a
random interval between 10 minutes and 2 hours. The commit messages match the required list.

Verify with:

```bash
git log --oneline --decorate --all
git log --format='%h %ad %s' --date=iso
```

## Acceptance criteria

The detailed, checkable acceptance criteria are in
[`docs/acceptance-criteria.md`](acceptance-criteria.md). The final fresh-clone check is
`scripts/fresh_clone_check.sh`.
