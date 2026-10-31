# API documentation

Interactive OpenAPI documentation is available at `/api/docs` when the application is running. The
OpenAPI schema is served at `/api/openapi.json`. This document summarizes the stable surface and
includes examples.

Base URL for local development: `http://localhost:8000`.

## Error model

| Status | Meaning | Body |
| --- | --- | --- |
| 400 | Invalid query parameter or domain rule | `{"detail": "..."}` |
| 404 | Receipt or collection not found | `{"detail": "receipt not found", "id": "..."}` |
| 422 | Validation failure | `{"detail": "...", "problems": ["..."], "warnings": ["..."]}` |
| 500 | Unhandled server error | Standard FastAPI error |

Validation errors include a `problems` list. Extraction errors may also include `warnings`.

## System

### `GET /healthz`

Returns `200` while the process is alive.

```json
{"status": "ok", "version": "0.1.0"}
```

### `GET /readyz`

Checks the receipt database and vector database. Returns `503` when unavailable.

```json
{"status": "ready", "receipts": 3, "vectors": 3}
```

## Receipts

### `POST /api/receipts/upload`

Multipart form upload with field `file`. Accepted formats: PNG, JPEG, WEBP. Default maximum size is
10 MB and maximum decoded size is 40 megapixels. The returned receipt has status `pending`.

```bash
curl -sS -X POST http://localhost:8000/api/receipts/upload \
  -F "file=@receipt.png;type=image/png"
```

```json
{
  "receipt": {
    "id": 1,
    "merchant": "GREEN BOWL",
    "purchase_date": "2026-06-20",
    "currency": "USD",
    "subtotal_cents": 2850,
    "tax_cents": 285,
    "total_cents": 3135,
    "status": "pending",
    "items": [
      {"description": "Hamburger", "quantity": 2, "unit_price_cents": 1000,
       "line_total_cents": 2000}
    ]
  },
  "warnings": [],
  "ocr": {"engine": "tesseract", "duration_seconds": 0.11, "confidence": null},
  "upload": {"image_format": "PNG", "width": 900, "height": 500}
}
```

### `GET /api/receipts`

Query saved receipts.

| Query parameter | Type | Notes |
| --- | --- | --- |
| `date_from` | ISO date | inclusive |
| `date_to` | ISO date | inclusive |
| `merchant` | string | case-insensitive substring |
| `item` | string | case-insensitive item description substring |
| `status` | `saved`, `pending`, or omitted | defaults to `saved` |
| `limit` | integer | 1 to 1000, default 100 |
| `offset` | integer | default 0 |

```bash
curl -sS "http://localhost:8000/api/receipts?date_from=2026-06-01&date_to=2026-06-30&item=burger"
```

```json
{
  "receipts": [{"id": 1, "merchant": "GREEN BOWL", "total_cents": 3135, "items": []}],
  "count": 1,
  "filters": {"date_from": "2026-06-01", "date_to": "2026-06-30",
              "merchant": null, "item": "burger", "status": "saved"}
}
```

### `GET /api/receipts/{id}`

Returns `{"receipt": {...}}` with line items. Returns 404 when the identifier is unknown.

### `PUT /api/receipts/{id}`

Saves a reviewed receipt. The server sets status to `saved`, validates monetary consistency, updates
the row and items in one transaction, and upserts the receipt vector.

```json
{
  "merchant": "GREEN BOWL",
  "purchase_date": "2026-06-20",
  "currency": "USD",
  "subtotal_cents": 2850,
  "tax_cents": 285,
  "total_cents": 3135,
  "source_image": "/app/data/uploads/receipt.png",
  "raw_text": "GREEN BOWL ... TOTAL 31.35",
  "status": "saved",
  "items": [
    {"description": "Hamburger", "quantity": 2, "unit_price_cents": 1000,
     "line_total_cents": 2000},
    {"description": "Fries", "quantity": 1, "unit_price_cents": 500,
     "line_total_cents": 500}
  ]
}
```

Rules:

- `total_cents` must equal `subtotal_cents + tax_cents`.
- When items are present, `subtotal_cents` must equal the sum of line totals.
- Dates use `YYYY-MM-DD`.
- Money is always integer cents.

### `DELETE /api/receipts/{id}`

Deletes the receipt, cascades items, and removes the receipt vector. Returns
`{"deleted": true, "id": 1}`.

## Insights

### `GET /api/insights`

Returns saved-receipt aggregates.

```json
{
  "totals": [{"currency": "USD", "receipt_count": 3, "total_cents": 4250, "total": "42.50"}],
  "by_day": [{"date": "2026-06-20", "total_cents": 3135, "receipt_count": 1}],
  "by_merchant": [{"merchant": "GREEN BOWL", "total_cents": 3135, "receipt_count": 1}],
  "top_items": [{"description": "Hamburger", "occurrences": 1, "total_cents": 2000}],
  "by_category": [{"category": "uncategorized", "total_cents": 2850, "item_count": 3}],
  "receipt_count": 3
}
```

Multiple currencies are reported separately. No FX conversion is performed.

## Tools

### `GET /api/tools`

Returns the OpenAI-style function schemas for the three tools.

| Tool | Arguments | Purpose |
| --- | --- | --- |
| `get_purchases_by_date` | `date` | purchases on a day or range |
| `get_food_expenses_by_date` | `date` | total spending, grouped by currency |
| `find_merchant_by_item` | `item`, optional `days`, optional `date` | merchant lookup within a window |

Date phrases accepted by the tools include `today`, `yesterday`, `last 7 days`, `last week`,
`this month`, `last month`, `2026-06-20`, `20 June`, `June 20, 2026`, and numeric formats such as
`20/06/2026`.

## Query

### `POST /api/query`

```bash
curl -sS -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Give me total expenses for food on 20 June", "as_of": "2026-10-29"}'
```

```json
{
  "question": "Give me total expenses for food on 20 June",
  "answer": "Your total food expenses for 2026-06-20 were 31.35 USD across 1 receipts.",
  "engine": "rules",
  "found": true,
  "as_of": "2026-10-29",
  "tool_calls": [
    {
      "name": "get_food_expenses_by_date",
      "arguments": {"date_from": "2026-06-20", "date_to": "2026-06-20", "raw_date": "..."},
      "found": true,
      "answer": "Your total food expenses for 2026-06-20 were 31.35 USD across 1 receipts.",
      "warnings": []
    }
  ],
  "evidence": [
    {"type": "receipt", "receipt_id": 1, "merchant": "GREEN BOWL",
     "purchase_date": "2026-06-20", "total": "31.35", "currency": "USD"}
  ],
  "warnings": []
}
```

`as_of` is optional and defaults to the server date. It makes relative phrases deterministic in
tests and demos. When `OPENAI_API_KEY` is set, `engine` may be `llm:<model>`. If the provider call
fails, the response falls back to `rules` and includes a warning.

An empty result is a successful response with `found: false`, an empty `evidence` list, and an
answer that explicitly says no matching receipts were found.

## UI routes

| Route | Purpose |
| --- | --- |
| `/` | upload and extraction review |
| `/history` | receipt history, filters, and spending insights |
| `/query` | natural-language questions with evidence |
| `/static/*` | CSS and JavaScript assets |

## Configuration

See `.env.example` and the README configuration table. Runtime secrets are read from the
environment. The application does not require an LLM key.
