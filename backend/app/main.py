import os
import sys
import uuid

import logging
import time

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pythonjsonlogger import jsonlogger
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from slowapi import _rate_limit_exceeded_handler
from sqlalchemy import text as sql_text

from app.api import auth_router, documents_router, export_router, license_router, llm_router
from app.services.auth import check_license
from app.middleware.csrf import CSRFMiddleware
from app.db.session import Base, engine
from app.utils.logging import RequestIdFilter
from app.utils.request_id import set_request_id
from app.utils.metrics import REQUEST_COUNT, REQUEST_LATENCY
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        log_record["timestamp"] = self.formatTime(record)
        log_record["level"] = record.levelname
        log_record["logger"] = record.name
        if not log_record.get("message"):
            log_record["message"] = record.getMessage()


json_formatter = CustomJsonFormatter()
json_handler = logging.StreamHandler(sys.stdout)
json_handler.setFormatter(json_formatter)

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    handlers=[json_handler],
    force=True,
)


def _attach_request_id_filter() -> None:
    request_filter = RequestIdFilter()
    root_logger = logging.getLogger()
    root_logger.addFilter(request_filter)
    for handler in root_logger.handlers:
        handler.addFilter(request_filter)

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(logger_name)
        logger.addFilter(request_filter)
        for handler in logger.handlers:
            handler.addFilter(request_filter)


_attach_request_id_filter()
logger = logging.getLogger("vera")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Startup: initializing database")
    Base.metadata.create_all(bind=engine)

    # Check license with Hub
    license_status = check_license()
    app.state.enforcement_level = license_status.get("enforcement_level", "grace")
    if license_status.get("valid"):
        logger.info("License valid for VERA — customer=%s, enforcement=%s", license_status.get("customer"), app.state.enforcement_level)
    else:
        logger.warning("VERA is unlicensed: %s (enforcement=%s)", license_status.get("error", "unknown"), app.state.enforcement_level)

    yield


app = FastAPI(title="VERA API", version="1.3.0", lifespan=lifespan)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in cors_origins if origin.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Request-ID", "X-API-Key", "X-CSRF-Token"],
)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(CSRFMiddleware)

data_dir = os.getenv("DATA_DIR", "./data")
app.mount("/files", StaticFiles(directory=data_dir), name="files")

# ---------------------------------------------------------------------------
# Include route modules
# ---------------------------------------------------------------------------
app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(export_router)
app.include_router(llm_router)
app.include_router(license_router)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    request_id = request.headers.get("x-request-id", uuid.uuid4().hex)
    set_request_id(request_id)
    logger.debug("Request start %s %s", request.method, request.url.path)
    response = await call_next(request)
    duration_ms = (time.time() - start_time) * 1000
    REQUEST_COUNT.labels(request.method, request.url.path, response.status_code).inc()
    REQUEST_LATENCY.labels(request.method, request.url.path).observe(duration_ms / 1000)
    logger.debug(
        "Request end %s %s status=%s duration_ms=%.2f",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@app.middleware("http")
async def license_enforcement_middleware(request: Request, call_next):
    """Block write operations when license is in soft/hard enforcement."""
    from app.services.auth import get_enforcement_level, is_path_enforcement_exempt

    path = request.url.path
    if is_path_enforcement_exempt(path):
        return await call_next(request)

    level = get_enforcement_level()

    if level == "hard":
        return JSONResponse(
            status_code=402,
            content={"detail": "License expired — system locked. Contact your administrator."},
        )

    if level == "soft":
        # Block write operations in soft mode.
        # Upload and validate require POST method check; summary endpoints are GET
        # but trigger LLM computation so are blocked regardless of method.
        # Allow: viewing documents, exporting existing, admin functions, auth.
        _soft_blocked_message = {"detail": "License expired — read-only mode. Renew your license to restore full access."}
        if path.startswith("/documents/upload") and request.method in ("POST", "PUT", "PATCH"):
            return JSONResponse(status_code=402, content=_soft_blocked_message)
        if path.endswith("/validate") and request.method in ("POST", "PUT", "PATCH"):
            return JSONResponse(status_code=402, content=_soft_blocked_message)
        if path.endswith("/summary"):
            return JSONResponse(status_code=402, content=_soft_blocked_message)

    return await call_next(request)


# ---------------------------------------------------------------------------
# Health & metrics (kept in main)
# ---------------------------------------------------------------------------


@app.get("/health")
async def health_check():
    with engine.connect() as connection:
        connection.execute(sql_text("SELECT 1"))
    return JSONResponse({"status": "ok"})


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
