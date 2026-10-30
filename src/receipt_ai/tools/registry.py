"""Tool schemas and dispatch shared by the rule-based router and the LLM."""

from __future__ import annotations

from datetime import date
from typing import Any

from receipt_ai.services.query import QueryService, ToolResult


class ToolArgumentError(ValueError):
    """Raised when a tool call has invalid arguments."""


TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_purchases_by_date",
            "description": (
                "List saved food purchases for a date or date range. Use this for questions "
                "about what food the user bought on a specific day."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": (
                            "Date phrase such as 'yesterday', '2026-06-20', '20 June', "
                            "or 'last 7 days'."
                        ),
                    }
                },
                "required": ["date"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_food_expenses_by_date",
            "description": (
                "Return total food spending for a date or date range, grouped by currency."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Date phrase such as 'yesterday' or '20 June'.",
                    }
                },
                "required": ["date"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_merchant_by_item",
            "description": (
                "Find which merchants sold an item within a recent date window. Use this for "
                "questions like 'where did I buy hamburger from last 7 days'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "item": {
                        "type": "string",
                        "description": "Food item name, for example hamburger or coffee.",
                    },
                    "days": {
                        "type": "integer",
                        "description": "Number of days to look back. Defaults to 7.",
                        "minimum": 1,
                        "maximum": 3650,
                    },
                    "date": {
                        "type": "string",
                        "description": "Optional date phrase overriding the day window.",
                    },
                },
                "required": ["item"],
                "additionalProperties": False,
            },
        },
    },
]


class ToolRegistry:
    """Validate and execute the three receipt query tools."""

    def __init__(self, query_service: QueryService, as_of: date | None = None) -> None:
        self.query_service = query_service
        self.as_of = as_of

    @staticmethod
    def schemas() -> list[dict[str, Any]]:
        return TOOL_SCHEMAS

    def _as_of(self, arguments: dict[str, Any]) -> date | None:
        raw = arguments.get("as_of")
        if raw:
            try:
                return date.fromisoformat(str(raw))
            except ValueError as exc:
                raise ToolArgumentError("as_of must be an ISO date") from exc
        return self.as_of

    def call(self, name: str, arguments: dict[str, Any] | None = None) -> ToolResult:
        arguments = dict(arguments or {})
        as_of = self._as_of(arguments)
        if name == "get_purchases_by_date":
            self._require(arguments, "date")
            self._reject_unknown(arguments, {"date", "as_of"})
            return self.query_service.get_purchases_by_date(str(arguments["date"]), as_of=as_of)
        if name == "get_food_expenses_by_date":
            self._require(arguments, "date")
            self._reject_unknown(arguments, {"date", "as_of"})
            return self.query_service.get_food_expenses_by_date(str(arguments["date"]), as_of=as_of)
        if name == "find_merchant_by_item":
            self._require(arguments, "item")
            self._reject_unknown(arguments, {"item", "days", "date", "as_of"})
            days = arguments.get("days", 7)
            if isinstance(days, bool) or not isinstance(days, int):
                raise ToolArgumentError("days must be an integer")
            if days < 1 or days > 3650:
                raise ToolArgumentError("days must be between 1 and 3650")
            date_phrase = arguments.get("date")
            return self.query_service.find_merchant_by_item(
                str(arguments["item"]),
                days=days,
                date_phrase=str(date_phrase) if date_phrase else None,
                as_of=as_of,
            )
        raise ToolArgumentError(f"unknown tool: {name}")

    @staticmethod
    def _require(arguments: dict[str, Any], key: str) -> None:
        if key not in arguments or arguments[key] in {None, ""}:
            raise ToolArgumentError(f"missing required argument: {key}")

    @staticmethod
    def _reject_unknown(arguments: dict[str, Any], allowed: set[str]) -> None:
        unknown = set(arguments) - allowed
        if unknown:
            raise ToolArgumentError(f"unknown arguments: {sorted(unknown)}")

    def execute(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.call(name, arguments).to_dict()
