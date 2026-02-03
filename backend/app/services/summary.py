from __future__ import annotations

import json
import logging
import re
import uuid

from sqlalchemy import select, update

from app.db.session import Base, engine, get_session
from app.models.documents import AuditLog, Document
from app.schemas.documents import DocumentStatus


def build_summary(document_id: str) -> dict:
    Base.metadata.create_all(bind=engine)
    logger.info("Build summary document_id=%s", document_id)
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

    line_count = len(lines)
    word_count = sum(len(line.split()) for line in lines)

    date_pattern = re.compile(r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})")
    dates: list[str] = []
    seen_dates = set()
    for line in lines:
        for match in date_pattern.findall(line):
            if match in seen_dates:
                continue
            seen_dates.add(match)
            dates.append(match)

    currency_pattern = re.compile(r"(?:£|\$|€)\s*\d{1,3}(?:,\d{3})*(?:\.\d{2})?")
    amounts: list[str] = []
    seen_amounts = set()
    for line in lines:
        for match in currency_pattern.finditer(line):
            value = match.group(0)
            if value in seen_amounts:
                continue
            seen_amounts.add(value)
            amounts.append(value)

    highlights = lines[:3]
    highlight_text = " | ".join(highlights) if highlights else "No text detected"
    date_text = ", ".join(dates) if dates else "Not detected"
    amount_text = ", ".join(amounts) if amounts else "Not detected"

    doc_signals = [
        ("Invoice/Receipt", ["invoice", "receipt", "subtotal", "total", "amount due", "balance due", "vat", "tax", "paid"]),
        ("Statement", ["statement", "account", "transactions", "balance"]),
        ("Form", ["application", "form", "please fill", "checkbox", "signature"]),
        ("Letter", ["dear", "sincerely", "regards"]),
        ("Report", ["report", "summary", "analysis"]),
    ]
    text_blob = "\n".join(lines).lower()
    best_label = "General document"
    best_hits = 0
    for label, keywords in doc_signals:
        hits = sum(1 for keyword in keywords if keyword in text_blob)
        if hits > best_hits:
            best_hits = hits
            best_label = label

    if best_hits >= 3:
        confidence = "high"
    elif best_hits == 2:
        confidence = "medium"
    elif best_hits == 1:
        confidence = "low"
    else:
        confidence = "low"

    stopwords = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "to",
        "was",
        "were",
        "will",
        "with",
    }
    words = re.findall(r"[A-Za-z][A-Za-z0-9'-]+", validated_text.lower())
    keyword_counts: dict[str, int] = {}
    for word in words:
        if len(word) < 3 or word in stopwords:
            continue
        keyword_counts[word] = keyword_counts.get(word, 0) + 1
    sorted_keywords = sorted(keyword_counts.items(), key=lambda item: (-item[1], item[0]))
    top_keywords = [word for word, _ in sorted_keywords[:5]]
    keyword_text = ", ".join(top_keywords) if top_keywords else "Not detected"

    bullet_summary = [
        f"Overview: {line_count} lines · {word_count} words",
        f"Document type: {best_label} ({confidence})",
        f"Highlights: {highlight_text}",
        f"Keywords: {keyword_text}",
        f"Dates detected: {date_text}",
        f"Amounts detected: {amount_text}",
        "All low-confidence items reviewed by user",
    ]
    structured_fields: dict[str, str] = {
        "line_count": str(line_count),
        "word_count": str(word_count),
        "highlights": highlight_text,
        "dates": date_text,
        "amounts": amount_text,
        "document_type": best_label,
        "document_type_confidence": confidence,
        "keywords": keyword_text,
    }

    with get_session() as session:
        session.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(structured_fields=json.dumps(structured_fields))
        )
        session.add(
            AuditLog(
                id=uuid.uuid4().hex,
                document_id=document_id,
                event_type="summary_generated",
                detail=json.dumps({"field_count": len(structured_fields)}),
            )
        )
        session.commit()

    return {
        "bullet_summary": bullet_summary,
        "structured_fields": structured_fields,
        "validation_status": DocumentStatus.validated,
    }
logger = logging.getLogger("vera.summary")
