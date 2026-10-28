# Receipt AI

A self-contained receipt intelligence platform. It accepts food receipt images, extracts the
merchant, date, line items, and totals with a local OCR engine, stores the structured result in
SQLite, indexes a searchable vector representation, and answers natural-language questions about
food spending.

The repository also contains the two data-engineering workstreams required by the take-home task:

- a reproducible exploratory analysis of `customers-100000.csv`
- a bounded-memory streaming pipeline for `customers-2000000.csv`
- a small self-hosted vector database with a pure Python cosine similarity implementation

## Requirements

- Python 3.11 or newer
- Tesseract OCR for real image extraction (`brew install tesseract` on macOS,
  `apt-get install tesseract-ocr` on Debian/Ubuntu)
- Docker only for the container workflow

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,analysis]"
uvicorn receipt_ai.api.main:app --reload
```

Open <http://localhost:8000>. The upload page accepts a receipt image, shows the extracted fields
for review, and saves the confirmed receipt. The history page shows spending summaries and the
query page answers natural-language questions with the evidence rows used to build the answer.

## Common commands

```bash
make lint            # ruff static analysis
make format-check    # ruff formatting check
make test            # unit and integration tests
make cov             # tests with coverage
make analyze         # analyze the 100k customer file into reports/
make stream          # stream the 2M customer file
make benchmark       # compare processing strategies
make docker-build    # build the application image
make docker-up       # start the app with persistent data
```

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `RECEIPT_AI_DATA_DIR` | `data` | Root for the database, vector store, uploads, and reports |
| `RECEIPT_AI_DB_PATH` | `data/receipts.db` | Receipt SQLite database |
| `RECEIPT_AI_VECTOR_DB_PATH` | `data/vectors.db` | Self-hosted vector database |
| `RECEIPT_AI_UPLOAD_DIR` | `data/uploads` | Stored receipt images |
| `RECEIPT_AI_MAX_UPLOAD_BYTES` | `10485760` | Maximum accepted upload size |
| `RECEIPT_AI_OCR_LANG` | `eng` | Tesseract language pack |
| `RECEIPT_AI_TESSERACT_CMD` | `tesseract` | Tesseract executable |
| `OPENAI_API_KEY` | unset | Enables optional LLM tool calling |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible endpoint |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model used for tool calling |

The application works without an API key. The natural-language router falls back to a deterministic
intent parser that calls the same tools the LLM would call, so the demo and tests are fully local.

## Layout

```
src/receipt_ai/
  csv_analysis/   schema inspection, quality profiling, statistics, segmentation, charts
  streaming/      incremental reader, aggregations, batching, partitioned writer, benchmarks
  vector/         validation, pure Python cosine similarity, SQLite store, top-k search
  db/             receipt schema and repository
  ocr/            local OCR engine, preprocessing, extraction, normalization, validation
  services/       upload and review workflow, analytics, natural-language query
  tools/          tool schemas and dispatch for the LLM
  api/            FastAPI routes and dependency wiring
  ui/             Jinja templates and static assets
scripts/          command line entry points and demo helpers
docs/             design notes, acceptance criteria, benchmark evidence, and explanations
tests/            unit, integration, and container smoke tests
```

## Documentation

Start with [docs/acceptance-criteria.md](docs/acceptance-criteria.md) and
[docs/assumptions.md](docs/assumptions.md). The engineering knowledge answers live in
[docs/rest-vs-mcp.md](docs/rest-vs-mcp.md) and the related pages. Dataset findings are recorded in
[docs/csv-insights.md](docs/csv-insights.md), and streaming trade-offs in
[docs/streaming-tradeoffs.md](docs/streaming-tradeoffs.md).

## License

MIT
