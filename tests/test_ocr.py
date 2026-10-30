from __future__ import annotations

import shutil
from datetime import date

import pytest
from PIL import Image, ImageDraw

from receipt_ai.money import MoneyParseError, parse_amount_to_cents
from receipt_ai.ocr.engine import TesseractEngine
from receipt_ai.ocr.extract import extract_receipt
from receipt_ai.ocr.normalize import (
    NormalizationError,
    normalize_receipt,
    parse_quantity,
    parse_receipt_date,
)
from receipt_ai.ocr.preprocess import preprocess_image
from receipt_ai.ocr.validation import ExtractionValidationError, validate_extraction

RECEIPT_TEXT = """GREEN BOWL
123 Main Street
Date: 20 June 2026
2 x Hamburger 20.00
Fries 5.00
Coffee 3.50
Subtotal 28.50
Tax 2.85
TOTAL $31.35
Thank you"""

TODAY = date(2026, 10, 29)


def test_parse_amount_formats() -> None:
    assert parse_amount_to_cents("$1,234.56") == 123456
    assert parse_amount_to_cents("1.234,56") == 123456
    assert parse_amount_to_cents("(5.00)") == -500
    assert parse_amount_to_cents("USD 12.5") == 1250
    assert parse_amount_to_cents(12.5) == 1250
    with pytest.raises(MoneyParseError):
        parse_amount_to_cents("not money")


def test_parse_receipt_dates() -> None:
    assert parse_receipt_date("2026-06-20", today=TODAY)[0] == "2026-06-20"
    assert parse_receipt_date("20 June 2026", today=TODAY)[0] == "2026-06-20"
    assert parse_receipt_date("June 20, 2026", today=TODAY)[0] == "2026-06-20"
    assert parse_receipt_date("20/06/2026", today=TODAY)[0] == "2026-06-20"
    assert parse_receipt_date("06/20/2026", today=TODAY)[0] == "2026-06-20"
    assert parse_receipt_date("20 June", today=TODAY)[0] == "2026-06-20"
    iso, warnings = parse_receipt_date("05/06/2026", today=TODAY)
    assert iso == "2026-05-06"
    assert warnings
    with pytest.raises(NormalizationError):
        parse_receipt_date("not a date", today=TODAY)


def test_parse_quantity() -> None:
    assert parse_quantity("2") == 2.0
    assert parse_quantity("2,5") == 2.5
    with pytest.raises(NormalizationError):
        parse_quantity("0")


def test_extract_receipt_fields() -> None:
    raw = extract_receipt(RECEIPT_TEXT)
    assert raw.merchant == "GREEN BOWL"
    assert raw.date == "20 June 2026"
    assert raw.total == "$31.35"
    assert raw.subtotal == "28.50"
    assert raw.tax == "2.85"
    assert raw.currency == "USD"
    assert [item.description for item in raw.items] == ["Hamburger", "Fries", "Coffee"]
    assert raw.items[0].quantity == "2"


def test_normalize_and_validate_success() -> None:
    normalized = normalize_receipt(
        extract_receipt(RECEIPT_TEXT), today=TODAY, source_image="receipt.png"
    )
    assert normalized.purchase_date == "2026-06-20"
    assert normalized.total_cents == 3135
    assert normalized.subtotal_cents == 2850
    assert normalized.tax_cents == 285
    assert len(normalized.items) == 3
    draft, warnings = validate_extraction(normalized, today=TODAY)
    assert draft.merchant == "GREEN BOWL"
    assert draft.total_cents == 3135
    assert draft.status == "pending"
    assert warnings == []


def test_validation_rejects_future_date() -> None:
    text = "GREEN BOWL\nDate: 20 June 2027\nBurger 10.00\nTOTAL 10.00"
    normalized = normalize_receipt(extract_receipt(text), today=TODAY)
    with pytest.raises(ExtractionValidationError) as error:
        validate_extraction(normalized, today=TODAY)
    assert any("future" in problem for problem in error.value.problems)


def test_validation_rejects_missing_date_and_total() -> None:
    normalized = normalize_receipt(extract_receipt("GREEN BOWL\nBurger"), today=TODAY)
    with pytest.raises(ExtractionValidationError) as error:
        validate_extraction(normalized, today=TODAY)
    assert any("purchase date" in problem for problem in error.value.problems)
    assert any("total" in problem for problem in error.value.problems)


def test_validation_rejects_inconsistent_totals() -> None:
    text = "GREEN BOWL\nDate: 20 June 2026\nBurger 10.00\nSubtotal 10.00\nTax 1.00\nTOTAL 20.00"
    normalized = normalize_receipt(extract_receipt(text), today=TODAY)
    with pytest.raises(ExtractionValidationError) as error:
        validate_extraction(normalized, today=TODAY)
    assert any("does not equal" in problem for problem in error.value.problems)


def test_validation_warns_for_missing_items() -> None:
    text = "GREEN BOWL\nDate: 20 June 2026\nTOTAL 10.00"
    normalized = normalize_receipt(extract_receipt(text), today=TODAY)
    draft, warnings = validate_extraction(normalized, today=TODAY)
    assert draft.total_cents == 1000
    assert any("no line items" in warning for warning in warnings)


def test_preprocess_image(tmp_path) -> None:
    source = tmp_path / "receipt.png"
    image = Image.new("RGB", (200, 100), "white")
    draw = ImageDraw.Draw(image)
    draw.text((10, 10), "GREEN BOWL", fill="black")
    image.save(source)
    prepared = preprocess_image(source, tmp_path / "prepared.png", min_dimension=400)
    with Image.open(prepared) as result:
        assert result.mode == "L"
        assert max(result.size) == 400
    assert prepared.exists()


@pytest.mark.skipif(not shutil.which("tesseract"), reason="Tesseract is not installed")
def test_tesseract_engine_extracts_text(tmp_path) -> None:
    source = tmp_path / "receipt.png"
    image = Image.new("RGB", (600, 300), "white")
    draw = ImageDraw.Draw(image)
    draw.text((30, 40), "GREEN BOWL", fill="black")
    draw.text((30, 90), "TOTAL 12.34", fill="black")
    image.save(source)
    engine = TesseractEngine()
    result = engine.extract_text(source)
    assert "GREEN" in result.text.upper()
    assert result.duration_seconds >= 0
