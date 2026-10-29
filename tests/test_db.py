from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from receipt_ai.db.models import (
    MonetaryIntegrityError,
    ReceiptDraft,
    ReceiptItemInput,
    ReceiptValidationError,
)
from receipt_ai.db.repository import ReceiptNotFoundError, ReceiptRepository


@pytest.fixture
def repository(tmp_path: Path) -> ReceiptRepository:
    repo = ReceiptRepository(tmp_path / "receipts.db")
    yield repo
    repo.close()


def draft(**overrides: object) -> ReceiptDraft:
    values: dict[str, object] = {
        "merchant": "Green Bowl",
        "purchase_date": "2026-06-20",
        "tax_cents": 50,
        "items": [
            ReceiptItemInput("Hamburger", 1000),
            ReceiptItemInput("Fries", 500),
        ],
        "status": "saved",
    }
    values.update(overrides)
    return ReceiptDraft(**values)  # type: ignore[arg-type]


def test_create_computes_totals(repository: ReceiptRepository) -> None:
    receipt = repository.create_receipt(draft())
    assert receipt.subtotal_cents == 1500
    assert receipt.tax_cents == 50
    assert receipt.total_cents == 1550
    assert receipt.item_count == 2
    assert receipt.items[0].unit_price_cents == 1000


def test_rejects_subtotal_mismatch(repository: ReceiptRepository) -> None:
    with pytest.raises(MonetaryIntegrityError):
        repository.create_receipt(draft(subtotal_cents=1400))
    assert repository.count_receipts() == 0


def test_rejects_total_mismatch(repository: ReceiptRepository) -> None:
    with pytest.raises(MonetaryIntegrityError):
        repository.create_receipt(draft(total_cents=9999))
    assert repository.count_receipts() == 0


def test_rejects_invalid_domain_values(repository: ReceiptRepository) -> None:
    with pytest.raises(ReceiptValidationError):
        repository.create_receipt(draft(purchase_date="20-06-2026"))
    with pytest.raises(ReceiptValidationError):
        repository.create_receipt(draft(merchant="   "))
    with pytest.raises(ReceiptValidationError):
        repository.create_receipt(draft(currency="US"))
    with pytest.raises(ReceiptValidationError):
        repository.create_receipt(draft(tax_cents=-1))
    with pytest.raises(ReceiptValidationError):
        repository.create_receipt(draft(items=[ReceiptItemInput("Bad", 100, quantity=0)]))


def test_database_constraints_are_enforced(repository: ReceiptRepository) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        repository.connection.execute(
            """
            INSERT INTO receipts(merchant, purchase_date, currency, subtotal_cents, tax_cents,
                                 total_cents)
            VALUES('Bad', '2026-06-20', 'USD', 100, 0, 50)
            """
        )


def test_delete_cascades_items(repository: ReceiptRepository) -> None:
    receipt = repository.create_receipt(draft())
    assert repository.delete_receipt(receipt.id) is True
    assert repository.delete_receipt(receipt.id) is False
    count = repository.connection.execute("SELECT COUNT(*) AS count FROM receipt_items").fetchone()[
        "count"
    ]
    assert count == 0


def test_update_replaces_items_and_totals(repository: ReceiptRepository) -> None:
    receipt = repository.create_receipt(draft(status="pending"))
    updated = repository.update_receipt(
        receipt.id,
        draft(
            merchant="Blue Cafe",
            purchase_date="2026-06-21",
            tax_cents=100,
            items=[ReceiptItemInput("Coffee", 400)],
            status="saved",
        ),
    )
    assert updated.merchant == "Blue Cafe"
    assert updated.purchase_date == "2026-06-21"
    assert updated.subtotal_cents == 400
    assert updated.total_cents == 500
    assert updated.status == "saved"
    assert [item.description for item in updated.items] == ["Coffee"]
    with pytest.raises(ReceiptNotFoundError):
        repository.update_receipt(999, draft())


def test_list_filters(repository: ReceiptRepository) -> None:
    repository.create_receipt(draft())
    repository.create_receipt(
        draft(
            merchant="Blue Cafe",
            purchase_date="2026-06-21",
            items=[ReceiptItemInput("Coffee", 400)],
            status="saved",
        )
    )
    repository.create_receipt(
        draft(
            merchant="Pending Place",
            purchase_date="2026-06-22",
            status="pending",
        )
    )
    assert len(repository.list_receipts()) == 2
    assert len(repository.list_receipts(status=None)) == 3
    assert len(repository.list_receipts(merchant="blue")) == 1
    assert len(repository.list_receipts(item="hamburger")) == 1
    assert len(repository.list_receipts(date_from="2026-06-21", date_to="2026-06-21")) == 1


def test_total_expenses_groups_by_currency(repository: ReceiptRepository) -> None:
    repository.create_receipt(draft())
    repository.create_receipt(draft(currency="EUR", items=[ReceiptItemInput("Pizza", 800)]))
    result = repository.total_expenses("2026-06-01", "2026-06-30")
    assert result["found"] is True
    assert result["receipt_count"] == 2
    totals = {item["currency"]: item["total_cents"] for item in result["currencies"]}
    assert totals == {"EUR": 850, "USD": 1550}
    empty = repository.total_expenses("2026-07-01", "2026-07-31")
    assert empty["found"] is False
    assert empty["receipt_count"] == 0


def test_item_lookup_with_date_window(repository: ReceiptRepository) -> None:
    repository.create_receipt(draft())
    repository.create_receipt(
        draft(
            merchant="Burger Barn",
            purchase_date="2026-06-30",
            items=[ReceiptItemInput("Cheeseburger", 900)],
        )
    )
    results = repository.receipts_for_item("burger", "2026-06-01", "2026-06-30")
    assert [receipt.merchant for receipt in results] == ["Burger Barn", "Green Bowl"]
    assert repository.receipts_for_item("burger", "2026-07-01", "2026-07-31") == []


def test_purchases_on(repository: ReceiptRepository) -> None:
    repository.create_receipt(draft())
    repository.create_receipt(draft(purchase_date="2026-06-21"))
    assert len(repository.purchases_on("2026-06-20")) == 1
    assert repository.purchases_on("2026-06-19") == []


def test_insights(repository: ReceiptRepository) -> None:
    repository.create_receipt(draft())
    repository.create_receipt(
        draft(
            merchant="Blue Cafe",
            purchase_date="2026-06-21",
            items=[ReceiptItemInput("Coffee", 400, category="drinks")],
        )
    )
    insights = repository.insights()
    assert insights["receipt_count"] == 2
    assert insights["totals"][0]["total_cents"] == 2000
    assert insights["by_day"][0]["date"] == "2026-06-21"
    assert insights["by_merchant"][0]["merchant"] == "Green Bowl"
    assert any(category["category"] == "drinks" for category in insights["by_category"])
