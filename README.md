# Receipt AI

A self-contained receipt intelligence platform and the accompanying data-engineering work for the
Shopee take-home exercise.

Upload a photo of a food receipt. Local Tesseract extracts the text. A deterministic parser
normalizes the merchant, date, line items, tax, and total. You review and correct the result, then
save it to SQLite. Saved receipts are indexed in a self-hosted vector database and exposed through
three narrow AI tools that answer questions such as:

- What food did I buy yesterday?
- Give me total expenses for food on 20 June.
- Where did I buy hamburger from last 7 days?

Every answer includes the tool arguments and the receipt evidence behind it. The application works
fully offline. An optional OpenAI-compatible API enables model-driven tool calling, with a
deterministic rule-based router as the fallback.

## Contents

| Area | What is included |
| --- | --- |
| Written answers | [`knowledge.txt`](knowledge.txt) and [`docs/`](docs/) |
| 100k customer analysis | schema, quality, statistics, segmentation, charts, evidence-based insights |
| 2M streaming pipeline | incremental reader, bounded aggregations, batching, partitioned writer, benchmark |
| Self-hosted vector DB | SQLite storage, pure Python cosine similarity, top-k search |
| Receipt application | upload, OCR, review, SQLite persistence, insights, natural-language query tools |
| Delivery | UI, REST API, Dockerfile, Compose, CI, demo script, requirement mapping |

## Quick start

### Local

Requirements: Python 3.11 or newer and Tesseract OCR.

```bash
# macOS: brew install tesseract
# Debian/Ubuntu: sudo apt-get install tesseract-ocr tesseract-ocr-eng

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,analysis]"
uvicorn receipt_ai.api.main:app --reload
```

Open <http://localhost:8000>. API documentation is at <http://localhost:8000/api/docs>.

If Tesseract is not installed, the UI and API still start. Uploads will explain that the OCR engine
is unavailable. Tests use a deterministic fake OCR engine and do not require Tesseract.

### Docker

```bash
docker compose up --build
```

Open <http://localhost:8000>. The named volume `receipt-ai-data` keeps receipts and both databases
across restarts.

```bash
bash scripts/verify_docker.sh   # build, health checks, volume persistence smoke test
```

### Demo

```bash
bash scripts/demo.sh
```

The demo starts the Compose stack, generates a receipt image dated yesterday, uploads it through the
API, saves it, and asks the three required questions. It prints the answers and the evidence counts.
The recording storyboard and reference placeholder are in
[`docs/demo-video.md`](docs/demo-video.md).

## Dataset commands

The two customer CSVs are intentionally ignored by git. Place `customers-100000.csv` and
`customers-2000000.csv` in the repository root.

```bash
make analyze       # 100k analysis into reports/ and charts into reports/figures/
make stream        # full 2M streaming aggregation
make benchmark     # compare naive load, streaming batches, and partitioned split
```

Published evidence:

- [`docs/csv-insights.md`](docs/csv-insights.md)
- [`docs/streaming-tradeoffs.md`](docs/streaming-tradeoffs.md)
- [`docs/benchmark-results.md`](docs/benchmark-results.md)
- [`docs/benchmarks.md`](docs/benchmarks.md)

## Tests and quality

```bash
make lint
make format-check
make test
make cov
```

The suite covers schema and quality profiling, statistics, segmentation, chart generation, streaming
boundaries and malformed rows, partitioned writing, cosine edge cases, vector persistence and
search, monetary and relational integrity, upload validation, OCR normalization and validation,
tool routing, and the full receipt upload-review-save-query-delete flow through the API.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `RECEIPT_AI_DATA_DIR` | `data` | root for databases and uploads |
| `RECEIPT_AI_DB_PATH` | `data/receipts.db` | receipt SQLite database |
| `RECEIPT_AI_VECTOR_DB_PATH` | `data/vectors.db` | vector SQLite database |
| `RECEIPT_AI_UPLOAD_DIR` | `data/uploads` | stored receipt images |
| `RECEIPT_AI_MAX_UPLOAD_BYTES` | `10485760` | maximum upload size |
| `RECEIPT_AI_OCR_LANG` | `eng` | Tesseract language |
| `RECEIPT_AI_TESSERACT_CMD` | `tesseract` | Tesseract executable |
| `RECEIPT_AI_VECTOR_DIMENSION` | `256` | hashing embedder dimension |
| `OPENAI_API_KEY` | unset | enables optional LLM tool calling |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible endpoint |
| `OPENAI_MODEL` | `gpt-4o-mini` | model for tool calling |
| `RECEIPT_AI_LLM_TIMEOUT` | `30` | seconds before falling back |

Copy `.env.example` if you want a starting point. Never commit a real `.env`.

## How it works

```text
upload -> validate -> preprocess -> Tesseract -> parse -> normalize -> validate
       -> pending receipt -> user review -> saved receipt -> vector index
question -> date resolution -> tool registry -> SQLite query -> answer + evidence
```

- Money is stored as integer cents. Dates are ISO strings.
- Receipt writes and item writes share one transaction. Deleting a receipt cascades to items and
  removes its vector.
- OCR is isolated behind an engine protocol, so the test suite does not need Tesseract.
- The vector store uses a deterministic hashed bag-of-words embedder, so retrieval is lexical rather
  than semantic. This keeps the demo offline and dependency free.
- The rule-based router and the optional LLM call the same three tool functions.

More detail: [architecture](docs/architecture.md), [API](docs/api.md),
[agent reliability](docs/agent-reliability.md), [vector index](docs/vector-index.md).

## Project layout

```text
src/receipt_ai/
  api/            FastAPI app, routes, schemas, upload validation
  csv_analysis/   schema, quality, statistics, segmentation, charts, CLI
  streaming/      incremental reader, aggregations, batching, writer, benchmark, CLI
  vector/         validation, cosine similarity, embedding, SQLite store, search
  db/             receipt schema, models, repository
  ocr/            Tesseract engine, preprocessing, extraction, normalization, validation
  services/       receipt workflow, query tools, natural-language routing
  tools/          tool schemas and registry
  ui/             Jinja templates and static assets
scripts/          analysis, demo, Docker verification, fresh-clone check
docs/             engineering answers, architecture, API, benchmarks, limitations
tests/            unit, integration, and Docker asset tests
```

## Documentation

Start with [docs/acceptance-criteria.md](docs/acceptance-criteria.md) and
[docs/assumptions.md](docs/assumptions.md). The engineering knowledge answers live in
[docs/rest-vs-mcp.md](docs/rest-vs-mcp.md) and the related pages. Dataset findings are recorded in
[docs/csv-insights.md](docs/csv-insights.md), and streaming trade-offs in
[docs/streaming-tradeoffs.md](docs/streaming-tradeoffs.md).

## License

MIT
