"""Local OCR engine backed by the Tesseract command line tool."""

from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class OCRError(RuntimeError):
    """Raised when text extraction fails."""


class TesseractNotInstalledError(OCRError):
    """Raised when the Tesseract executable cannot be found."""


@dataclass(frozen=True)
class OCRResult:
    text: str
    engine: str
    duration_seconds: float
    confidence: float | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "text": self.text,
            "engine": self.engine,
            "duration_seconds": round(self.duration_seconds, 3),
            "confidence": self.confidence,
        }


class OCREngine(Protocol):
    name: str

    def extract_text(self, image_path: str | Path) -> OCRResult: ...


class TesseractEngine:
    """Run Tesseract locally with a bounded timeout."""

    name = "tesseract"

    def __init__(
        self,
        command: str = "tesseract",
        language: str = "eng",
        page_segmentation_mode: int = 6,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.command = command
        self.language = language
        self.page_segmentation_mode = page_segmentation_mode
        self.timeout_seconds = timeout_seconds

    def resolve_command(self) -> str:
        resolved = shutil.which(self.command)
        if not resolved:
            raise TesseractNotInstalledError(
                f"Tesseract executable not found: {self.command!r}. "
                "Install tesseract or set RECEIPT_AI_TESSERACT_CMD."
            )
        return resolved

    def is_available(self) -> bool:
        return shutil.which(self.command) is not None

    def version(self) -> str | None:
        try:
            result = subprocess.run(
                [self.resolve_command(), "--version"],
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except (OCRError, OSError, subprocess.SubprocessError):
            return None
        return result.stdout.splitlines()[0] if result.stdout else None

    def extract_text(self, image_path: str | Path) -> OCRResult:
        path = Path(image_path)
        if not path.exists():
            raise OCRError(f"image not found: {path}")
        command = self.resolve_command()
        start = time.perf_counter()
        try:
            result = subprocess.run(
                [
                    command,
                    str(path),
                    "stdout",
                    "--psm",
                    str(self.page_segmentation_mode),
                    "-l",
                    self.language,
                ],
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise OCRError(f"tesseract timed out after {self.timeout_seconds} seconds") from exc
        except OSError as exc:
            raise OCRError(f"tesseract failed to start: {exc}") from exc
        duration = time.perf_counter() - start
        if result.returncode != 0:
            detail = (result.stderr or "").strip()[:500]
            raise OCRError(f"tesseract exited with {result.returncode}: {detail}")
        return OCRResult(
            text=result.stdout,
            engine=self.name,
            duration_seconds=duration,
        )


def get_default_engine(language: str = "eng", command: str = "tesseract") -> TesseractEngine:
    return TesseractEngine(command=command, language=language)
