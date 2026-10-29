"""Drive the three required questions through the running API."""

from __future__ import annotations

import io
import os
from datetime import date, timedelta

import httpx
from PIL import Image, ImageDraw, ImageFont

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def load_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return ImageFont.truetype(candidate, size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def build_receipt_image(purchase_date: str) -> bytes:
    image = Image.new("RGB", (900, 520), "white")
    draw = ImageDraw.Draw(image)
    font = load_font(28)
    lines = [
        "GREEN BOWL",
        "123 Main Street",
        f"Date: {purchase_date}",
        "2 x Hamburger 20.00",
        "Fries 5.00",
        "Coffee 3.50",
        "Subtotal 28.50",
        "Tax 2.85",
        "TOTAL $31.35",
        "Thank you",
    ]
    for index, line in enumerate(lines):
        draw.text((40, 30 + index * 44), line, fill="black", font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


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


def ask(client: httpx.Client, question: str, purchase_date: str) -> None:
    response = client.post(
        "/api/query",
        json={"question": question, "as_of": date.today().isoformat()},
    )
    response.raise_for_status()
    body = response.json()
    print(f"\nQ: {question}")
    print(f"A: {body['answer']}")
    print(
        f"   engine={body['engine']} found={body['found']} "
        f"tool={body['tool_calls'][0]['name'] if body['tool_calls'] else 'none'} "
        f"evidence_rows={len(body['evidence'])}"
    )
    if body.get("warnings"):
        print(f"   warnings={body['warnings']}")
    if not body["found"]:
        print("   (empty result is expected when the date window has no receipts)")


def main() -> int:
    purchase_date = (date.today() - timedelta(days=1)).isoformat()
    with httpx.Client(base_url=BASE_URL, timeout=60.0) as client:
        health = client.get("/healthz")
        health.raise_for_status()
        print(f"Application is healthy at {BASE_URL}")

        image = build_receipt_image(purchase_date)
        files = {"file": ("demo_receipt.png", image, "image/png")}
        upload = client.post("/api/receipts/upload", files=files)
        upload.raise_for_status()
        uploaded = upload.json()
        receipt = uploaded["receipt"]
        print(
            f"\nUploaded receipt #{receipt['id']} for {receipt['merchant']} "
            f"on {receipt['purchase_date']} with {len(receipt['items'])} items "
            f"totaling {receipt['total']} {receipt['currency']}"
        )
        if uploaded.get("warnings"):
            print(f"Extraction warnings: {uploaded['warnings']}")

        saved = client.put(f"/api/receipts/{receipt['id']}", json=save_payload(receipt))
        saved.raise_for_status()
        print(f"Saved receipt #{receipt['id']} and indexed it for retrieval")

        ask(client, "What food did I buy yesterday?", purchase_date)
        ask(client, f"Give me total expenses for food on {purchase_date}", purchase_date)
        ask(client, "Where did I buy hamburger from last 7 days?", purchase_date)

        insights = client.get("/api/insights").json()
        totals = (
            ", ".join(f"{item['total']} {item['currency']}" for item in insights["totals"])
            or "none"
        )
        print(f"\nInsights: {insights['receipt_count']} saved receipts, totals: {totals}")
        print(f"Open {BASE_URL} for the upload, history, and query pages.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
