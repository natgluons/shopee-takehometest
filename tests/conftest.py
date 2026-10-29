"""Shared pytest fixtures and path helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from receipt_ai.ocr.engine import OCRResult

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture
def sample_customers_csv(tmp_path: Path) -> Path:
    rows = [
        "Index,Customer Id,First Name,Last Name,Company,City,Country,Phone 1,Phone 2,Email,Subscription Date,Website",
        "1,ABC001,Ada,Lovelace,Analytical Engines,London,United Kingdom,111-1111,222-2222,ada@example.com,2020-01-15,https://example.com",
        "2,ABC002,Grace,Hopper,Navy Systems,Arlington,United States,333-3333,,grace@navy.mil,2021-06-20,https://navy.mil",
        "3,ABC003,Alan,Turing,Bletchley Park,Bletchley,United Kingdom,444-4444,,alan@example.org,2022-03-01,https://example.org",
        "4,ABC003,Alan,Turing,Bletchley Park,Bletchley,United Kingdom,444-4444,,alan@example.org,2022-03-01,https://example.org",
    ]
    path = tmp_path / "customers.csv"
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return path


class FakeOCREngine:
    """Deterministic OCR engine for tests that do not need Tesseract."""

    name = "fake"

    def __init__(self, text: str = "") -> None:
        self.text = text
        self.calls = 0

    def extract_text(self, image_path: object) -> OCRResult:
        self.calls += 1
        return OCRResult(text=self.text, engine=self.name, duration_seconds=0.01)


@pytest.fixture
def fake_ocr() -> FakeOCREngine:
    return FakeOCREngine()
