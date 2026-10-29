"""Receipt upload, review, history, and deletion routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, UploadFile

from receipt_ai.api.deps import get_receipt_service, get_repository
from receipt_ai.api.schemas import ReceiptPayload
from receipt_ai.db.repository import ReceiptRepository
from receipt_ai.services.receipts import ReceiptService

router = APIRouter(prefix="/api/receipts", tags=["receipts"])


@router.post("/upload")
async def upload_receipt(
    file: UploadFile = File(...),
    service: ReceiptService = Depends(get_receipt_service),
) -> dict[str, object]:
    limit = service.settings.max_upload_bytes
    content = await file.read(limit + 1)
    return service.process_upload(
        filename=file.filename or "",
        content_type=file.content_type,
        content=content,
    )


@router.get("")
def list_receipts(
    date_from: str | None = None,
    date_to: str | None = None,
    merchant: str | None = None,
    item: str | None = None,
    status: str | None = "saved",
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    repository: ReceiptRepository = Depends(get_repository),
) -> dict[str, object]:
    receipts = repository.list_receipts(
        date_from=date_from,
        date_to=date_to,
        merchant=merchant,
        item=item,
        status=status,
        limit=limit,
        offset=offset,
    )
    return {
        "receipts": [receipt.to_dict() for receipt in receipts],
        "count": len(receipts),
        "filters": {
            "date_from": date_from,
            "date_to": date_to,
            "merchant": merchant,
            "item": item,
            "status": status,
        },
    }


@router.get("/{receipt_id}")
def get_receipt(
    receipt_id: int,
    repository: ReceiptRepository = Depends(get_repository),
) -> dict[str, object]:
    receipt = repository.get_receipt(receipt_id)
    if receipt is None:
        from receipt_ai.db.repository import ReceiptNotFoundError

        raise ReceiptNotFoundError(receipt_id)
    return {"receipt": receipt.to_dict()}


@router.put("/{receipt_id}")
def save_receipt(
    receipt_id: int,
    payload: ReceiptPayload,
    service: ReceiptService = Depends(get_receipt_service),
) -> dict[str, object]:
    receipt = service.save_receipt(receipt_id, payload.to_draft())
    return {"receipt": receipt.to_dict()}


@router.delete("/{receipt_id}")
def delete_receipt(
    receipt_id: int,
    service: ReceiptService = Depends(get_receipt_service),
) -> dict[str, object]:
    deleted = service.delete_receipt(receipt_id)
    if not deleted:
        from receipt_ai.db.repository import ReceiptNotFoundError

        raise ReceiptNotFoundError(receipt_id)
    return {"deleted": True, "id": receipt_id}
