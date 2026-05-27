"""FastAPI application entry point."""

import logging
import uuid
import os
import time
from pathlib import Path
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config.settings import settings
from app.core.logging_config import setup_logging
setup_logging()

from app.core.exceptions import InvoiceServiceException
from app.models.response import ErrorResponse
from app.api.routes import health, upload, system
from app.api.routes import training as training_routes

logger = logging.getLogger(__name__)

request_counts = defaultdict(list)
RATE_LIMIT = 100
RATE_WINDOW = 60


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    os.makedirs("logs", exist_ok=True)
    # Auto-load (or generate) learned patterns from training data on startup
    try:
        from app.services.training.pattern_learner import load_learned_patterns
        patterns = load_learned_patterns()
        logger.info(
            f"Learned patterns loaded: {patterns.get('meta', {}).get('trained_on_docs', 0)} docs, "
            f"fields: {list(patterns.get('field_labels', {}).keys())}"
        )
    except Exception as e:
        logger.warning(f"Could not load learned patterns on startup: {e}")
    yield
    logger.info("Shutting down...")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Invoice Intelligence Microservice with Indian GST Compliance",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    client_ip = request.client.host if request.client else "unknown"
    current_time = time.time()
    request_counts[client_ip] = [
        t for t in request_counts[client_ip]
        if current_time - t < RATE_WINDOW
    ]
    if len(request_counts[client_ip]) >= RATE_LIMIT:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"error": "Rate limit exceeded"}
        )
    request_counts[client_ip].append(current_time)
    return await call_next(request)


@app.exception_handler(InvoiceServiceException)
async def invoice_service_exception_handler(request: Request, exc: InvoiceServiceException):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=ErrorResponse(
            error_message=exc.message,
            error_code=exc.error_code,
            request_id=getattr(request.state, "request_id", None),
        ).model_dump(),
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            error_message="Internal server error",
            error_code="INTERNAL_ERROR",
            request_id=getattr(request.state, "request_id", None),
        ).model_dump(),
    )


app.include_router(health.router, prefix=settings.API_V1_PREFIX, tags=["Health"])
app.include_router(upload.router, prefix=settings.API_V1_PREFIX, tags=["Upload"])
app.include_router(training_routes.router, prefix=settings.API_V1_PREFIX, tags=["Training"])
app.include_router(system.router, prefix=settings.API_V1_PREFIX, tags=["System"])

_BASE_DIR = Path(__file__).resolve().parent.parent
_frontend_dir = _BASE_DIR / "frontend"
if _frontend_dir.exists():
    app.mount("/frontend", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")


@app.get("/")
async def root():
    return {
        "message": "Invoice Intelligence Microservice",
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "frontend": "/frontend/index.html",
    }
