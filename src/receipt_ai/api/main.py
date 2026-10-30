"""FastAPI application factory."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import receipt_ai
from receipt_ai.api.routes import insights as insights_routes
from receipt_ai.api.routes import query as query_routes
from receipt_ai.api.routes import receipts as receipt_routes
from receipt_ai.api.validation import UploadValidationError
from receipt_ai.config import Settings, get_settings
from receipt_ai.db.models import ReceiptValidationError
from receipt_ai.db.repository import ReceiptNotFoundError, ReceiptRepository
from receipt_ai.money import MoneyParseError
from receipt_ai.ocr.engine import OCREngine, get_default_engine
from receipt_ai.ocr.validation import ExtractionValidationError
from receipt_ai.services.nl_query import NaturalLanguageQueryEngine, QueryEngineError
from receipt_ai.services.query import QueryService
from receipt_ai.services.receipts import ReceiptService
from receipt_ai.vector.store import CollectionNotFoundError, VectorStore
from receipt_ai.vector.validation import VectorValidationError

logger = logging.getLogger("receipt_ai")

VECTOR_COLLECTION = "receipts"
UI_DIR = Path(__file__).resolve().parent.parent / "ui"


def create_app(
    settings: Settings | None = None,
    repository: ReceiptRepository | None = None,
    vector_store: VectorStore | None = None,
    ocr_engine: OCREngine | None = None,
) -> FastAPI:
    active_settings = settings or get_settings()
    active_settings.ensure_directories()

    app = FastAPI(
        title="Receipt AI",
        version=receipt_ai.__version__,
        description=(
            "Upload food receipts, extract fields with local OCR, store them in SQLite, "
            "and answer natural-language questions with grounded tools."
        ),
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    repository = repository or ReceiptRepository(active_settings.db_path)
    vector_store = vector_store or VectorStore(active_settings.vector_db_path)
    try:
        vector_store.create_collection(VECTOR_COLLECTION, active_settings.vector_dimension)
    except Exception:
        logger.exception("Failed to initialize the receipt vector collection")
        raise

    active_engine = ocr_engine or get_default_engine(
        language=active_settings.ocr_lang, command=active_settings.tesseract_cmd
    )
    app.state.settings = active_settings
    app.state.repository = repository
    app.state.vector_store = vector_store
    app.state.ocr_engine = active_engine
    app.state.receipt_service = ReceiptService(
        repository=repository,
        vector_store=vector_store,
        ocr_engine=active_engine,
        settings=active_settings,
    )
    app.state.query_service = QueryService(repository)
    app.state.nl_query_engine = NaturalLanguageQueryEngine(
        app.state.query_service, settings=active_settings
    )
    templates = Jinja2Templates(directory=str(UI_DIR / "templates"))
    app.state.templates = templates
    app.mount("/static", StaticFiles(directory=str(UI_DIR / "static")), name="static")
    app.include_router(receipt_routes.router)
    app.include_router(query_routes.router)
    app.include_router(insights_routes.router)

    @app.get("/healthz", tags=["system"])
    def healthz() -> dict[str, str]:
        return {"status": "ok", "version": receipt_ai.__version__}

    @app.get("/readyz", tags=["system"])
    def readyz(request: Request) -> JSONResponse:
        state = request.app.state
        try:
            state.repository.connection.execute("SELECT 1").fetchone()
            state.vector_store.connection.execute("SELECT 1").fetchone()
        except sqlite3.Error:
            logger.exception("Readiness check failed")
            return JSONResponse({"status": "unavailable"}, status_code=503)
        return JSONResponse(
            {
                "status": "ready",
                "receipts": state.repository.count_receipts(),
                "vectors": state.vector_store.count(VECTOR_COLLECTION),
            }
        )

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request, "index.html", {"active": "upload"}
        )

    @app.get("/history", response_class=HTMLResponse, include_in_schema=False)
    def history(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request, "history.html", {"active": "history"}
        )

    @app.get("/query", response_class=HTMLResponse, include_in_schema=False)
    def query_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request, "query.html", {"active": "query"}
        )

    @app.exception_handler(ReceiptNotFoundError)
    async def receipt_not_found(_: Request, exc: ReceiptNotFoundError) -> JSONResponse:
        return JSONResponse({"detail": "receipt not found", "id": str(exc)}, status_code=404)

    @app.exception_handler(CollectionNotFoundError)
    async def collection_not_found(_: Request, exc: CollectionNotFoundError) -> JSONResponse:
        return JSONResponse({"detail": "vector collection not found"}, status_code=404)

    @app.exception_handler(ReceiptValidationError)
    async def receipt_invalid(_: Request, exc: ReceiptValidationError) -> JSONResponse:
        return JSONResponse({"detail": "invalid receipt", "problems": exc.problems}, status_code=422)

    @app.exception_handler(VectorValidationError)
    async def vector_invalid(_: Request, exc: VectorValidationError) -> JSONResponse:
        return JSONResponse({"detail": "invalid vector", "problems": [str(exc)]}, status_code=422)

    @app.exception_handler(QueryEngineError)
    async def query_failed(_: Request, exc: QueryEngineError) -> JSONResponse:
        return JSONResponse({"detail": "query failed", "problems": [str(exc)]}, status_code=422)

    @app.exception_handler(ExtractionValidationError)
    async def extraction_invalid(_: Request, exc: ExtractionValidationError) -> JSONResponse:
        return JSONResponse(
            {
                "detail": "extraction validation failed",
                "problems": exc.problems,
                "warnings": exc.warnings,
            },
            status_code=422,
        )

    @app.exception_handler(UploadValidationError)
    async def upload_invalid(_: Request, exc: UploadValidationError) -> JSONResponse:
        return JSONResponse(
            {"detail": "invalid upload", "problems": exc.problems}, status_code=422
        )

    @app.exception_handler(MoneyParseError)
    async def money_invalid(_: Request, exc: MoneyParseError) -> JSONResponse:
        return JSONResponse({"detail": "invalid amount", "problems": [str(exc)]}, status_code=422)

    @app.exception_handler(ValueError)
    async def value_invalid(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=400)

    return app


app = create_app()
