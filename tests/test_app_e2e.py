from __future__ import annotations

import io
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from receipt_ai.api.main import create_app
from receipt_ai.config import Settings


def png_bytes(width: int = 400, height: int = 200) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def client(tmp_path: Path, fake_ocr) -> TestClient:
    settings = Settings(
        data_dir=tmp_path,
        db_path=tmp_path / "receipts.db",
        vector_db_path=tmp_path / "vectors.db",
        upload_dir=tmp_path / "uploads",
        max_upload_bytes=5 * 1024 * 1024,
    )
    app = create_app(settings=settings, ocr_engine=fake_ocr)
    with TestClient(app) as test_client:
        test_client.app.state.test_settings = settings
        yield test_client


def receipt_text(purchase_date: str, merchant: str = "Green Bowl") -> str:
    return (
        f"{merchant}\n"
        f"Date: {purchase_date}\n"
        "2 x Hamburger 20.00\n"
        "Fries 5.00\n"
        "Coffee 3.50\n"
        "Subtotal 28.50\n"
        "Tax 2.85\n"
        "TOTAL $31.35\n"
        "Thank you\n"
    )


def upload(client: TestClient, text: str, filename: str = "receipt.png") -> dict:
    client.app.state.ocr_engine.text = text
    response = client.post(
        "/api/receipts/upload",
        files={"file": (filename, png_bytes(), "image/png")},
    )
    return {"response": response, "payload": response.json()}


def save_payload(receipt: dict) -> dict:
    return {
        "merchant": receipt["merchant"],
        "purchase_date": receipt["purchase_date"],
        "currency": receipt["currency"],
        "subtotal_cents": receipt["subtotal_cents"],
        "tax_cents": receipt["tax_cents"],
        "total_cents": receipt["total_cents"],
        "source_image": receipt["source_image"],
        "raw_text": receipt["raw_text"],
        "status": "saved",
        "items": [
            {
                "description": item["description"],
                "quantity": item["quantity"],
                "unit_price_cents": item["unit_price_cents"],
                "line_total_cents": item["line_total_cents"],
            }
            for item in receipt["items"]
        ],
    }


def test_end_to_end_receipt_flow(client: TestClient) -> None:
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    upload_result = upload(client, receipt_text(yesterday))
    response = upload_result["response"]
    payload = upload_result["payload"]
    assert response.status_code == 200
    receipt = payload["receipt"]
    assert receipt["status"] == "pending"
    assert receipt["merchant"] == "Green Bowl"
    assert receipt["purchase_date"] == yesterday
    assert receipt["total_cents"] == 3135
    assert len(receipt["items"]) == 3
    assert payload["upload"]["image_format"] == "PNG"

    saved_response = client.put(f"/api/receipts/{receipt['id']}", json=save_payload(receipt))
    assert saved_response.status_code == 200
    saved = saved_response.json()["receipt"]
    assert saved["status"] == "saved"
    assert client.app.state.vector_store.count("receipts") == 1

    listed = client.get("/api/receipts").json()
    assert listed["count"] == 1
    assert listed["receipts"][0]["id"] == receipt["id"]

    assert (
        client.get(f"/api/receipts?date_from={yesterday}&date_to={yesterday}").json()["count"] == 1
    )
    assert client.get("/api/receipts?merchant=green").json()["count"] == 1
    assert client.get("/api/receipts?item=hamburger").json()["count"] == 1
    assert client.get("/api/receipts?item=sushi").json()["count"] == 0

    detail = client.get(f"/api/receipts/{receipt['id']}")
    assert detail.status_code == 200
    assert detail.json()["receipt"]["merchant"] == "Green Bowl"

    insights = client.get("/api/insights").json()
    assert insights["receipt_count"] == 1
    assert insights["totals"][0]["total_cents"] == 3135
    assert insights["by_merchant"][0]["merchant"] == "Green Bowl"


