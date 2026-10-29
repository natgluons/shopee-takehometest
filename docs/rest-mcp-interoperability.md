# REST and MCP interoperability

## The layering

A useful mental model is three layers.

1. The domain layer owns receipts, money, dates, and database transactions.
2. The REST layer exposes those operations with HTTP semantics, validation, and error codes.
3. The MCP layer exposes a curated subset as model-facing tools with descriptions and JSON schemas.

The model never talks to SQLite. It talks to a tool. The tool talks to the service. The service
uses the repository. The REST route uses the same service. This keeps behavior identical whether a
human clicks a button, a script calls REST, or a model calls an MCP tool.

## Wrapping REST with MCP

An MCP tool wrapper is usually thin. It does four things:

- validate arguments against a JSON schema
- map model-friendly values such as relative dates into canonical values
- call the underlying service or REST endpoint
- return a compact result with evidence and an explicit empty state

For example, `get_food_expenses_by_date` accepts `{"date": "2026-06-20"}` and returns
`{"total": "42.50", "currency": "USD", "receipt_count": 3, "evidence": [...]}`. The wrapper rejects
unknown fields and invalid dates before any query runs.

## Design rules that make the bridge safe

- Prefer a small number of narrow tools over one flexible `run_sql` tool.
- Put the same authorization checks on the tool path and the REST path.
- Never let the model supply identifiers that bypass ownership checks.
- Return machine-readable errors instead of prose-only failures.
- Include the exact filter and the rows used so a human can verify the answer.
- Keep timeouts and result limits at the tool boundary.
- Log tool name, arguments, duration, and result count. Avoid logging sensitive payloads.

## Transport mapping

MCP supports stdio and streamable HTTP transports. A common production setup runs the MCP server in
the same process as the application or as a sidecar. The MCP server calls the application service
directly, not over the public internet. If it calls REST, use an internal address and a service
credential. This avoids adding a network hop that can fail halfway through a model turn.

## Compatibility matrix

| Capability | REST mapping | MCP mapping |
| --- | --- | --- |
| List receipts | `GET /api/receipts` | resource `receipts` or tool `list_receipts` |
| Upload image | `POST /api/receipts/upload` | tool `upload_receipt` with base64 or URI |
| Save reviewed receipt | `PUT /api/receipts/{id}` | tool `save_receipt` |
| Spending total | `GET /api/insights` | tool `get_food_expenses_by_date` |
| Merchant lookup | `GET /api/receipts?item=...` | tool `find_merchant_by_item` |

## This repository

The optional LLM path sends the three tool schemas to an OpenAI-compatible chat completions
endpoint, executes returned tool calls through a shared registry, and feeds the results back for a
final answer. The deterministic router uses the same registry. Adding an MCP server would mean
publishing the registry over MCP and reusing the same handlers. No business logic would move.
