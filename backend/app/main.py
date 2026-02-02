from __future__ import annotations

import json
import os

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, update

from app.services.ocr import run_ocr
from app.services.validation import apply_corrections
from app.services.summary import build_summary
from app.schemas.documents import ValidateRequest
from app.db.session import Base, engine, get_session
from app.models.documents import Document
from app.schemas.documents import DocumentStatus
from app.models.documents import Token

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
    Base.metadata.create_all(bind=engine)


@app.post("/documents/upload")
async def upload_document(file: UploadFile = File(...)):
    try:
        ocr_result = await run_ocr(file)
    except RuntimeError as error:
        if str(error) == "paddleocr_not_installed":
            raise HTTPException(status_code=503, detail="PaddleOCR is not installed")
        raise
    payload = {
        "document_id": ocr_result.document_id,
        "image_url": ocr_result.image_url,
        "image_width": ocr_result.image_width,
        "image_height": ocr_result.image_height,
        "status": ocr_result.status,
        "tokens": ocr_result.tokens,
    }
    return JSONResponse(payload)


@app.post("/documents/{document_id}/validate")
async def validate_document(document_id: str, payload: ValidateRequest):
    try:
        validated_text, status, validated_at = apply_corrections(
            document_id,
            [item.model_dump() for item in payload.corrections],
            payload.reviewed_token_ids,
            payload.review_complete,
        )
    except ValueError as error:
        if str(error) == "document_not_found":
            raise HTTPException(status_code=404, detail="Document not found")
        if str(error) == "review_incomplete":
            raise HTTPException(status_code=409, detail="Review incomplete")
        raise
    return JSONResponse(
        {"validated_text": validated_text, "validation_status": status, "validated_at": validated_at}
    )


@app.get("/documents/{document_id}")
async def get_document(document_id: str):
    with get_session() as session:
        document = session.get(Document, document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")

        tokens = session.execute(
            select(Token)
            .where(Token.document_id == document_id)
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
            "image_url": f"/files/{os.path.basename(str(getattr(document, 'image_path')))}",
            "image_width": int(getattr(document, "image_width")),
            "image_height": int(getattr(document, "image_height")),
            "status": document.status,
            "tokens": token_payload,
        }
    )


@app.get("/documents/{document_id}/summary")
async def get_summary(document_id: str):
    try:
        summary = build_summary(document_id)
    except ValueError as error:
        if str(error) == "document_not_found":
            raise HTTPException(status_code=404, detail="Document not found")
        if str(error) == "document_not_validated":
            raise HTTPException(status_code=409, detail="Document not validated")
        raise
    return JSONResponse(summary)


@app.get("/documents/{document_id}/export")
async def export_document(document_id: str, format: str = "json"):
    with get_session() as session:
        document = session.get(Document, document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")
        document_status = str(document.status)
        if document_status != DocumentStatus.validated.value:
            raise HTTPException(status_code=409, detail="Document not validated")

        validated_text = document.validated_text if document.validated_text is not None else ""
        session.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(status=DocumentStatus.exported.value)
        )
        session.commit()

        payload = {
            "document_id": document_id,
            "validated_text": validated_text,
            "structured_fields": {},
        }

    if format.lower() == "csv":
        lines = ["key,value"]
        lines.append(f"document_id,{payload['document_id']}")
        lines.append(f"validated_text,{payload['validated_text'].replace('\n', ' ')}")
        for key, value in payload["structured_fields"].items():
            lines.append(f"{key},{value}")
        return PlainTextResponse("\n".join(lines), media_type="text/csv")

    return JSONResponse(payload)
