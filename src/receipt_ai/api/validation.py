"""Upload validation for receipt images."""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError

ALLOWED_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
ALLOWED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})
EXTENSION_FORMATS = {
    ".jpg": "JPEG",
    ".jpeg": "JPEG",
    ".png": "PNG",
    ".webp": "WEBP",
}
FORMAT_CONTENT_TYPES = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}
MAGIC_PREFIXES = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF",),
}


class UploadValidationError(ValueError):
    """Raised when an uploaded file is not an acceptable receipt image."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("; ".join(problems))


@dataclass(frozen=True)
class UploadInfo:
    filename: str
    extension: str
    content_type: str
    image_format: str
    width: int
    height: int
    size_bytes: int

    def to_dict(self) -> dict[str, object]:
        return {
            "filename": self.filename,
            "extension": self.extension,
            "content_type": self.content_type,
            "image_format": self.image_format,
            "width": self.width,
            "height": self.height,
            "size_bytes": self.size_bytes,
        }


def safe_filename(filename: str) -> str:
    """Return just the base name, rejecting empty and traversal style names."""
    name = Path(filename or "").name.strip()
    if not name or name in {".", ".."}:
        raise UploadValidationError(["filename is missing or unsafe"])
    return name


def _check_magic(content: bytes, content_type: str) -> None:
    prefixes = MAGIC_PREFIXES.get(content_type, ())
    if content_type == "image/webp":
        if not (content.startswith(b"RIFF") and content[8:12] == b"WEBP"):
            raise UploadValidationError(["file content is not a valid WEBP image"])
        return
    if prefixes and not any(content.startswith(prefix) for prefix in prefixes):
        raise UploadValidationError(["file content does not match the declared image type"])


def validate_upload(
    filename: str,
    content_type: str | None,
    content: bytes,
    max_bytes: int,
    max_pixels: int = 40_000_000,
) -> UploadInfo:
    """Validate extension, MIME type, size, magic bytes, and decoded dimensions."""
    name = safe_filename(filename)
    extension = Path(name).suffix.lower()
    problems: list[str] = []
    if extension not in ALLOWED_EXTENSIONS:
        problems.append(f"unsupported file extension: {extension or 'none'}")
    normalized_type = (content_type or "").split(";")[0].strip().lower()
    if normalized_type not in ALLOWED_CONTENT_TYPES:
        problems.append(f"unsupported content type: {normalized_type or 'none'}")
    if not content:
        problems.append("file is empty")
    elif len(content) > max_bytes:
        problems.append(f"file is larger than the {max_bytes} byte limit")
    if problems:
        raise UploadValidationError(problems)

    _check_magic(content, normalized_type)
    try:
        with Image.open(io.BytesIO(content)) as probe:
            probe.verify()
        with Image.open(io.BytesIO(content)) as image:
            image_format = image.format or ""
            width, height = image.size
            mode = image.mode
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise UploadValidationError([f"image could not be decoded: {exc}"]) from exc

    if image_format not in FORMAT_CONTENT_TYPES:
        raise UploadValidationError([f"unsupported image format: {image_format or 'unknown'}"])
    expected_extension_format = EXTENSION_FORMATS.get(extension)
    if expected_extension_format and expected_extension_format != image_format:
        raise UploadValidationError(
            [
                f"extension {extension} does not match image format {image_format}"
            ]
        )
    if width < 1 or height < 1:
        raise UploadValidationError(["image dimensions must be positive"])
    if width * height > max_pixels:
        raise UploadValidationError([f"image exceeds the {max_pixels} pixel limit"])
    if mode not in {"1", "L", "LA", "P", "RGB", "RGBA", "CMYK"}:
        raise UploadValidationError([f"unsupported image mode: {mode}"])

    return UploadInfo(
        filename=name,
        extension=extension,
        content_type=FORMAT_CONTENT_TYPES[image_format],
        image_format=image_format,
        width=width,
        height=height,
        size_bytes=len(content),
    )
