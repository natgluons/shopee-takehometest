# REST API vs MCP

## What REST is good at

REST is a resource-oriented HTTP style. A client sends a method and a path such as `GET
/api/receipts?date_from=2026-06-20`, and the server responds with a representation, usually JSON.
REST gives us mature tooling, caching, status codes, authentication middleware, API gateways,
observability, and a huge hiring pool. It is the default contract between services.

For AI, REST is the system of record. Models should not invent database queries. They should call a
narrow, validated endpoint or tool that runs a parameterized query. REST is where business rules,
authorization, and transactions live.

## What MCP adds

The Model Context Protocol is an open standard for connecting AI applications to external context
and tools. An MCP server publishes tools and resources with names, descriptions, and JSON schemas.
An MCP client such as a desktop assistant connects to one or more servers, merges their tool lists,
and lets the model request calls. The host application executes the call and returns the result.

The important difference is intent. REST describes resources, while MCP describes model-facing
capabilities. MCP also standardizes discovery, so a new server can appear without shipping a new
prompt or a custom integration in every client. It supports tools, resources, and prompts as
separate concepts. It also has an explicit lifecycle for initialization and capability negotiation.

## Side-by-side

| Concern | REST API | MCP |
| --- | --- | --- |
| Primary audience | Services and application code | AI hosts and model-driven clients |
| Contract shape | HTTP method, path, status, body | Named tools and resources with JSON schemas |
| Discovery | OpenAPI or documentation | Protocol-level capability and tool listing |
| Execution | Client code decides what to call | Model chooses a tool and host executes it |
| Failure model | HTTP status codes and error bodies | Tool result content plus protocol errors |
| Auth | Application-specific headers and OAuth | Host-managed transport authentication |
| Best fit | Business operations and data access | Exposing safe, bounded actions to a model |

## Where people get confused

MCP is not a replacement for REST. It is a layer that can sit in front of REST. If you already have
`POST /api/receipts/upload`, an MCP tool named `upload_receipt` can wrap it. The wrapper validates
arguments, enforces limits, calls the REST endpoint, and returns a compact result the model can
read. The REST endpoint still owns persistence and invariants.

MCP is also not a magic accuracy fix. A model can still call the wrong tool or pass a bad date. The
real reliability comes from a small tool surface, strict schemas, validation, and evidence in the
result.

## How this project uses both

This repository exposes the receipt platform as a REST API under `/api`. The natural-language query
feature exposes three narrow tools to an optional LLM: purchases by date, food expenses by date, and
merchant by item over a window. Those tools are described with JSON schemas and have deterministic
implementations. The same functions are called by the local rule-based router, so the product works
without an API key. A production deployment could publish the same three tools over MCP without
changing the tool implementation, because the tool layer is already separated from transport.
