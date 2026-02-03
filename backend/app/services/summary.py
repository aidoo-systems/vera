from __future__ import annotations

import json
import logging
import os
import re
import uuid

import httpx
from sqlalchemy import select, update

from app.db.session import Base, engine, get_session
from app.models.documents import AuditLog, Document
from app.schemas.documents import DocumentStatus


def build_summary(document_id: str, model_override: str | None = None) -> dict:
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

    date_patterns = [
        re.compile(r"\b\d{4}-\d{2}-\d{2}\b"),
        re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b"),
        re.compile(
            r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{2,4}\b",
            re.IGNORECASE,
        ),
        re.compile(
            r"\b\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{2,4}\b",
            re.IGNORECASE,
        ),
        re.compile(r"\b\d{1,2}[.]\d{1,2}[.]\d{2,4}\b"),
    ]
    dates: list[str] = []
    seen_dates = set()
    for line in lines:
        for pattern in date_patterns:
            for match in pattern.findall(line):
                value = match.strip()
                if value in seen_dates:
                    continue
                seen_dates.add(value)
                dates.append(value)

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

    def pick_vendor(candidate_lines: list[str]) -> str | None:
        skip_terms = {"invoice", "receipt", "statement", "report", "form", "application"}
        for line in candidate_lines[:5]:
            normalized = line.lower()
            if any(term in normalized for term in skip_terms):
                continue
            if sum(ch.isalpha() for ch in line) < 3:
                continue
            return line
        return None

    def pick_total(candidate_lines: list[str]) -> str | None:
        total_terms = ["total", "amount due", "balance due", "amount", "grand total", "total due"]
        for line in candidate_lines:
            normalized = line.lower()
            if any(term in normalized for term in total_terms):
                matches = [match.group(0) for match in currency_pattern.finditer(line)]
                if matches:
                    return matches[-1]
        return amounts[-1] if amounts else None

    def pick_items(candidate_lines: list[str]) -> list[str]:
        items: list[str] = []
        skip_terms = ["total", "subtotal", "tax", "amount due", "balance", "invoice", "receipt"]
        for line in candidate_lines:
            normalized = line.lower()
            if any(term in normalized for term in skip_terms):
                continue
            has_price = bool(currency_pattern.search(line))
            has_qty = bool(re.search(r"\b\d+\s*(x|qty|quantity)\b", normalized))
            if has_price or has_qty:
                items.append(line)
            if len(items) >= 3:
                break
        return items

    def llm_enabled() -> bool:
        return os.getenv("LLM_SUMMARY_ENABLED", "false").lower() in {"1", "true", "yes", "on"}

    def parse_llm_points(raw_text: str) -> list[str] | None:
        try:
            parsed = json.loads(raw_text)
            if isinstance(parsed, list):
                cleaned = [str(item).strip() for item in parsed if str(item).strip()]
                return cleaned[:5] if cleaned else None
        except json.JSONDecodeError:
            pass

        array_match = re.search(r"\[[\s\S]*\]", raw_text)
        if array_match:
            try:
                parsed = json.loads(array_match.group(0))
                if isinstance(parsed, list):
                    cleaned = [str(item).strip() for item in parsed if str(item).strip()]
                    return cleaned[:5] if cleaned else None
            except json.JSONDecodeError:
                pass

        lines_raw = [line.strip() for line in raw_text.splitlines() if line.strip()]
        cleaned_lines = [re.sub(r"^(?:[-*•]\s+)", "", line) for line in lines_raw]
        cleaned_lines = [line for line in cleaned_lines if line]
        return cleaned_lines[:5] if cleaned_lines else None

    def fetch_llm_points(text: str) -> list[str] | None:
        base_url = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
        model = model_override or os.getenv("OLLAMA_MODEL", "llama3.1")
        prompt = (
            "Summarize the following document text into 3 to 5 concise bullet points. "
            "Return ONLY a JSON array of strings. Avoid extra commentary.\n\n"
            f"Document text:\n{text}\n"
        )
        payload = {"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0.2}}
        try:
            with httpx.Client(timeout=20.0) as client:
                response = client.post(f"{base_url}/api/generate", json=payload)
            if response.status_code >= 400:
                logger.warning("LLM summary failed status=%s", response.status_code)
                return None
            data = response.json()
            response_text = str(data.get("response", ""))
            return parse_llm_points(response_text)
        except Exception as exc:  # pragma: no cover
            logger.warning("LLM summary failed error=%s", exc)
            return None

    vendor = pick_vendor(lines)
    total_value = pick_total(lines)
    items = pick_items(lines)
    date_value = dates[0] if dates else None

    summary_points_list: list[str] = []
    if vendor:
        summary_points_list.append(f"Vendor: {vendor}")
    if date_value:
        summary_points_list.append(f"Date: {date_value}")
    if total_value:
        summary_points_list.append(f"Total: {total_value}")
    if items:
        summary_points_list.append(f"Items: {'; '.join(items)}")
    if llm_enabled():
        llm_points = fetch_llm_points(validated_text)
        if llm_points:
            summary_points_list = llm_points
    if not summary_points_list and lines:
        summary_points_list = lines[:3]

    summary_points_text = " | ".join(summary_points_list) if summary_points_list else "No text detected"
    date_text = ", ".join(dates) if dates else "Not detected"
    amount_text = ", ".join(amounts) if amounts else "Not detected"

    doc_signals = [
        (
            "Invoice/Receipt",
            ["invoice", "receipt", "subtotal", "total", "amount due", "balance due", "vat", "tax", "paid"],
        ),
        ("Statement", ["statement", "account", "transactions", "balance", "opening balance", "closing balance"]),
        ("Purchase order", ["purchase order", "po number", "ship to", "bill to"]),
        ("Shipping/Delivery", ["tracking", "shipment", "delivered", "carrier", "shipping label"]),
        ("Legal/Contract", ["agreement", "contract", "terms", "party", "liability"]),
        ("Form/Application", ["application", "form", "please fill", "checkbox", "signature"]),
        ("Report", ["report", "summary", "analysis", "findings"]),
        ("Letter/Correspondence", ["dear", "sincerely", "regards"]),
        ("ID/Certificate", ["certificate", "issued", "id number", "passport", "license"]),
    ]
    text_blob = "\n".join(lines).lower()
    best_label = "Unknown"
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
        f"Summary points: {summary_points_text}",
        f"Keywords: {keyword_text}",
        f"Dates detected: {date_text}",
        f"Amounts detected: {amount_text}",
        "All low-confidence items reviewed by user",
    ]
    structured_fields: dict[str, str] = {
        "line_count": str(line_count),
        "word_count": str(word_count),
        "highlights": highlight_text,
        "summary_points": summary_points_text,
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
