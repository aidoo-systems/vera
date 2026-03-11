import csv
import io
import json
import os
import sys
import uuid

import asyncio
import logging
import time

import httpx
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pythonjsonlogger import jsonlogger
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from slowapi.middleware import SlowAPIMiddleware
from slowapi import _rate_limit_exceeded_handler
from sqlalchemy import case, func, select, update
from sqlalchemy import text as sql_text

from app.services.storage import save_upload
from app.services.validation import apply_corrections, apply_page_corrections
from app.services.summary import build_summary, build_page_summary
from app.services.ollama import list_models, pull_model, stream_pull_model
from app.services.auth import (
    create_session,
    delete_session,
    get_session as get_auth_session,
    hub_configured,
    validate_with_hub,
)
from app.middleware.auth import require_auth
from app.schemas.documents import StructuredFieldsUpdateRequest, ValidateRequest
from app.db.session import Base, engine, get_session
from app.models.documents import AuditLog, Document, DocumentPage
from app.schemas.documents import DocumentStatus
from app.models.documents import Token
from app.worker import celery_app
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
    level=logging.DEBUG,
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
    yield


app = FastAPI(title="VERA API", version="1.2.0", lifespan=lifespan)

upload_rate_limit = os.getenv("UPLOAD_RATE_LIMIT", "10/minute")
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in cors_origins if origin.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Request-ID", "X-API-Key"],
)
app.add_middleware(SlowAPIMiddleware)

data_dir = os.getenv("DATA_DIR", "./data")
app.mount("/files", StaticFiles(directory=data_dir), name="files")


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


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    username: str
    password: str