def test_end_to_end_required_questions(client: TestClient) -> None:
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    result = upload(client, receipt_text(yesterday))
    receipt = result["payload"]["receipt"]
    client.put(f"/api/receipts/{receipt['id']}", json=save_payload(receipt))

    purchases = client.post("/api/query", json={"question": "What food did I buy yesterday"})
    assert purchases.status_code == 200
    purchases_body = purchases.json()
    assert purchases_body["found"] is True
    assert purchases_body["tool_calls"][0]["name"] == "get_purchases_by_date"
    assert purchases_body["evidence"]

    expenses = client.post(
        "/api/query",
        json={"question": f"Give me total expenses for food on {yesterday}"},
    )
    assert expenses.status_code == 200
    expenses_body = expenses.json()
    assert expenses_body["found"] is True
    assert "31.35" in expenses_body["answer"]
    assert expenses_body["tool_calls"][0]["name"] == "get_food_expenses_by_date"

    merchant = client.post(
        "/api/query",
        json={"question": "Where did I buy hamburger from last 7 days"},
    )
    assert merchant.status_code == 200
    merchant_body = merchant.json()
    assert merchant_body["found"] is True
    assert "Green Bowl" in merchant_body["answer"]
    assert merchant_body["tool_calls"][0]["name"] == "find_merchant_by_item"
    assert any(entry["type"] == "item" for entry in merchant_body["evidence"])


def test_query_empty_result_and_as_of(client: TestClient) -> None:
    response = client.post(
        "/api/query",
        json={
            "question": "What food did I buy yesterday",
            "as_of": "2026-06-21",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["found"] is False
    assert body["evidence"] == []
    assert body["as_of"] == "2026-06-21"
    assert "could not find" in body["answer"].lower()


def test_upload_validation_and_cleanup(client: TestClient) -> None:
    settings = client.app.state.test_settings
    response = client.post(
        "/api/receipts/upload",
        files={"file": ("receipt.txt", b"not an image", "text/plain")},
    )
    assert response.status_code == 422
    assert "problems" in response.json()

    future = (date.today() + timedelta(days=30)).isoformat()
    result = upload(client, receipt_text(future))
    assert result["response"].status_code == 422
    assert list(settings.upload_dir.glob("*")) == []


def test_delete_receipt_removes_vector(client: TestClient) -> None:
    result = upload(client, receipt_text("2026-06-20"))
    receipt = result["payload"]["receipt"]
    client.put(f"/api/receipts/{receipt['id']}", json=save_payload(receipt))
    assert client.app.state.vector_store.count("receipts") == 1

    delete_response = client.delete(f"/api/receipts/{receipt['id']}")
    assert delete_response.status_code == 200
    assert client.app.state.vector_store.count("receipts") == 0
    assert client.get("/api/receipts").json()["count"] == 0
    assert client.delete(f"/api/receipts/{receipt['id']}").status_code == 404


def test_health_ui_and_tools(client: TestClient) -> None:
    assert client.get("/healthz").json()["status"] == "ok"
    ready = client.get("/readyz")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"

    for path, marker in (
        ("/", "Upload a food receipt"),
        ("/history", "Receipt history"),
        ("/query", "Ask your receipt history"),
    ):
        page = client.get(path)
        assert page.status_code == 200
        assert marker in page.text
    assert client.get("/static/styles.css").status_code == 200
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/history.js").status_code == 200
    assert client.get("/static/query.js").status_code == 200

    tools = client.get("/api/tools").json()["tools"]
    assert {tool["function"]["name"] for tool in tools} == {
        "get_purchases_by_date",
        "get_food_expenses_by_date",
        "find_merchant_by_item",
    }


def test_vector_search_is_persisted_and_searchable(client: TestClient) -> None:
    result = upload(client, receipt_text("2026-06-20"))
    receipt = result["payload"]["receipt"]
    client.put(f"/api/receipts/{receipt['id']}", json=save_payload(receipt))

    from receipt_ai.vector.search import search_by_text

    store = client.app.state.vector_store
    embedder = client.app.state.receipt_service.embedder
    matches = search_by_text(store, "receipts", "Green Bowl hamburger", embedder, k=1)
    assert matches
    assert matches[0].external_id == f"receipt:{receipt['id']}"
    assert matches[0].metadata["merchant"] == "Green Bowl"
