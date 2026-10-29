# Limitations

## Scope and deployment

- Single user, no authentication, no authorization, and no tenant isolation. Do not expose it
  publicly without adding those controls.
- SQLite is the system of record and the vector store. It handles a local workload well, but it is
  not a multi-writer distributed database. Concurrent writes are serialized.
- There are no schema migrations. A schema change requires a migration plan before an upgrade. The
  current schema version is stored in `schema_meta`.
- The application is not designed for horizontal scaling. A shared database and object storage would
  be required before running multiple replicas.
- Uploaded images stay on local disk. There is no object storage, retention policy, or deletion
  workflow beyond deleting the receipt row.

## OCR and extraction

- Tesseract accuracy depends on image quality. Blur, shadows, folds, thermal paper fade, unusual
  fonts, and handwritten receipts may be misread.
- The extractor uses conservative regular expressions and line heuristics. It handles common
  English receipt layouts but not every multilingual or highly stylized format.
- Numeric dates are ambiguous when both parts are 12 or less. The parser defaults to month/day and
  records a warning. The review UI lets the user correct it.
- Dates without a year default to the current year, or the previous year if that would be in the
  future. This can be wrong for old receipts and is reported as a warning.
- Line item extraction can miss discounts, modifiers, multi-line descriptions, and items printed
  without a trailing amount.
- PDF receipts and screenshots in unsupported formats are rejected. The demo supports PNG, JPEG, and
  WEBP.
- OCR confidence is not populated. Adding a TSV confidence pass is a possible improvement.

## Money and dates

- Totals are grouped by currency. There is no exchange-rate source and no FX conversion, so
  cross-currency totals are intentionally never added together.
- Money is stored as integer cents. Values with more than two decimal places are rounded half up
  before storage.
- Receipt totals must equal subtotal plus tax within a two cent tolerance. A receipt layout that
  uses a different definition of subtotal or includes a service charge may be rejected until the
  user corrects it.
- Subtotal must equal the sum of line totals when items exist. Discounts or split lines can require
  manual adjustment during review.

## Vector search

- The hashed bag-of-words embedder is lexical, not semantic. It is deterministic and dependency
  free but it will not match synonyms that share no tokens.
- Search is brute force: `O(N * D)` per query. There is no ANN index. This is fine for thousands of
  receipts and not fine for millions.
- Vectors are stored as JSON text in SQLite. This is simple and portable but larger and slower than
  a binary format.
- Changing the embedder dimension or algorithm requires re-indexing all receipts. There is a
  `rebuild_index` service method but no automatic migration.
- Metadata filtering supports equality only, not ranges or full-text.

## Natural-language answers

- Without an API key, the rule-based router handles the three required question shapes and common
  date phrases. It is not a general-purpose conversational agent.
- With an API key, the LLM path depends on an external OpenAI-compatible endpoint. Network failures
  and provider errors fall back to the rule-based router, and a warning is returned.
- The LLM can still choose the wrong tool or a poor date phrase. Evidence and tool-call arguments
  are returned so the answer can be audited, but no automated correctness guarantee exists.
- There is no formal evaluation harness with a large labelled question set. Tests cover the required
  examples and representative edge cases.
- The assistant cannot answer questions outside the three tools, such as nutrition, item
  categorization across arbitrary taxonomies, or budget forecasting.

## Data analysis

- The 100k analysis conclusions are only about the provided synthetic customer file. The flat
  geographic distribution and absence of free email domains suggest synthetic generation, so
  business conclusions should not be generalized.
- Segmentation is descriptive. There are no transactions, revenue, or churn labels, so RFM, CLV,
  and churn prediction are out of scope.
- Phone validation accepts extension formats but does not normalize to E.164. A production import
  should do that.
- The analysis uses pandas on the 100k file. The streaming pipeline is separate and deliberately
  does not depend on pandas.
- The 2M streaming benchmark uses a line-count estimate for rows, which assumes no embedded newlines
  in fields. The provided file satisfies that assumption.

## Operational

- Logging is basic structured text. There is no OpenTelemetry tracing or metrics endpoint.
- There is no rate limiting, request queue, or background worker. OCR runs in the request path and
  can be slow for large images.
- Health checks prove the process and databases are reachable, not that OCR or an external LLM is
  healthy.
- The CI workflow builds and smoke-tests the image but does not publish it. Publication is
  documented and intentionally separate.
- The demonstration video reference is a placeholder until a recording is added.
