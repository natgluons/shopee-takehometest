"""Receipt upload, review, save, and indexing workflow."""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

from receipt_ai.api.validation import UploadInfo, validate_upload
from receipt_ai.config import Settings
from receipt_ai.db.models import Receipt, ReceiptDraft
from receipt_ai.db.repository import ReceiptRepository
from receipt_ai.ocr.engine import OCREngine
from receipt_ai.ocr.extract import extract_receipt
from receipt_ai.ocr.normalize import normalize_receipt
from receipt_ai.ocr.preprocess import preprocessed_image
from receipt_ai.ocr.validation import validate_extraction
from receipt_ai.vector.embedding import HashingEmbedder
from receipt_ai.vector.store import VectorStore

logger = logging.getLogger("receipt_ai.services.receipts")

VECTOR_COLLECTION = "receipts"


def receipt_external_id(receipt_id: int) -> str:
    return f"receipt:{receipt_id}"


class ReceiptService:
    """Coordinate OCR, normalization, persistence, and vector indexing."""

    def __init__(
        self,
        repository: ReceiptRepository,
        vector_store: VectorStore,
        ocr_engine: OCREngine,
        settings: Settings,
        embedder: HashingEmbedder | None = None,
        collection: str = VECTOR_COLLECTION,
    ) -> None:
        self.repository = repository
        self.vector_store = vector_store
        self.ocr_engine = ocr_engine
        self.settings = settings
        self.embedder = embedder or HashingEmbedder(settings.vector_dimension)
        self.collection = collection

    def _store_upload(self, info: UploadInfo, content: bytes) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        filename = f"{timestamp}_{uuid4().hex[:12]}{info.extension}"
        path = self.settings.upload_dir / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def process_upload(
        self,
        filename: str,
        content_type: str | None,
        content: bytes,
        today: date | None = None,
    ) -> dict[str, object]:
        info = validate_upload(
            filename,
            content_type,
            content,
            max_bytes=self.settings.max_upload_bytes,
        )
        stored_path = self._store_upload(info, content)
        try:
            with preprocessed_image(stored_path) as prepared:
                ocr_result = self.ocr_engine.extract_text(prepared)
            raw = extract_receipt(ocr_result.text)
            normalized = normalize_receipt(
                raw,
                default_currency="USD",
                today=today,
                source_image=str(stored_path),
            )
            draft, warnings = validate_extraction(normalized, today=today, status="pending")
            receipt = self.repository.create_receipt(draft)
        except Exception:
            stored_path.unlink(missing_ok=True)
            raise
        logger.info(
            "Processed receipt upload id=%s merchant=%s items=%s",
            receipt.id,
            receipt.merchant,
            receipt.item_count,
        )
        return {
            "receipt": receipt.to_dict(),
            "warnings": warnings,
            "ocr": ocr_result.to_dict(),
            "upload": info.to_dict(),
        }

    def save_receipt(self, receipt_id: int, draft: ReceiptDraft) -> Receipt:
        existing = self.repository.get_receipt(receipt_id)
        if existing is None:
            from receipt_ai.db.repository import ReceiptNotFoundError

            raise ReceiptNotFoundError(receipt_id)
        merged = ReceiptDraft(
            merchant=draft.merchant,
            purchase_date=draft.purchase_date,
            currency=draft.currency,
            subtotal_cents=draft.subtotal_cents,
            tax_cents=draft.tax_cents,
            total_cents=draft.total_cents,
            items=draft.items,
            source_image=draft.source_image or existing.source_image,
            raw_text=draft.raw_text or existing.raw_text,
            status="saved",
        )
        receipt = self.repository.update_receipt(receipt_id, merged)
        self.index_receipt(receipt)
        return receipt

    def create_receipt(self, draft: ReceiptDraft, index: bool = True) -> Receipt:
        receipt = self.repository.create_receipt(draft)
        if index and receipt.status == "saved":
            self.index_receipt(receipt)
        return receipt

    def delete_receipt(self, receipt_id: int) -> bool:
        receipt = self.repository.get_receipt(receipt_id)
        if receipt is None:
            return False
        deleted = self.repository.delete_receipt(receipt_id)
        if deleted:
            try:
                self.vector_store.delete(self.collection, receipt_external_id(receipt_id))
            except KeyError:
                logger.warning("Vector collection missing while deleting receipt %s", receipt_id)
        return deleted

    def index_receipt(self, receipt: Receipt) -> None:
        item_text = " ".join(item.description for item in receipt.items)
        content = (
            f"{receipt.merchant} {receipt.purchase_date} {item_text} "
            f"total {receipt.total_cents / 100:.2f} {receipt.currency}"
        )
        vector = self.embedder.embed(content)
        self.vector_store.upsert(
            self.collection,
            receipt_external_id(receipt.id),
            vector,
            content=content,
            metadata={
                "receipt_id": receipt.id,
                "merchant": receipt.merchant,
                "purchase_date": receipt.purchase_date,
                "total_cents": receipt.total_cents,
                "currency": receipt.currency,
                "item_count": receipt.item_count,
                "status": receipt.status,
            },
        )

    def rebuild_index(self) -> int:
        count = 0
        for receipt in self.repository.iter_receipts(status="saved"):
            self.index_receipt(receipt)
            count += 1
        return count