@app.post("/api/auth/login")
@limiter.limit("5/minute")
async def auth_login(request: Request, body: LoginRequest):
    """Authenticate via Hub and create a session."""
    if not hub_configured():
        raise HTTPException(status_code=503, detail="Authentication not configured")

    user = validate_with_hub(body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    session_id = create_session({
        "username": user["username"],
        "role": user.get("role", "user"),
        "user_id": user.get("id"),
    })

    response = JSONResponse({"username": user["username"], "role": user.get("role", "user")})
    response.set_cookie(
        key="vera_session",
        value=session_id,
        httponly=True,
        samesite="lax",
        max_age=86400,
    )
    return response


@app.post("/api/auth/logout")
async def auth_logout(request: Request):
    """Clear the session."""
    session_id = request.cookies.get("vera_session")
    if session_id:
        delete_session(session_id)
    response = JSONResponse({"status": "ok"})
    response.delete_cookie("vera_session")
    return response


@app.get("/api/auth/status")
async def auth_status(request: Request):
    """Check current auth status."""
    if not hub_configured():
        return JSONResponse({"authenticated": True, "auth_required": False})

    session_id = request.cookies.get("vera_session")
    if not session_id:
        return JSONResponse({"authenticated": False, "auth_required": True})

    session = get_auth_session(session_id)
    if not session:
        return JSONResponse({"authenticated": False, "auth_required": True})

    return JSONResponse({
        "authenticated": True,
        "auth_required": True,
        "username": session.get("username"),
        "role": session.get("role"),
    })


# ---------------------------------------------------------------------------
# Document endpoints (auth required)
# ---------------------------------------------------------------------------


@app.post("/documents/upload")
@limiter.limit(upload_rate_limit)
async def upload_document(request: Request, file: UploadFile = File(...), _auth=Depends(require_auth)):
    logger.info("Upload started filename=%s", file.filename)
    try:
        document_id, image_path, image_url, pages = save_upload(file)
        with get_session() as session:
            session.add(
                Document(
                    id=document_id,
                    image_path=image_path,
                    image_width=0,
                    image_height=0,
                    status=DocumentStatus.uploaded.value,
                    structured_fields=json.dumps({}),
                    page_count=len(pages),
                )
            )
            for page in pages:
                session.add(
                    DocumentPage(
                        id=uuid.uuid4().hex,
                        document_id=document_id,
                        page_index=page["page_index"],
                        image_path=page["image_path"],
                        image_width=0,
                        image_height=0,
                        status=DocumentStatus.uploaded.value,
                    )
                )
            session.commit()
        task_result = celery_app.send_task("vera.process_document", args=[document_id])
        with get_session() as session:
            session.execute(
                update(Document)
                .where(Document.id == document_id)
                .values(processing_task_id=task_result.id)
            )
            session.commit()
    except RuntimeError as error:
        if str(error) == "celery_not_installed":
            raise HTTPException(status_code=503, detail="Background worker is not available")
        if str(error) == "pdf_support_not_installed":
            raise HTTPException(status_code=503, detail="PDF support is not installed")
        if str(error) == "pdf_no_pages":
            raise HTTPException(status_code=400, detail="PDF has no pages")
        if str(error) == "mime_support_not_installed":
            raise HTTPException(status_code=503, detail="MIME validation is not installed")
        raise
    except ValueError as error:
        if str(error) == "unsupported_file_type":
            raise HTTPException(status_code=415, detail="Unsupported file type")
        if str(error) == "unsupported_mime_type":
            raise HTTPException(status_code=415, detail="Unsupported MIME type")
        if str(error) == "file_too_large":
            raise HTTPException(status_code=413, detail="File exceeds upload size limit")
        if str(error) == "virus_detected":
            raise HTTPException(status_code=400, detail="File failed security scan")
        raise
    except Exception:
        logger.exception("Upload failed")
        raise
    logger.info("Upload queued document_id=%s", document_id)
    with get_session() as session:
        page_rows = session.execute(
            select(DocumentPage)
            .where(DocumentPage.document_id == document_id)
            .order_by(DocumentPage.page_index.asc())
        ).scalars().all()

    page_payload = [
        {
            "page_id": page.id,
            "page_index": int(getattr(page, "page_index")),
            "image_url": f"/files/{os.path.basename(str(getattr(page, 'image_path')))}",
            "status": page.status,
            "review_complete": bool(getattr(page, "review_complete_at")),
            "version": int(getattr(page, "version", 1)),
        }
        for page in page_rows
    ]

    payload = {
        "document_id": document_id,
        "image_url": image_url,
        "image_width": 0,
        "image_height": 0,
        "status": DocumentStatus.uploaded.value,
        "page_count": len(page_payload),
        "pages": page_payload,
        "structured_fields": {},
        "review_complete": False,
    }
    return JSONResponse(jsonable_encoder(payload))


@app.post("/documents/{document_id}/validate")
async def validate_document(document_id: str, payload: ValidateRequest, _auth=Depends(require_auth)):
    logger.info("Validate started document_id=%s review_complete=%s", document_id, payload.review_complete)
    try:
        validated_text, status, validated_at = apply_corrections(
            document_id,
            [item.model_dump() for item in payload.corrections],
            payload.reviewed_token_ids,
            payload.review_complete,
            payload.structured_fields,
        )
    except ValueError as error:
        if str(error) == "document_not_found":
            raise HTTPException(status_code=404, detail="Document not found")
        if str(error) == "review_incomplete":
            raise HTTPException(status_code=409, detail="Review incomplete")
        raise
    logger.info("Validate completed document_id=%s status=%s", document_id, status)
    return JSONResponse(
        jsonable_encoder(
            {
                "validated_text": validated_text,
                "validation_status": status,
                "validated_at": validated_at,
                "structured_fields": payload.structured_fields or {},
            }
        )
    )


@app.post("/documents/{document_id}/pages/{page_id}/validate")
async def validate_document_page(document_id: str, page_id: str, payload: ValidateRequest, _auth=Depends(require_auth)):
    logger.info(
        "Validate page started document_id=%s page_id=%s review_complete=%s",
        document_id,
        page_id,
        payload.review_complete,
    )
    try:
        validated_text, status, validated_at = apply_page_corrections(
            document_id,
            page_id,
            [item.model_dump() for item in payload.corrections],
            payload.reviewed_token_ids,
            payload.review_complete,
            payload.structured_fields,
            payload.page_version,
        )
    except ValueError as error:
        if str(error) == "document_not_found":
            raise HTTPException(status_code=404, detail="Document not found")
        if str(error) == "review_incomplete":
            raise HTTPException(status_code=409, detail="Review incomplete")
        if str(error) == "version_required":
            raise HTTPException(status_code=400, detail="Page version is required")
        if str(error) == "version_conflict":
            raise HTTPException(status_code=409, detail="Review out of date")
        raise
    logger.info("Validate page completed document_id=%s page_id=%s status=%s", document_id, page_id, status)
    return JSONResponse(
        jsonable_encoder(
            {
                "validated_text": validated_text,
                "validation_status": status,
                "validated_at": validated_at,
                "structured_fields": payload.structured_fields or {},
            }
        )
    )


def _build_page_status(session, page: DocumentPage) -> dict:
    token_count = session.execute(
        select(func.count(Token.id)).where(Token.page_id == page.id)
    ).scalar_one()
    forced_review_count = session.execute(
        select(func.count(Token.id))
        .where(Token.page_id == page.id)
        .where(Token.forced_review.is_(True))
    ).scalar_one()
    updated_at = getattr(page, "updated_at", None)
    updated_at_value = updated_at.isoformat() if updated_at else None

    return {
        "page_id": page.id,
        "page_index": int(getattr(page, "page_index")),
        "status": page.status,
        "review_complete": bool(getattr(page, "review_complete_at")),
        "token_count": int(token_count or 0),
        "forced_review_count": int(forced_review_count or 0),
        "updated_at": updated_at_value,
        "version": int(getattr(page, "version", 1)),
    }


@app.get("/documents/{document_id}")
async def get_document(document_id: str, _auth=Depends(require_auth)):
    logger.debug("Get document document_id=%s", document_id)
    with get_session() as session:
        document = session.get(Document, document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")
        structured_fields_raw = getattr(document, "structured_fields")
        structured_fields = json.loads(str(structured_fields_raw)) if structured_fields_raw else {}

        pages = session.execute(
            select(DocumentPage)
            .where(DocumentPage.document_id == document_id)
            .order_by(DocumentPage.page_index.asc())
        ).scalars().all()
        page_payload = [
            {
                "page_id": page.id,
                "page_index": int(getattr(page, "page_index")),
                "image_url": f"/files/{os.path.basename(str(getattr(page, 'image_path')))}",
                "image_width": int(getattr(page, "image_width")),
                "image_height": int(getattr(page, "image_height")),
                "status": page.status,
                "review_complete": bool(getattr(page, "review_complete_at")),
                "version": int(getattr(page, "version", 1)),
            }
            for page in pages
        ]

        return JSONResponse(
            {
                "document_id": document.id,
                "image_url": f"/files/{os.path.basename(str(getattr(document, 'image_path')))}",
                "image_width": int(getattr(document, "image_width")),
                "image_height": int(getattr(document, "image_height")),
                "status": document.status,
                "page_count": int(getattr(document, "page_count")),
                "pages": page_payload,
                "structured_fields": structured_fields,
                "review_complete": bool(getattr(document, "review_complete_at")),
            }
        )


@app.get("/documents/{document_id}/pages/status")
async def get_document_page_statuses(document_id: str, _auth=Depends(require_auth)):
    logger.debug("Get document statuses document_id=%s", document_id)
    with get_session() as session:
        document = session.get(Document, document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")

        pages = session.execute(
            select(DocumentPage)
            .where(DocumentPage.document_id == document_id)
            .order_by(DocumentPage.page_index.asc())
        ).scalars().all()

        page_payload = [_build_page_status(session, page) for page in pages]

        return JSONResponse(
            {
                "document_id": document.id,
                "status": document.status,
                "review_complete": bool(getattr(document, "review_complete_at")),
                "pages": page_payload,
            }
        )


@app.get("/documents/{document_id}/pages/{page_id}/status")
async def get_document_page_status(document_id: str, page_id: str, _auth=Depends(require_auth)):
    logger.debug("Get document page status document_id=%s page_id=%s", document_id, page_id)
    with get_session() as session:
        document = session.get(Document, document_id)
        page = session.get(DocumentPage, page_id)
        if document is None or page is None or page.document_id != document_id:
            raise HTTPException(status_code=404, detail="Document not found")

        payload = _build_page_status(session, page)
        payload["document_id"] = document.id
        payload["document_status"] = document.status
        payload["document_review_complete"] = bool(getattr(document, "review_complete_at"))
        return JSONResponse(payload)


@app.get("/documents/{document_id}/status/stream")
async def stream_document_status(document_id: str, interval: float = 2.0, _auth=Depends(require_auth)):
    logger.info("Status stream requested document_id=%s", document_id)

    async def event_stream():
        while True:
            with get_session() as session:
                document = session.get(Document, document_id)
                if document is None:
                    yield f"data: {json.dumps({'error': 'document_not_found'})}\n\n"
                    break

                pages = session.execute(
                    select(DocumentPage)
                    .where(DocumentPage.document_id == document_id)
                    .order_by(DocumentPage.page_index.asc())
                ).scalars().all()

                payload = {
                    "document_id": document.id,
                    "status": document.status,
                    "review_complete": bool(getattr(document, "review_complete_at")),
                    "pages": [_build_page_status(session, page) for page in pages],
                }
            yield f"data: {json.dumps(payload)}\n\n"
            await asyncio.sleep(max(0.5, interval))

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/documents/{document_id}/pages/{page_id}")
async def get_document_page(document_id: str, page_id: str, _auth=Depends(require_auth)):
    logger.debug("Get document page document_id=%s page_id=%s", document_id, page_id)
    with get_session() as session:
        document = session.get(Document, document_id)
        page = session.get(DocumentPage, page_id)
        if document is None or page is None or page.document_id != document_id:
            raise HTTPException(status_code=404, detail="Document not found")

        tokens = session.execute(
            select(Token)
            .where(Token.document_id == document_id)
            .where(Token.page_id == page_id)
            .order_by(Token.line_index.asc(), Token.token_index.asc())
        ).scalars().all()

        token_payload = []
        for token in tokens:
            bbox_raw = getattr(token, "bbox")
            flags_raw = getattr(token, "flags")
            bbox = json.loads(str(bbox_raw)) if bbox_raw is not None else []
            flags = json.loads(str(flags_raw)) if flags_raw is not None else []
            token_payload.append(
                {
                    "id": token.id,
                    "line_id": token.line_id,
                    "line_index": int(getattr(token, "line_index")),
                    "token_index": int(getattr(token, "token_index")),
                    "text": token.text,
                    "confidence": token.confidence,
                    "confidence_label": token.confidence_label,
                    "forced_review": bool(int(getattr(token, "forced_review") or 0)),
                    "bbox": bbox,
                    "flags": flags,
                }
            )

        return JSONResponse(
            {
                "document_id": document.id,
                "page_id": page.id,
                "page_index": int(getattr(page, "page_index")),
                "image_url": f"/files/{os.path.basename(str(getattr(page, 'image_path')))}",
                "image_width": int(getattr(page, "image_width")),
                "image_height": int(getattr(page, "image_height")),
                "status": page.status,
                "review_complete": bool(getattr(page, "review_complete_at")),
                "version": int(getattr(page, "version", 1)),
                "tokens": token_payload,
            }
        )


@app.post("/documents/{document_id}/cancel")
async def cancel_document(document_id: str, _auth=Depends(require_auth)):
    logger.info("Cancel requested document_id=%s", document_id)
    if not hasattr(celery_app, "control"):
        raise HTTPException(status_code=503, detail="Background worker is not available")

    with get_session() as session:
        document = session.get(Document, document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")

        if document.status not in (DocumentStatus.uploaded.value, DocumentStatus.processing.value):
            raise HTTPException(status_code=409, detail="Document is not processing")

        task_id = getattr(document, "processing_task_id")
        if not task_id:
            raise HTTPException(status_code=409, detail="No active task to cancel")

        try:
            celery_app.control.revoke(task_id, terminate=True)
        except Exception:  # pragma: no cover
            logger.exception("Failed to revoke task document_id=%s task_id=%s", document_id, task_id)
            raise HTTPException(status_code=500, detail="Failed to cancel processing")

        session.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(status=DocumentStatus.canceled.value, processing_task_id=None)
        )
        session.execute(
            update(DocumentPage)
            .where(DocumentPage.document_id == document_id)
            .values(status=DocumentStatus.canceled.value)
        )
        session.add(
            AuditLog(
                id=os.urandom(16).hex(),
                document_id=document_id,
                event_type="ocr_canceled",
                detail=json.dumps({"task_id": task_id}),
            )
        )
        session.commit()

    return JSONResponse({"status": DocumentStatus.canceled.value})


@app.get("/documents/{document_id}/summary")
async def get_summary(document_id: str, model: str | None = None, _auth=Depends(require_auth)):
    logger.info("Summary requested document_id=%s", document_id)
    try:
        summary = build_summary(document_id, model_override=model)
    except ValueError as error:
        if str(error) == "document_not_found":
            raise HTTPException(status_code=404, detail="Document not found")
        if str(error) == "document_not_validated":
            raise HTTPException(status_code=409, detail="Document not validated")
        raise
    logger.info("Summary completed document_id=%s", document_id)
    return JSONResponse(summary)


@app.get("/documents/{document_id}/pages/{page_id}/summary")
async def get_page_summary(document_id: str, page_id: str, model: str | None = None, _auth=Depends(require_auth)):
    logger.info("Summary requested document_id=%s page_id=%s", document_id, page_id)
    try:
        summary = build_page_summary(document_id, page_id, model_override=model)
    except ValueError as error:
        if str(error) == "document_not_found":
            raise HTTPException(status_code=404, detail="Document not found")
        if str(error) == "page_not_validated":
            raise HTTPException(status_code=409, detail="Review incomplete")
        raise
    logger.info("Page summary completed document_id=%s page_id=%s", document_id, page_id)
    return JSONResponse(summary)


@app.get("/llm/models")
async def get_llm_models(_auth=Depends(require_auth)):
    try:
        models = list_models()
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Ollama is not available")
    return JSONResponse({"models": models})


@app.get("/llm/health")
async def get_llm_health(_auth=Depends(require_auth)):
    try:
        models = list_models()
    except httpx.HTTPError:
        return JSONResponse({"reachable": False, "models": [], "model": os.getenv("OLLAMA_MODEL", "llama3.1")})
    return JSONResponse({"reachable": True, "models": models, "model": os.getenv("OLLAMA_MODEL", "llama3.1")})


@app.post("/llm/models/pull")
async def pull_llm_model(payload: dict, _auth=Depends(require_auth)):
    model = str(payload.get("model", "")).strip()
    if not model:
        raise HTTPException(status_code=400, detail="Model name is required")
    try:
        result = pull_model(model)
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Failed to pull model from Ollama")
    return JSONResponse({"status": "ok", "result": result})


@app.post("/llm/models/pull/stream")
async def pull_llm_model_stream(payload: dict, _auth=Depends(require_auth)):
    model = str(payload.get("model", "")).strip()
    if not model:
        raise HTTPException(status_code=400, detail="Model name is required")

    def event_stream():
        try:
            for event in stream_pull_model(model):
                yield json.dumps(event) + "\n"
        except httpx.HTTPError:
            yield json.dumps({"error": "Failed to pull model from Ollama"}) + "\n"

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


@app.post("/documents/{document_id}/fields")
async def update_structured_fields(document_id: str, payload: StructuredFieldsUpdateRequest, _auth=Depends(require_auth)):
    logger.info("Fields update document_id=%s count=%s", document_id, len(payload.structured_fields))
    with get_session() as session:
        document = session.get(Document, document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")

        session.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(structured_fields=json.dumps(payload.structured_fields))
        )
        session.add(
            AuditLog(
                id=os.urandom(16).hex(),
                document_id=document_id,
                event_type="fields_updated",
                detail=json.dumps({"field_count": len(payload.structured_fields)}),
            )
        )
        session.commit()

    return JSONResponse({"structured_fields": payload.structured_fields})


@app.get("/documents/{document_id}/audit")
async def get_audit_log(document_id: str, _auth=Depends(require_auth)):
    logger.debug("Audit log requested document_id=%s", document_id)
    with get_session() as session:
        document = session.get(Document, document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")

        entries = session.execute(
            select(AuditLog)
            .where(AuditLog.document_id == document_id)
            .order_by(AuditLog.created_at.desc())
        ).scalars().all()

        payload = []
        for entry in entries:
            detail_raw = getattr(entry, "detail")
            detail = json.loads(str(detail_raw)) if detail_raw else {}
            payload.append(
                {
                    "id": entry.id,
                    "event_type": entry.event_type,
                    "actor": entry.actor,
                    "detail": detail,
                    "created_at": entry.created_at.isoformat(),
                }
            )

    return JSONResponse({"audit_log": payload})


@app.get("/documents/{document_id}/export")
async def export_document(document_id: str, format: str = "json", _auth=Depends(require_auth)):
    logger.info("Export requested document_id=%s format=%s", document_id, format)
    with get_session() as session:
        document = session.get(Document, document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")
        document_status = str(document.status)
        if document_status not in (DocumentStatus.validated.value, DocumentStatus.summarized.value):
            raise HTTPException(status_code=409, detail="Document not validated")

        validated_text = document.validated_text if document.validated_text is not None else ""
        structured_fields_raw = getattr(document, "structured_fields")
        structured_fields = json.loads(str(structured_fields_raw)) if structured_fields_raw else {}
        session.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(status=DocumentStatus.exported.value)
        )
        session.add(
            AuditLog(
                id=os.urandom(16).hex(),
                document_id=document_id,
                event_type="exported",
                detail=json.dumps({"format": format.lower()}),
            )
        )
        session.commit()

        payload = {
            "document_id": document_id,
            "validated_text": validated_text,
            "structured_fields": structured_fields,
        }

    if format.lower() == "txt":
        return PlainTextResponse(validated_text, media_type="text/plain")

    if format.lower() == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf, quoting=csv.QUOTE_ALL)
        writer.writerow(["key", "value"])
        writer.writerow(["document_id", payload["document_id"]])
        cleaned_text = payload["validated_text"].replace("\n", " ")
        writer.writerow(["validated_text", cleaned_text])
        for key, value in payload["structured_fields"].items():
            writer.writerow([key, value])
        return PlainTextResponse(buf.getvalue(), media_type="text/csv")

    return JSONResponse(payload)


@app.get("/documents/{document_id}/pages/{page_id}/export")
async def export_document_page(document_id: str, page_id: str, format: str = "json", _auth=Depends(require_auth)):
    logger.info("Export requested document_id=%s page_id=%s format=%s", document_id, page_id, format)
    with get_session() as session:
        document = session.get(Document, document_id)
        page = session.get(DocumentPage, page_id)
        if document is None or page is None or page.document_id != document_id:
            raise HTTPException(status_code=404, detail="Document not found")
        if page.status not in (DocumentStatus.validated.value, DocumentStatus.summarized.value):
            raise HTTPException(status_code=409, detail="Review incomplete")

        validated_text = page.validated_text if page.validated_text is not None else ""
        structured_fields_raw = getattr(page, "structured_fields")
        structured_fields = json.loads(str(structured_fields_raw)) if structured_fields_raw else {}

        session.execute(
            update(DocumentPage)
            .where(DocumentPage.id == page_id)
            .values(status=DocumentStatus.exported.value)
        )
        session.add(
            AuditLog(
                id=os.urandom(16).hex(),
                document_id=document_id,
                page_id=page_id,
                event_type="exported",
                detail=json.dumps({"format": format.lower(), "scope": "page"}),
            )
        )
        session.commit()

        payload = {
            "document_id": document_id,
            "page_id": page_id,
            "validated_text": validated_text,
            "structured_fields": structured_fields,
        }

    if format.lower() == "txt":
        return PlainTextResponse(validated_text, media_type="text/plain")

    if format.lower() == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf, quoting=csv.QUOTE_ALL)
        writer.writerow(["key", "value"])
        writer.writerow(["document_id", payload["document_id"]])
        writer.writerow(["page_id", payload["page_id"]])
        cleaned_text = payload["validated_text"].replace("\n", " ")
        writer.writerow(["validated_text", cleaned_text])
        for key, value in payload["structured_fields"].items():
            writer.writerow([key, value])
        return PlainTextResponse(buf.getvalue(), media_type="text/csv")

    return JSONResponse(payload)


@app.get("/health")
async def health_check():
    with engine.connect() as connection:
        connection.execute(sql_text("SELECT 1"))
    return JSONResponse({"status": "ok"})


@app.get("/metrics")
async def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
