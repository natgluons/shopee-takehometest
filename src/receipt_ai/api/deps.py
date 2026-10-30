"""Shared FastAPI dependencies backed by application state."""

from __future__ import annotations

from fastapi import Request

from receipt_ai.config import Settings
from receipt_ai.db.repository import ReceiptRepository
from receipt_ai.vector.store import VectorStore


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_repository(request: Request) -> ReceiptRepository:
    return request.app.state.repository


def get_vector_store(request: Request) -> VectorStore:
    return request.app.state.vector_store
