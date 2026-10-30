from __future__ import annotations

import io

import pytest
from PIL import Image

from receipt_ai.api.validation import UploadValidationError, validate_upload


def png_bytes(width: int = 40, height: int = 20) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def test_valid_png() -> None:
    info = validate_upload("receipt.png", "image/png", png_bytes(), max_bytes=10_000_000)
    assert info.image_format == "PNG"
    assert info.width == 40
    assert info.height == 20
    assert info.content_type == "image/png"


def test_rejects_unsupported_extension() -> None:
    with pytest.raises(UploadValidationError) as error:
        validate_upload("receipt.gif", "image/png", png_bytes(), max_bytes=10_000_000)
    assert any("extension" in problem for problem in error.value.problems)


def test_rejects_unsupported_content_type() -> None:
    with pytest.raises(UploadValidationError) as error:
        validate_upload("receipt.png", "application/pdf", png_bytes(), max_bytes=10_000_000)
    assert any("content type" in problem for problem in error.value.problems)


def test_rejects_empty_and_oversized_files() -> None:
    with pytest.raises(UploadValidationError):
        validate_upload("receipt.png", "image/png", b"", max_bytes=100)
    with pytest.raises(UploadValidationError) as error:
        validate_upload("receipt.png", "image/png", png_bytes(), max_bytes=10)
    assert any("larger" in problem for problem in error.value.problems)


def test_rejects_corrupted_image() -> None:
    with pytest.raises(UploadValidationError):
        validate_upload(
            "receipt.png",
            "image/png",
            b"\x89PNG\r\n\x1a\nnot really a png",
            max_bytes=10_000_000,
        )


def test_rejects_extension_format_mismatch() -> None:
    with pytest.raises(UploadValidationError):
        validate_upload("receipt.png", "image/jpeg", png_bytes(), max_bytes=10_000_000)


def test_rejects_unsafe_filename() -> None:
    with pytest.raises(UploadValidationError):
        validate_upload("../", "image/png", png_bytes(), max_bytes=10_000_000)


def test_rejects_pixel_bomb() -> None:
    with pytest.raises(UploadValidationError) as error:
        validate_upload(
            "receipt.png",
            "image/png",
            png_bytes(200, 200),
            max_bytes=10_000_000,
            max_pixels=100,
        )
    assert any("pixel" in problem for problem in error.value.problems)
