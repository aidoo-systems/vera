from __future__ import annotations

import re

from sqlalchemy import select, update

from app.db.session import Base, engine, get_session
from app.models.documents import Document
from app.schemas.documents import DocumentStatus


def build_summary(document_id: str) -> dict:
    Base.metadata.create_all(bind=engine)
    with get_session() as session:
        document = session.get(Document, document_id)
        if document is None:
            raise ValueError("document_not_found")
        document_status = session.execute(
            select(Document.status).where(Document.id == document_id)
        ).scalar_one()
        if document_status != DocumentStatus.validated.value:
            raise ValueError("document_not_validated")

        validated_text = session.execute(
            select(Document.validated_text).where(Document.id == document_id)
        ).scalar_one()
        validated_text = validated_text if validated_text is not None else ""

        session.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(status=DocumentStatus.summarized.value)
        )
        session.commit()

    lines = [line.strip() for line in validated_text.splitlines() if line.strip()]

    vendor = lines[0] if lines else "Not detected"

    date_match = None
    date_pattern = re.compile(r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})")
    for line in lines:
        date_match = date_pattern.search(line)
        if date_match:
            break
    date_value = date_match.group(0) if date_match else "Not detected"

    total_value = "Not detected"
    currency_pattern = re.compile(r"(£|\$|€)\s*\d{1,3}(?:,\d{3})*(?:\.\d{2})?")
    for line in lines:
        if re.search(r"\b(total|amount\s+due|balance\s+due|grand\s+total)\b", line, re.IGNORECASE):
            currency_match = currency_pattern.search(line)
            if currency_match:
                total_value = currency_match.group(0)
                break
    if total_value == "Not detected":
        for line in reversed(lines):
            currency_match = currency_pattern.search(line)
            if currency_match:
                total_value = currency_match.group(0)
                break

    vat_value = "Not detected"
    for line in lines:
        if re.search(r"\b(vat|tax)\b", line, re.IGNORECASE):
            currency_match = currency_pattern.search(line)
            if currency_match:
                vat_value = currency_match.group(0)
                break

    line_items = "Not detected"
    if lines:
        line_items = str(max(len(lines) - 2, 0))

    bullet_summary = [
        f"Vendor: {vendor}",
        f"Date: {date_value}",
        f"Total amount: {total_value}",
        f"VAT detected: {vat_value}",
        f"{line_items} line items identified" if line_items != "Not detected" else "Line items: Not detected",
        "All low-confidence items reviewed by user",
    ]
    structured_fields: dict[str, str] = {
        "vendor": vendor,
        "date": date_value,
        "total_amount": total_value,
        "vat": vat_value,
        "line_items": line_items,
    }

    return {
        "bullet_summary": bullet_summary,
        "structured_fields": structured_fields,
        "validation_status": DocumentStatus.validated,
    }
