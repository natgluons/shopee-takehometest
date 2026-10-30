"""Natural-language query and tool discovery routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from receipt_ai.api.deps import get_nl_query_engine, get_query_service
from receipt_ai.api.schemas import QueryPayload
from receipt_ai.services.nl_query import NaturalLanguageQueryEngine
from receipt_ai.services.query import QueryService
from receipt_ai.tools.registry import ToolRegistry

router = APIRouter(prefix="/api", tags=["query"])


@router.get("/tools")
def list_tools() -> dict[str, object]:
    return {"tools": ToolRegistry.schemas()}


@router.post("/query")
def ask_question(
    payload: QueryPayload,
    engine: NaturalLanguageQueryEngine = Depends(get_nl_query_engine),
    _: QueryService = Depends(get_query_service),
) -> dict[str, object]:
    return engine.answer(payload.question, as_of=payload.as_of).to_dict()
