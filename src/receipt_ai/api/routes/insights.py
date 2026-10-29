"""Aggregated spending insights route."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from receipt_ai.api.deps import get_repository
from receipt_ai.db.repository import ReceiptRepository

router = APIRouter(prefix="/api", tags=["insights"])


@router.get("/insights")
def get_insights(
    repository: ReceiptRepository = Depends(get_repository),
) -> dict[str, object]:
    return repository.insights(status="saved")
