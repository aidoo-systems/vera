"""Document route handlers: upload, get, validate, cancel, status, fields, audit."""

import asyncio
import json
import logging
import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select, update

from app.api.deps import _build_page_status, upload_rate_limit
from app.db.session import get_session
from app.middleware.auth import require_auth
from app.models.documents import AuditLog, Document, DocumentPage, Token
from app.schemas.documents import DocumentStatus, StructuredFieldsUpdateRequest, ValidateRequest
from app.services.storage import save_upload
from app.services.validation import apply_corrections, apply_page_corrections
from app.worker import celery_app

logger = logging.getLogger("vera")
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.post("/documents/upload")
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


@router.post("/documents/{document_id}/validate")
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
        if str(error) == "invalid_document_status":
            raise HTTPException(status_code=409, detail="Document is not in a reviewable state")
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


@router.post("/documents/{document_id}/pages/{page_id}/validate")
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
        if str(error) == "invalid_document_status":
            raise HTTPException(status_code=409, detail="Document is not in a reviewable state")
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


@router.get("/documents/{document_id}")
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


@router.get("/documents/{document_id}/pages/status")
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


@router.get("/documents/{document_id}/pages/{page_id}/status")
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


@router.get("/documents/{document_id}/status/stream")
async def stream_document_status(document_id: str, interval: float = 2.0, _auth=Depends(require_auth)):
    logger.info("Status stream requested document_id=%s", document_id)

    terminal_statuses = {"ocr_done", "validated", "summarized", "exported", "failed", "canceled"}

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
                is_terminal = document.status in terminal_statuses
            yield f"data: {json.dumps(payload)}\n\n"
            if is_terminal:
                break
            await asyncio.sleep(max(0.5, interval))

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/documents/{document_id}/pages/{page_id}")
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


@router.post("/documents/{document_id}/reopen")
async def reopen_document(document_id: str, _auth=Depends(require_auth)):
    """Reopen a validated/exported document for further review."""
    logger.info("Reopen requested document_id=%s", document_id)
    reopenable = {
        DocumentStatus.validated.value,
        DocumentStatus.summarized.value,
        DocumentStatus.exported.value,
    }
    with get_session() as session:
        document = session.get(Document, document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")

        if document.status not in reopenable:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot reopen document in '{document.status}' status",
            )

        session.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(status=DocumentStatus.review_in_progress.value, review_complete_at=None)
        )
        # Reset page review flags so the reviewer sees them again
        session.execute(
            update(DocumentPage)
            .where(DocumentPage.document_id == document_id)
            .values(review_complete_at=None)
        )
        session.add(
            AuditLog(
                id=os.urandom(16).hex(),
                document_id=document_id,
                event_type="document_reopened",
                detail=json.dumps({"previous_status": document.status}),
            )
        )
        session.commit()

    return JSONResponse({"status": DocumentStatus.review_in_progress.value, "document_id": document_id})


@router.post("/documents/{document_id}/cancel")
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


@router.post("/documents/{document_id}/fields")
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


@router.get("/documents/{document_id}/audit")
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
