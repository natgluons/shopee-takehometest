# Acceptance criteria

This document maps the take-home requirements to observable evidence in the repository.

## Engineering knowledge

1. `knowledge.txt` answers the five written questions in casual English without semicolons or em
   dashes.
2. Long-form engineering notes live under `docs/` for REST versus MCP, interoperability,
   answer reliability, containerization, and model fine-tuning.

## 100k customer analysis

3. The analyzer inspects the real schema and infers logical column types.
4. The profiler reports missing values, duplicate rows, duplicate customer identifiers, invalid
   emails, invalid dates, and whitespace defects.
5. Descriptive statistics cover the numeric index, subscription date range, and categorical
   distributions.
6. Customer segments are derived from observable fields, not invented transaction data.
7. Charts are written to `reports/figures/` and every number in `docs/csv-insights.md` comes from
   a reproducible command.

## 2M customer streaming

8. The streaming reader never materializes the whole file.
9. Aggregations use bounded state and one pass over the data.
10. Batch size is configurable and the final partial batch is processed.
11. The partitioned writer emits valid CSV files split by a useful key.
12. Malformed rows, blank lines, and missing columns are counted rather than crashing the run.
13. The benchmark harness records elapsed time, peak traced memory, and rows per second.
14. Documentation compares streaming, batching, and physical file splitting, including when each
    approach is appropriate.

## Self-hosted vector database

15. Vectors are validated for dimensionality, finiteness, and non-zero norm before storage.
16. Cosine similarity is implemented with the Python standard library only.
17. Edge cases include zero vectors, mismatched dimensions, negative values, and single-element
    vectors.
18. Vectors persist in SQLite with collection metadata and JSON metadata payloads.
19. CRUD operations are transactional and idempotent for an external identifier.
20. Top-k search returns deterministic ordering with a stable tie-breaker.

## Receipt application

21. The database stores receipts and line items with integer cents and foreign-key cascades.
22. Uploads are validated for content type, extension, magic bytes, dimensions, and size.
23. OCR runs locally through Tesseract and preprocessing improves contrast and scale.
24. Extraction detects merchant, purchase date, items, subtotal, tax, and total.
25. Dates are normalized to ISO format and money is normalized to integer cents.
26. Validation rejects missing dates, future dates, non-positive totals, and inconsistent totals.
27. The review flow persists a pending extraction, lets the user edit it, then saves it.
28. Query tools answer purchases by date, food expense by date, and merchant by item over a window.
29. Every answer includes tool evidence or an explicit empty-result explanation.
30. The UI supports upload and review, history and insights, and natural-language questions.
31. End-to-end tests cover upload, review, save, history, insights, and query.

## Delivery

32. A multi-stage Dockerfile runs as a non-root user and includes Tesseract.
33. Compose mounts a volume so data survives container restarts.
34. CI runs linting and tests, then builds the container image.
35. Image publication strategy is documented.
36. Final documentation covers architecture, API, benchmarks, limitations, requirements mapping,
    and a demonstration script.
37. A fresh clone can install, test, and run using the documented commands.
