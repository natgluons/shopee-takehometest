# Architecture

## System context

Receipt AI is a single-node application with a server-rendered UI, a REST API, a local OCR engine, a
SQLite system of record, and an embedded vector store. The optional LLM path is an enhancement, not
a dependency.

```text
Browser
  |
  | HTML, JSON, multipart uploads
  v
FastAPI application
  |-- UI routes (Jinja templates, static assets)
  |-- REST routes (/api/receipts, /api/insights, /api/query, /api/tools)
  |
  |-- ReceiptService
  |     |-- upload validation (MIME, extension, magic bytes, dimensions, size)
  |     |-- image preprocessing (Pillow: orient, grayscale, resize, sharpen)
  |     |-- OCR (Tesseract subprocess)
  |     |-- extraction (regex field parsing)
  |     |-- normalization (ISO dates, integer cents, items)
  |     |-- validation (future dates, totals, subtotal, currency)
  |     |-- persistence (ReceiptRepository)
  |     `-- indexing (VectorStore + hashing embedder)
  |
  |-- QueryService
  |     |-- date phrase resolution
  |     |-- purchases by date
  |     |-- food expenses by date or range
  |     `-- merchant by item over a window
  |
  `-- NaturalLanguageQueryEngine
        |-- deterministic rule router (always available)
        `-- optional OpenAI-compatible tool calling
              `-- ToolRegistry -> QueryService

SQLite                          Filesystem
  data/receipts.db                data/uploads/<stored image>
  data/vectors.db                 reports/ (generated analysis output)
```

## Data model

### Receipts

`receipts` stores one row per receipt with merchant, ISO purchase date, three-letter currency,
subtotal, tax, total in integer cents, source image path, raw OCR text, status (`pending` or
`saved`), and timestamps. A database check enforces `total_cents = subtotal_cents + tax_cents`.
Non-negative checks apply to all monetary columns.

`receipt_items` stores line items with description, quantity, unit price, line total, and optional
category. The foreign key uses `ON DELETE CASCADE`. Indexes cover purchase date, merchant,
status, receipt items, and item descriptions.

### Vectors

`collections` stores a named collection, dimension, metric, and creation time. `vectors` stores an
external identifier, content text, a JSON vector, JSON metadata, and timestamps. The unique key is
`(collection_id, external_id)`. Receipt vectors use `receipt:<id>` as the external identifier.

## Receipt lifecycle

```text
upload
  -> validate file
  -> store image under a generated name
  -> preprocess to a temporary PNG
  -> run Tesseract
  -> parse fields
  -> normalize dates and money
  -> validate
  -> insert receipt with status = pending
  -> return extraction, warnings, OCR metadata

review
  -> user edits fields in the UI
  -> PUT /api/receipts/{id}
  -> validate and update receipt
  -> status = saved
  -> embed and upsert vector
  -> receipt becomes queryable
```

Pending receipts are intentionally excluded from list, insight, and query results. A failed upload
or validation removes the stored image so the system does not accumulate orphans.

## Query path

The UI sends a question and an optional `as_of` date. The natural-language engine first tries the
LLM path if an API key is configured. If that path fails for any reason it falls back to the
deterministic router. Both paths use the same three tools.

1. The date phrase is resolved against `as_of`. Relative phrases are relative to that date, not the
   machine clock.
2. The tool validates arguments and calls `ReceiptRepository` with parameterized SQL.
3. The tool builds a structured result with `answer`, `data`, `evidence`, `warnings`, and `found`.
4. The API returns the result. The UI renders the answer, the evidence rows, and the exact tool
   call arguments.

The LLM never receives a SQL tool and never talks to SQLite directly. The optional model can only
choose among three narrow functions.

## Why these boundaries

- OCR is isolated behind an `OCREngine` protocol, so tests use a deterministic fake and production
  uses Tesseract.
- Normalization is separate from extraction, so date and money parsing can be tested without an
  image.
- Validation is separate from persistence, so domain errors are explicit and testable.
- The repository owns transactions and SQL. Routers and tools do not build SQL.
- The vector store is independent of receipts. It can be replaced with a dedicated service without
  changing the receipt domain.
- The rule-based router shares the registry with the LLM path, so tool behavior cannot drift between
  the two modes.

## Consistency and failure handling

- SQLite transactions wrap receipt plus items writes. A failure rolls back both.
- Deleting a receipt cascades to items and removes the corresponding vector.
- Upsert semantics make indexing idempotent, so a retry does not duplicate a vector.
- Upload validation rejects oversized, corrupt, mismatched, or unsafe files before OCR.
- OCR failures return an error and remove the stored image.
- Query errors return a structured problem list. Empty results are a successful response with
  `found: false` and an empty evidence list.
- `/healthz` reports liveness. `/readyz` checks both SQLite databases and returns 503 if either is
  unavailable.

## Deployment topology

- Local development: `uvicorn` with files under `data/`.
- Container: multi-stage Python 3.12 slim image with Tesseract, non-root user, read-only root
  filesystem, writable `/app/data` volume, and `/tmp` tmpfs.
- Compose: one service, named volume `receipt-ai-data`, health check, port 8000.
- CI: lint, format check, full test suite, container build, and container health smoke test.

## Extension points

- Replace `HashingEmbedder` with a real embedding model and re-index the collection.
- Publish `ToolRegistry` over MCP to reuse the same tools from any MCP client.
- Swap SQLite for PostgreSQL and the embedded vector store for pgvector or a dedicated vector
  database if concurrency or scale grows.
- Add authentication and a tenant identifier before exposing the service outside a local machine.
