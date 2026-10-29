# Assumptions

## Dataset assumptions

- `customers-100000.csv` and `customers-2000000.csv` are synthetic customer exports with the same
  columns. The large file is treated as a scale test, not as a different business domain.
- There are no transaction, revenue, or support-ticket columns, so segmentation uses subscription
  recency, subscription cohort, geography, company presence, and contact completeness. Any
  "value" segment is explicitly a proxy and is labelled as such.
- `Index` is a row number supplied by the exporter. It is useful for statistics and duplicate
  checks but is not a business key.
- `Customer Id` is assumed to be the intended identifier. Repeated identifiers are reported as data
  quality defects rather than silently deduplicated.
- Dates are parsed as ISO dates in the source. Ambiguous dates in receipt images are interpreted
  day-first only when the day is greater than 12, otherwise month-first is used and the ambiguity is
  surfaced as a warning.

## Receipt application assumptions

- The application is a single-user local tool. There is no authentication layer, tenant model, or
  multi-user authorization. Deploying it publicly would require those controls.
- Receipts are food receipts. Every saved receipt contributes to food expense totals without an
  additional category gate, while line items may optionally carry a category.
- Currency is stored per receipt. Aggregations group by the receipt currency and do not perform FX
  conversion, because no exchange-rate source is provided.
- Monetary values are stored as integer cents. Floating point is used only inside parsing and is
  immediately rounded to cents.
- OCR quality depends on the local Tesseract installation. The review step exists because OCR is
  fallible, and the saved record is the user-confirmed record.
- Uploaded images are retained for audit. The demo accepts common raster formats and rejects PDFs.
- The optional LLM path uses an OpenAI-compatible chat completions endpoint. Without an API key the
  deterministic intent parser is used. Both paths call the same tool functions.
- The vector index uses a deterministic hashed bag-of-words embedding so the project remains fully
  local and dependency-free. It is adequate for keyword-style retrieval over receipt text but it is
  not a semantic embedding model.
- SQLite is the system of record and the vector store. Write concurrency is limited by SQLite, which
  is acceptable for a single-user local deployment.
- The 2M benchmark is run locally and numbers vary by machine. Published numbers include the
  hardware and command used.
