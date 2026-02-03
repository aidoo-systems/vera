from __future__ import annotations

import json
import os

import logging
import time

from fastapi import FastAPI, File, HTTPException, UploadFile, Request
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, update
from sqlalchemy import text as sql_text

from app.services.storage import save_upload
from app.services.validation import apply_corrections
from app.services.summary import build_summary
from app.schemas.documents import StructuredFieldsUpdateRequest, ValidateRequest
from app.db.session import Base, engine, get_session
from app.models.documents import AuditLog, Document
from app.schemas.documents import DocumentStatus
from app.models.documents import Token
from app.worker import celery_app

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("vera")

app = FastAPI(title="VERA API", version="0.1.0")

cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in cors_origins if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

data_dir = os.getenv("DATA_DIR", "./data")
app.mount("/files", StaticFiles(directory=data_dir), name="files")


@app.on_event("startup")
def startup_event():
    logger.info("Startup: initializing database")
    Base.metadata.create_all(bind=engine)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    logger.debug("Request start %s %s", request.method, request.url.path)
    response = await call_next(request)
    duration_ms = (time.time() - start_time) * 1000
    logger.debug(
        "Request end %s %s status=%s duration_ms=%.2f",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


@app.post("/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    logger.info("Upload started filename=%s", file.filename)
    try:
        document_id, image_path, image_url = save_upload(file)
        with get_session() as session:
            session.add(
                Document(
                    id=document_id,
                    image_path=image_path,
                    image_width=0,
                    image_height=0,
                    status=DocumentStatus.uploaded.value,
                    structured_fields=json.dumps({}),
                )
            )
            session.commit()
        celery_app.send_task("vera.process_document", args=[document_id])
    except RuntimeError as error:
        if str(error) == "celery_not_installed":
            raise HTTPException(status_code=503, detail="Background worker is not available")
        if str(error) == "pdf_support_not_installed":
            raise HTTPException(status_code=503, detail="PDF support is not installed")
        if str(error) == "pdf_no_pages":
            raise HTTPException(status_code=400, detail="PDF has no pages")
        raise
    except ValueError as error:
        if str(error) == "unsupported_file_type":
            raise HTTPException(status_code=415, detail="Unsupported file type")
        raise
    except Exception:
        logger.exception("Upload failed")
        raise
    logger.info("Upload queued document_id=%s", document_id)
    payload = {
        "document_id": document_id,
        "image_url": image_url,
        "image_width": 0,
        "image_height": 0,
        "status": DocumentStatus.uploaded.value,
        "tokens": [],
        "structured_fields": {},
    }
    return JSONResponse(jsonable_encoder(payload))


@app.post("/documents/{document_id}/validate")
async def validate_document(document_id: str, payload: ValidateRequest):
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


@app.get("/documents/{document_id}")
async def get_document(document_id: str):
    logger.debug("Get document document_id=%s", document_id)
    with get_session() as session:
        document = session.get(Document, document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")

        tokens = session.execute(
            select(Token)
            .where(Token.document_id == document_id)
            .order_by(Token.line_index.asc(), Token.token_index.asc())
        ).scalars().all()

        structured_fields_raw = getattr(document, "structured_fields")
        structured_fields = json.loads(str(structured_fields_raw)) if structured_fields_raw else {}

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
                "image_url": f"/files/{os.path.basename(str(getattr(document, 'image_path')))}",
                "image_width": int(getattr(document, "image_width")),
                "image_height": int(getattr(document, "image_height")),
                "status": document.status,
                "tokens": token_payload,
                "structured_fields": structured_fields,
            }
        )


@app.get("/documents/{document_id}/summary")
async def get_summary(document_id: str):
    logger.info("Summary requested document_id=%s", document_id)
    try:
        summary = build_summary(document_id)
    except ValueError as error:
        if str(error) == "document_not_found":
            raise HTTPException(status_code=404, detail="Document not found")
        if str(error) == "document_not_validated":
            raise HTTPException(status_code=409, detail="Document not validated")
        raise
    logger.info("Summary completed document_id=%s", document_id)
    return JSONResponse(summary)


@app.post("/documents/{document_id}/fields")
async def update_structured_fields(document_id: str, payload: StructuredFieldsUpdateRequest):
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
async def get_audit_log(document_id: str):
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
async def export_document(document_id: str, format: str = "json"):
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
        lines = ["key,value"]
        lines.append(f"document_id,{payload['document_id']}")
        cleaned_text = payload["validated_text"].replace("\n", " ")
        lines.append(f"validated_text,{cleaned_text}")
        for key, value in payload["structured_fields"].items():
            lines.append(f"{key},{value}")
        return PlainTextResponse("\n".join(lines), media_type="text/csv")

    return JSONResponse(payload)


@app.get("/health")
async def health_check():
    with engine.connect() as connection:
        connection.execute(sql_text("SELECT 1"))
    return JSONResponse({"status": "ok"})
