"""Export route handlers."""

import csv
import io
import json
import logging
import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from sqlalchemy import select, update

from app.db.session import get_session
from app.middleware.auth import require_auth
from app.models.documents import AuditLog, Document, DocumentPage
from app.schemas.documents import DocumentStatus
from app.services.invoice_export import build_invoice_data, to_facturx_xml, to_ubl_xml

logger = logging.getLogger("vera")
router = APIRouter()


@router.get("/documents/{document_id}/export")
async def export_document(document_id: str, format: str = "json", _auth=Depends(require_auth)):
    logger.info("Export requested document_id=%s format=%s", document_id, format)
    with get_session() as session:
        document = session.get(Document, document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")
        document_status = str(document.status)
        if document_status not in (DocumentStatus.validated.value, DocumentStatus.summarized.value, DocumentStatus.exported.value):
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

    if format.lower() in ("facturx", "ubl"):
        invoice = build_invoice_data(structured_fields)
        xml_bytes = to_facturx_xml(invoice, document_id) if format.lower() == "facturx" \
                    else to_ubl_xml(invoice, document_id)
        headers = {"Content-Disposition": f'attachment; filename="invoice-{document_id}.xml"'}
        if invoice.warnings:
            headers["X-VERA-Warnings"] = "; ".join(invoice.warnings)
        return Response(content=xml_bytes, media_type="application/xml", headers=headers)

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


@router.get("/documents/{document_id}/pages/{page_id}/export")
async def export_document_page(document_id: str, page_id: str, format: str = "json", _auth=Depends(require_auth)):
    logger.info("Export requested document_id=%s page_id=%s format=%s", document_id, page_id, format)
    with get_session() as session:
        document = session.get(Document, document_id)
        page = session.get(DocumentPage, page_id)
        if document is None or page is None or page.document_id != document_id:
            raise HTTPException(status_code=404, detail="Document not found")
        if page.status not in (DocumentStatus.validated.value, DocumentStatus.summarized.value, DocumentStatus.exported.value):
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

    if format.lower() in ("facturx", "ubl"):
        invoice = build_invoice_data(structured_fields)
        xml_bytes = to_facturx_xml(invoice, document_id) if format.lower() == "facturx" \
                    else to_ubl_xml(invoice, document_id)
        headers = {"Content-Disposition": f'attachment; filename="invoice-{document_id}-page-{page_id}.xml"'}
        if invoice.warnings:
            headers["X-VERA-Warnings"] = "; ".join(invoice.warnings)
        return Response(content=xml_bytes, media_type="application/xml", headers=headers)

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
