"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser() if value else default


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    db_path: Path
    vector_db_path: Path
    upload_dir: Path
    max_upload_bytes: int = 10 * 1024 * 1024
    ocr_lang: str = "eng"
    tesseract_cmd: str = "tesseract"
    vector_dimension: int = 256
    openai_api_key: str | None = field(default=None, repr=False)
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls) -> Settings:
        data_dir = _env_path("RECEIPT_AI_DATA_DIR", Path("data"))
        db_path = _env_path("RECEIPT_AI_DB_PATH", data_dir / "receipts.db")
        vector_db_path = _env_path("RECEIPT_AI_VECTOR_DB_PATH", data_dir / "vectors.db")
        upload_dir = _env_path("RECEIPT_AI_UPLOAD_DIR", data_dir / "uploads")
        return cls(
            data_dir=data_dir,
            db_path=db_path,
            vector_db_path=vector_db_path,
            upload_dir=upload_dir,
            max_upload_bytes=_env_int("RECEIPT_AI_MAX_UPLOAD_BYTES", 10 * 1024 * 1024),
            ocr_lang=os.environ.get("RECEIPT_AI_OCR_LANG", "eng"),
            tesseract_cmd=os.environ.get("RECEIPT_AI_TESSERACT_CMD", "tesseract"),
            vector_dimension=_env_int("RECEIPT_AI_VECTOR_DIMENSION", 256),
            openai_api_key=os.environ.get("OPENAI_API_KEY") or None,
            openai_base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip(
                "/"
            ),
            openai_model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            llm_timeout_seconds=float(os.environ.get("RECEIPT_AI_LLM_TIMEOUT", "30")),
        )

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.vector_db_path.parent.mkdir(parents=True, exist_ok=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "data_dir": str(self.data_dir),
            "db_path": str(self.db_path),
            "vector_db_path": str(self.vector_db_path),
            "upload_dir": str(self.upload_dir),
            "max_upload_bytes": self.max_upload_bytes,
            "ocr_lang": self.ocr_lang,
            "vector_dimension": self.vector_dimension,
            "llm_configured": bool(self.openai_api_key),
            "openai_model": self.openai_model if self.openai_api_key else None,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
