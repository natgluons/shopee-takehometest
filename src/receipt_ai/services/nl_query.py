"""Natural-language question routing with an optional LLM tool-calling path."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import httpx

from receipt_ai.config import Settings
from receipt_ai.services.query import (
    DateResolutionError,
    QueryService,
    ToolResult,
    resolve_date_range,
)
from receipt_ai.tools.registry import ToolArgumentError, ToolRegistry

logger = logging.getLogger("receipt_ai.query")

EXPENSE_RE = re.compile(r"\b(total|spend|spent|expense|expenses|cost|costs)\b", re.IGNORECASE)
MERCHANT_RE = re.compile(
    r"\b(where did i (?:buy|get|purchase)|which (?:merchant|store|shop)|where was)\b",
    re.IGNORECASE,
)
PURCHASE_RE = re.compile(
    r"\b(what (?:food )?did i (?:buy|get|purchase)|what did i buy|purchases?|bought)\b",
    re.IGNORECASE,
)
ITEM_RE = re.compile(
    r"\b(?:buy|bought|get|got|purchase|purchased)\s+(?:a\s+|an\s+|the\s+)?"
    r"(.+?)(?:\s+(?:from|at|in|on|during|last|past)\b|$)",
    re.IGNORECASE,
)
DAYS_RE = re.compile(r"\b(?:last|past)\s+(\d{1,3})\s+days?\b", re.IGNORECASE)


class QueryEngineError(RuntimeError):
    """Raised when a question cannot be answered."""


@dataclass
class QueryResponse:
    question: str
    answer: str
    engine: str
    found: bool
    as_of: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "answer": self.answer,
            "engine": self.engine,
            "found": self.found,
            "as_of": self.as_of,
            "tool_calls": self.tool_calls,
            "evidence": self.evidence,
            "warnings": list(self.warnings),
        }


def _tool_call_record(result: ToolResult) -> dict[str, Any]:
    return {
        "name": result.tool,
        "arguments": result.arguments,
        "found": result.found,
        "answer": result.answer,
        "warnings": result.warnings,
    }


def _extract_days(question: str) -> int:
    match = DAYS_RE.search(question)
    if match:
        return max(1, int(match.group(1)))
    if "last week" in question.lower() or "past week" in question.lower():
        return 7
    return 7


def _extract_item(question: str) -> str | None:
    quoted = re.search(r"[\"']([^\"']+)[\"']", question)
    if quoted:
        return quoted.group(1).strip()
    match = ITEM_RE.search(question)
    if not match:
        return None
    item = match.group(1).strip(" .,?!")
    if not item or item.lower() in {"food", "something", "anything"}:
        return None
    return item


class NaturalLanguageQueryEngine:
    """Route questions to deterministic tools, optionally using an LLM first."""

    def __init__(
        self,
        query_service: QueryService,
        settings: Settings | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.query_service = query_service
        self.settings = settings or Settings.from_env()
        self.http_client = http_client

    def answer(self, question: str, as_of: date | None = None) -> QueryResponse:
        question = " ".join(question.split())
        if not question:
            raise QueryEngineError("question must not be empty")
        effective_date = as_of or date.today()
        warnings: list[str] = []
        if self.settings.openai_api_key:
            try:
                return self._answer_with_llm(question, effective_date)
            except Exception as exc:  # noqa: BLE001 - fall back on any provider failure
                logger.warning("LLM query path failed, using rule-based fallback: %s", exc)
                warnings.append(f"LLM path failed, used the local router instead: {exc}")
        response = self._answer_with_rules(question, effective_date)
        response.warnings = warnings + response.warnings
        return response

    def _registry(self, as_of: date) -> ToolRegistry:
        return ToolRegistry(self.query_service, as_of=as_of)

    def _answer_with_rules(self, question: str, as_of: date) -> QueryResponse:
        registry = self._registry(as_of)
        lowered = question.lower()
        try:
            if EXPENSE_RE.search(lowered):
                result = registry.call("get_food_expenses_by_date", {"date": question})
                return self._response(question, as_of, "rules", result)
            if MERCHANT_RE.search(lowered):
                item = _extract_item(question)
                if not item:
                    return QueryResponse(
                        question=question,
                        answer=(
                            "Tell me which food item you are looking for, for example "
                            "'where did I buy hamburger from last 7 days'."
                        ),
                        engine="rules",
                        found=False,
                        as_of=as_of.isoformat(),
                    )
                arguments: dict[str, Any] = {
                    "item": item,
                    "days": _extract_days(question),
                }
                try:
                    resolve_date_range(question, today=as_of)
                except DateResolutionError:
                    pass
                else:
                    arguments["date"] = question
                result = registry.call("find_merchant_by_item", arguments)
                return self._response(question, as_of, "rules", result)
            if PURCHASE_RE.search(lowered):
                result = registry.call("get_purchases_by_date", {"date": question})
                return self._response(question, as_of, "rules", result)
            result = registry.call("get_purchases_by_date", {"date": question})
            return self._response(question, as_of, "rules", result)
        except (DateResolutionError, ToolArgumentError, ValueError) as exc:
            return QueryResponse(
                question=question,
                answer=(
                    "I could not understand the date in that question. Try a phrase such as "
                    "'yesterday', '20 June', or 'last 7 days'."
                ),
                engine="rules",
                found=False,
                as_of=as_of.isoformat(),
                warnings=[str(exc)],
            )

    @staticmethod
    def _response(question: str, as_of: date, engine: str, result: ToolResult) -> QueryResponse:
        return QueryResponse(
            question=question,
            answer=result.answer,
            engine=engine,
            found=result.found,
            as_of=as_of.isoformat(),
            tool_calls=[_tool_call_record(result)],
            evidence=result.evidence,
            warnings=result.warnings,
        )

    def _answer_with_llm(self, question: str, as_of: date) -> QueryResponse:
        settings = self.settings
        if not settings.openai_api_key:
            raise QueryEngineError("no API key configured")
        registry = self._registry(as_of)
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": (
                    "You are a receipt assistant. Today is "
                    f"{as_of.isoformat()}. Use the provided tools to answer questions about "
                    "the user's saved food receipts. Never invent a purchase, merchant, date, "
                    "or amount. If a tool finds nothing, say so clearly. Prefer calling a "
                    "tool over answering from memory. Mention the date range used."
                ),
            },
            {"role": "user", "content": question},
        ]
        url = f"{settings.openai_base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        }
        client = self.http_client or httpx
        tool_calls: list[dict[str, Any]] = []
        evidence: list[dict[str, Any]] = []
        last_result: ToolResult | None = None
        for _ in range(4):
            payload = {
                "model": settings.openai_model,
                "messages": messages,
                "tools": ToolRegistry.schemas(),
                "tool_choice": "auto",
                "temperature": 0,
            }
            response = client.post(
                url,
                json=payload,
                headers=headers,
                timeout=settings.llm_timeout_seconds,
            )
            response.raise_for_status()
            body = response.json()
            choices = body.get("choices") or []
            if not choices:
                raise QueryEngineError("LLM returned no choices")
            message = choices[0].get("message") or {}
            pending_calls = message.get("tool_calls") or []
            if not pending_calls:
                answer = (message.get("content") or "").strip()
                if not answer and last_result is not None:
                    answer = last_result.answer
                return QueryResponse(
                    question=question,
                    answer=answer or "I could not produce an answer.",
                    engine=f"llm:{settings.openai_model}",
                    found=bool(evidence),
                    as_of=as_of.isoformat(),
                    tool_calls=tool_calls,
                    evidence=evidence,
                )
            messages.append(
                {
                    "role": "assistant",
                    "content": message.get("content"),
                    "tool_calls": pending_calls,
                }
            )
            for call in pending_calls:
                function = call.get("function") or {}
                name = function.get("name") or ""
                raw_arguments = function.get("arguments") or "{}"
                try:
                    arguments = json.loads(raw_arguments)
                except json.JSONDecodeError as exc:
                    raise QueryEngineError(f"LLM returned invalid tool arguments: {exc}") from exc
                result = registry.call(name, arguments)
                last_result = result
                tool_calls.append(_tool_call_record(result))
                evidence.extend(result.evidence)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.get("id", ""),
                        "content": json.dumps(result.to_dict(), default=str)[:20_000],
                    }
                )
        raise QueryEngineError("LLM exceeded the tool-call limit")
