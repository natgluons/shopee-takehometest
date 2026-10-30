"""Image preprocessing to improve OCR on phone photos of receipts."""

from __future__ import annotations

import tempfile
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Iterator

from PIL import Image, ImageFilter, ImageOps

DEFAULT_MAX_DIMENSION = 2200
DEFAULT_MIN_DIMENSION = 1200


def _target_size(width: int, height: int, min_dimension: int, max_dimension: int) -> tuple[int, int]:
    largest = max(width, height)
    if largest > max_dimension:
        scale = max_dimension / largest
    elif largest < min_dimension:
        scale = min_dimension / largest
    else:
        return width, height
    return max(1, round(width * scale)), max(1, round(height * scale))


def preprocess_image(
    source: str | Path,
    destination: str | Path | None = None,
    min_dimension: int = DEFAULT_MIN_DIMENSION,
    max_dimension: int = DEFAULT_MAX_DIMENSION,
) -> Path:
    """Grayscale, orient, scale, and sharpen an image for OCR."""
    source_path = Path(source)
    if not source_path.exists():
        raise FileNotFoundError(f"image not found: {source_path}")
    with Image.open(source_path) as image:
        oriented = ImageOps.exif_transpose(image)
        grayscale = oriented.convert("L")
        width, height = _target_size(
            grayscale.width, grayscale.height, min_dimension, max_dimension
        )
        if (width, height) != grayscale.size:
            resampling = Image.Resampling.LANCZOS
            grayscale = grayscale.resize((width, height), resampling)
        grayscale = grayscale.filter(ImageFilter.MedianFilter(size=3))
        grayscale = ImageOps.autocontrast(grayscale, cutoff=1)
        grayscale = grayscale.filter(ImageFilter.UnsharpMask(radius=1.5, percent=140, threshold=3))

    if destination is None:
        handle = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        handle.close()
        destination_path = Path(handle.name)
    else:
        destination_path = Path(destination)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
    grayscale.save(destination_path, format="PNG", optimize=True)
    return destination_path


@contextmanager
def preprocessed_image(source: str | Path, **kwargs: object) -> Iterator[Path]:
    """Yield a temporary preprocessed image and remove it afterwards."""
    path = preprocess_image(source, **kwargs)  # type: ignore[arg-type]
    try:
        yield path
    finally:
        if path.exists():
            path.unlink(missing_ok=True)
