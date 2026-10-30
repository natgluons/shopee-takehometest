from __future__ import annotations

from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from receipt_ai.config import Settings
from receipt_ai.db.models import ReceiptDraft, ReceiptItemInput
from receipt_ai.db.repository import ReceiptRepository
from receipt_ai.services.nl_query import NaturalLanguageQueryEngine
from receipt_ai.services.query import (
    DateResolutionError,
    QueryService,
    resolve_date_range,
)
from receipt_ai.tools.registry import ToolArgumentError, ToolRegistry

TODAY = date(2026, 10, 29)
NO_LLM = replace(Settings.from_env(), openai_api_key=None)


@pytest.fixture
def query_service(tmp_path: Path) -> QueryService:
    repository = ReceiptRepository(tmp_path / "receipts.db")
    repository.create_receipt(
        ReceiptDraft(
            merchant="Green Bowl",
            purchase_date="2026-06-20",
            tax_cents=285,
            items=[
                ReceiptItemInput("Hamburger", 2000, quantity=2),
                ReceiptItemInput("Fries", 500),
                ReceiptItemInput("Coffee", 350),
            ],
            status="saved",
        )
    )
    repository.create_receipt(
        ReceiptDraft(
            merchant="Burger Barn",
            purchase_date="2026-06-27",
            currency="EUR",
            tax_cents=100,
            items=[ReceiptItemInput("Cheeseburger", 900)],
            status="saved",
        )
    )
    repository.create_receipt(
        ReceiptDraft(
            merchant="Draft Diner",
            purchase_date="2026-06-28",
            total_cents=1000,
            items=[ReceiptItemInput("Soup", 1000)],
            status="pending",
        )
    )
    service = QueryService(repository)
    yield service
    repository.close()


def test_resolve_date_phrases() -> None:
    assert resolve_date_range("yesterday", TODAY).start == date(2026, 10, 28)
    assert resolve_date_range("today", TODAY).start == TODAY
    assert resolve_date_range("20 June", TODAY).start == date(2026, 6, 20)
    assert resolve_date_range("Give me totals on 20 June", TODAY).start == date(2026, 6, 20)
    assert resolve_date_range("June 20, 2026", TODAY).start == date(2026, 6, 20)
    assert resolve_date_range("2026-06-20", TODAY).start == date(2026, 6, 20)
    window = resolve_date_range("last 7 days", TODAY)
    assert window.start == date(2026, 10, 23)
    assert window.end == TODAY
    with pytest.raises(DateResolutionError):
        resolve_date_range("sometime soon", TODAY)


def test_purchases_by_date(query_service: QueryService) -> None:
    result = query_service.get_purchases_by_date("20 June", as_of=TODAY)
    assert result.found is True
    assert result.data["receipt_count"] == 1
    assert result.evidence[0]["merchant"] == "Green Bowl"
    assert "Hamburger x2" in result.answer
    assert "31.35 USD" in result.answer


def test_purchases_empty_result(query_service: QueryService) -> None:
    result = query_service.get_purchases_by_date("yesterday", as_of=TODAY)
    assert result.found is False
    assert result.evidence == []
    assert "could not find" in result.answer.lower()


def test_expenses_by_date(query_service: QueryService) -> None:
    result = query_service.get_food_expenses_by_date("20 June", as_of=TODAY)
    assert result.found is True
    assert result.data["currencies"][0]["total_cents"] == 3135
    assert "31.35 USD" in result.answer


def test_expenses_range_and_multiple_currencies(query_service: QueryService) -> None:
    result = query_service.get_food_expenses_by_date("this month", as_of=date(2026, 6, 30))
    totals = {item["currency"]: item["total_cents"] for item in result.data["currencies"]}
    assert totals == {"EUR": 1000, "USD": 3135}
    assert result.data["receipt_count"] == 2


def test_merchant_by_item(query_service: QueryService) -> None:
    result = query_service.find_merchant_by_item("burger", days=8, as_of=date(2026, 6, 27))
    assert result.found is True
    assert set(result.data["merchants"]) == {"Burger Barn", "Green Bowl"}
    assert any(entry["merchant"] == "Green Bowl" for entry in result.evidence)
    assert "Burger Barn" in result.answer


def test_merchant_by_item_empty(query_service: QueryService) -> None:
    result = query_service.find_merchant_by_item("sushi", as_of=TODAY)
    assert result.found is False
    assert result.evidence == []


def test_tool_registry_validates_arguments(query_service: QueryService) -> None:
    registry = ToolRegistry(query_service, as_of=TODAY)
    assert registry.call("get_purchases_by_date", {"date": "20 June"}).found is True
    with pytest.raises(ToolArgumentError):
        registry.call("get_purchases_by_date", {})
    with pytest.raises(ToolArgumentError):
        registry.call("get_purchases_by_date", {"date": "20 June", "extra": 1})
    with pytest.raises(ToolArgumentError):
        registry.call("find_merchant_by_item", {"item": "burger", "days": 0})
    with pytest.raises(ToolArgumentError):
        registry.call("unknown", {})


def test_nl_engine_rules_for_required_questions(query_service: QueryService) -> None:
    engine = NaturalLanguageQueryEngine(query_service, settings=NO_LLM)
    purchases = engine.answer("What food did i buy on 20 June 2026", as_of=TODAY)
    assert purchases.found is True
    assert purchases.tool_calls[0]["name"] == "get_purchases_by_date"
    assert purchases.evidence

    expenses = engine.answer("Give me total expenses for food on 20 June", as_of=TODAY)
    assert expenses.found is True
    assert expenses.tool_calls[0]["name"] == "get_food_expenses_by_date"
    assert "31.35" in expenses.answer

    merchant = engine.answer("Where did i buy hamburger from last 7 day", as_of=date(2026, 6, 21))
    assert merchant.found is True
    assert merchant.tool_calls[0]["name"] == "find_merchant_by_item"
    assert "Green Bowl" in merchant.answer


def test_nl_engine_empty_and_unparseable(query_service: QueryService) -> None:
    engine = NaturalLanguageQueryEngine(query_service, settings=NO_LLM)
    empty = engine.answer("What food did i buy yesterday", as_of=TODAY)
    assert empty.found is False
    assert empty.evidence == []
    assert "could not find" in empty.answer.lower()

    unclear = engine.answer("What did i buy sometime soon", as_of=TODAY)
    assert unclear.found is False
    assert unclear.tool_calls == []
    assert "could not understand" in unclear.answer.lower()
