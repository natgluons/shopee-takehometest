# Ensuring the agent answers correctly

Correctness is a system property, not a prompt property. This project uses several independent
controls so a wrong answer is unlikely and an incorrect answer is easy to detect.

## 1. Constrain the action space

The model can call exactly three tools: purchases by date, food expense by date, and merchant by
item over a window. There is no SQL tool, no shell tool, and no free-form HTTP tool. Each tool has a
JSON schema, rejects unknown fields, validates dates, and caps result sizes. A narrow tool surface
reduces the chance of a plausible but unsupported answer.

## 2. Make the tool the source of truth

Tools return structured facts, not prose. For example:

```json
{
  "tool": "get_food_expenses_by_date",
  "arguments": {"date": "2026-06-20"},
  "data": {
    "date": "2026-06-20",
    "total_cents": 4250,
    "currency": "USD",
    "receipt_count": 3,
    "evidence": [{"receipt_id": 11, "merchant": "Green Bowl", "total_cents": 1850}]
  }
}
```

The answer is rendered from `data`, not from the model's memory. The model may phrase the sentence,
but the number comes from the tool.

## 3. Normalize before querying

- Dates: relative phrases are resolved against an explicit `as_of` date. `yesterday` becomes an ISO
  date. `20 June` resolves to the current year unless that date is in the future, in which case the
  previous year is used. Ambiguous numeric dates produce a warning.
- Money: parsing converts formatted amounts to integer cents. Aggregations sum integers, so there
  is no floating point drift.
- Currency: totals are grouped by currency. The tool refuses to add different currencies together.

## 4. Handle empty results explicitly

An empty result is a valid answer. The tool returns `found: false`, the evidence list is empty, and
the rendered answer says no receipts matched. The prompt explicitly tells the model not to invent a
purchase when the tool returns nothing. The UI shows the same empty state.

## 5. Include evidence and provenance

Every successful answer includes the tool name, normalized arguments, and the rows used. A human can
reconcile the answer with the receipt history. The API response exposes `tool_calls`, `evidence`,
and `engine`, so the behavior is observable in tests and production logs.

## 6. Deterministic fallback

The natural-language router first tries a rule-based parser. It recognizes date expressions, expense
questions, purchase questions, and item lookup questions. When `OPENAI_API_KEY` is set, the LLM tool
calling path is attempted first and the rule-based path remains the fallback. The application never
depends on a remote model to pass its own tests.

## 7. Layer the tests

| Level | What it checks |
| --- | --- |
| Unit | date parsing, money normalization, extraction, validation |
| Repository | SQL filters, aggregation totals, empty results, cascade deletes |
| Tool | schema validation, argument normalization, evidence shape |
| API integration | upload, review, save, history, insights, query |
| Evaluation | fixed questions with expected tool calls and expected totals |

## 8. Human review for extraction

OCR is probabilistic. Uploaded receipts are saved as `pending`, shown in an editable review form,
and only marked `saved` after the user confirms or corrects the fields. Trust in the database does
not depend on OCR perfection.

## 9. Operational controls

- Structured logs include tool name, arguments, duration, and result count without raw image data.
- Health endpoints separate liveness from readiness.
- Request limits and upload size limits prevent accidental denial of service.
- Database constraints enforce non-negative money, valid quantities, and referential integrity.
- A future evaluation run can assert a minimum tool selection accuracy and numeric exact-match rate.

## Known residual risks

- The hashed embedding is lexical, so semantically similar but differently worded items may not
  retrieve each other.
- OCR on crumpled or low-light receipts can misread digits. The review step and validation warnings
  mitigate this but do not eliminate it.
- Ambiguous date formats in receipts can be interpreted incorrectly. The parser records a warning
  and the user can correct the date during review.
