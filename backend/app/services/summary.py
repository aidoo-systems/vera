from __future__ import annotations

import json
import logging
import os
import re
import uuid

import httpx
import time
from sqlalchemy import select, update

from app.db.session import Base, engine, get_session
from app.models.documents import AuditLog, Document, DocumentPage
from app.schemas.documents import DocumentStatus
from app.utils.metrics import SUMMARY_DURATION, SUMMARY_LLM_FAILURES

_RULES_CACHE: dict = {}


def _load_rules() -> dict:
    global _RULES_CACHE
    if _RULES_CACHE:
        return _RULES_CACHE
    rules_path = os.getenv("EXTRACTION_RULES_PATH", "app/config/extraction_rules.json")
    try:
        with open(rules_path, "r", encoding="utf-8") as handle:
            _RULES_CACHE = json.load(handle)
    except FileNotFoundError:
        _RULES_CACHE = {}
    return _RULES_CACHE


def _detect_doc_type(lines: list[str], rules: dict) -> str:
    keywords = rules.get("doc_type_keywords", {})
    normalized_lines = "\n".join(line.lower() for line in lines)
    for doc_type, terms in keywords.items():
        if any(term in normalized_lines for term in terms):
            return doc_type
    return "general"


def _detect_locale(lines: list[str]) -> str:
    euro_pattern = re.compile(r"\b\d{1,3}(?:\.\d{3})+,\d{2}\b")
    comma_decimal_pattern = re.compile(r"\b\d{1,3},\d{2}\b")
    for line in lines:
        if euro_pattern.search(line) or comma_decimal_pattern.search(line):
            return "EU"
    return "US"



def _build_summary_from_text(
    validated_text: str,
    model_override: str | None = None,
    doc_type_override: str | None = None,
    locale_override: str | None = None,
) -> tuple[list[str], dict[str, str]]:
    raw_lines = validated_text.splitlines()
    lines = [line.strip() for line in raw_lines if line.strip()]

    rules = _load_rules()
    doc_type = doc_type_override or _detect_doc_type(lines, rules)
    locale = locale_override or _detect_locale(lines)

    line_count = len(lines)
    word_count = sum(len(line.split()) for line in lines)

    date_patterns = [
        re.compile(r"\b\d{4}[-/.]\d{2}[-/.]\d{2}\b"),
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

    currency_symbol_pattern = re.compile(r"(?:£|\$|€)\s*\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})")
    currency_code_pattern = re.compile(
        r"\b(?:USD|AUD|CAD|GBP|EUR)\s*\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})\b",
        re.IGNORECASE,
    )
    number_amount_pattern = re.compile(r"\b\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})\b")

    total_terms = rules.get("total_terms", ["total", "amount due", "balance due", "grand total", "total due"])
    subtotal_terms = rules.get(
        "subtotal_terms", ["subtotal", "sub total", "tax", "vat", "amount", "balance", "due"]
    )

    def normalize_amount(value: str) -> str:
        raw = value.strip()
        currency_prefix = ""
        code_match = re.search(r"\b(USD|AUD|CAD|GBP|EUR)\b", raw, re.IGNORECASE)
        if code_match:
            currency_prefix = f"{code_match.group(1).upper()} "
            raw = re.sub(r"\b(USD|AUD|CAD|GBP|EUR)\b", "", raw, flags=re.IGNORECASE).strip()

        if raw.startswith("$") or raw.startswith("£") or raw.startswith("€"):
            currency_prefix = raw[0]
            raw = raw[1:].strip()

        raw = raw.replace(" ", "")
        has_comma = "," in raw
        has_dot = "." in raw
        if has_comma and has_dot:
            decimal = "," if raw.rfind(",") > raw.rfind(".") else "."
            thousands = "." if decimal == "," else ","
            raw = raw.replace(thousands, "").replace(decimal, ".")
        elif locale == "EU" and has_comma:
            raw = raw.replace(".", "").replace(",", ".")
        elif locale == "US" and has_comma:
            parts = raw.split(",")
            if len(parts[-1]) == 2:
                raw = raw.replace(".", "").replace(",", ".")
            else:
                raw = raw.replace(",", "")
        elif has_dot:
            parts = raw.split(".")
            if len(parts[-1]) == 2:
                raw = raw.replace(",", "")
            else:
                raw = raw.replace(".", "")

        return f"{currency_prefix}{raw}".strip()

    def extract_amounts_from_line(line: str, allow_plain: bool) -> list[str]:
        values = [match.group(0) for match in currency_symbol_pattern.finditer(line)]
        values += [match.group(0) for match in currency_code_pattern.finditer(line)]
        if allow_plain and not values:
            values += [match.group(0) for match in number_amount_pattern.finditer(line)]
        return values

    amounts: list[str] = []
    seen_amounts = set()

    def add_amounts(values: list[str]) -> None:
        for value in values:
            normalized = normalize_amount(value)
            if normalized in seen_amounts:
                continue
            seen_amounts.add(normalized)
            amounts.append(normalized)

    for line in lines:
        normalized = line.lower()
        if any(term in normalized for term in total_terms):
            add_amounts(extract_amounts_from_line(line, allow_plain=True))

    for line in lines:
        normalized = line.lower()
        if any(term in normalized for term in subtotal_terms):
            add_amounts(extract_amounts_from_line(line, allow_plain=True))

    for line in lines:
        add_amounts(extract_amounts_from_line(line, allow_plain=False))

    invoice_pattern = re.compile(
        r"\b(?:invoice|receipt|order|po|purchase order|reference|ref|ticket)\s*(?:no\.?|number|#|id)?\s*[:#]?\s*([A-Za-z0-9-]{3,})",
        re.IGNORECASE,
    )
    tax_pattern = re.compile(
        r"\b(?:vat|tax)\s*(?:id|number|no\.?)\s*[:#]?\s*([A-Za-z0-9-]{5,})",
        re.IGNORECASE,
    )
    email_pattern = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    phone_pattern = re.compile(
        r"(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)?\d{3,4}[\s.-]?\d{4}"
    )

    invoice_numbers: list[str] = []
    tax_ids: list[str] = []
    emails: list[str] = []
    phones: list[str] = []
    seen_invoice = set()
    seen_tax = set()
    seen_email = set()
    seen_phone = set()

    for line in lines:
        normalized_line = line.lower()
        for match in invoice_pattern.findall(line):
            value = match.strip()
            if value and value not in seen_invoice:
                seen_invoice.add(value)
                invoice_numbers.append(value)
        for match in tax_pattern.findall(line):
            value = match.strip()
            if value and value not in seen_tax:
                seen_tax.add(value)
                tax_ids.append(value)
        for match in email_pattern.findall(line):
            if match not in seen_email:
                seen_email.add(match)
                emails.append(match)
        for match in phone_pattern.findall(line):
            value = match.strip()
            if value.isdigit() and any(term in normalized_line for term in ("vat", "tax", "id")):
                continue
            if value and value not in seen_phone:
                seen_phone.add(value)
                phones.append(value)

    def pick_vendor(candidate_lines: list[str]) -> str | None:
        skip_terms = set(
            rules.get("vendor_skip_terms", ["invoice", "receipt", "statement", "report", "form", "application"])
        )
        for line in candidate_lines[:5]:
            normalized = line.lower()
            if any(term in normalized for term in skip_terms):
                continue
            if sum(ch.isalpha() for ch in line) < 3:
                continue
            return line
        return None

    def pick_total(candidate_lines: list[str]) -> str | None:
        total_terms = rules.get(
            "total_terms", ["total", "amount due", "balance due", "amount", "grand total", "total due"]
        )
        for line in candidate_lines:
            normalized = line.lower()
            if any(term in normalized for term in total_terms):
                matches = extract_amounts_from_line(line, allow_plain=True)
                if matches:
                    return matches[-1]
        return amounts[-1] if amounts else None

    def pick_items(candidate_lines: list[str]) -> list[str]:
        items: list[str] = []
        skip_terms = rules.get("skip_terms", ["total", "subtotal", "tax", "amount due", "balance", "invoice", "receipt"])
        for line in candidate_lines:
            normalized = line.lower()
            if any(term in normalized for term in skip_terms):
                continue
            has_price = bool(currency_symbol_pattern.search(line) or currency_code_pattern.search(line))
            has_qty = bool(re.search(r"\b\d+\s*(x|qty|quantity)\b", normalized))
            if has_price or has_qty:
                items.append(line)
            if len(items) >= 3:
                break
        return items

    def fetch_llm_detailed_summary(text: str) -> str | None:
        base_url = os.getenv("OLLAMA_URL", "http://localhost:11434").rstrip("/")
        model = model_override or os.getenv("OLLAMA_MODEL", "llama3.1")
        prompt = (
            "Write a detailed summary that covers the entire page. "
            "Include all major details in the same order they appear. "
            "Return plain text only.\n\n"
            f"Document text:\n{text}\n"
        )
        payload = {"model": model, "prompt": prompt, "stream": False, "options": {"temperature": 0.2}}
        try:
            timeout_seconds = float(os.getenv("OLLAMA_TIMEOUT", "60"))
            retries = int(os.getenv("OLLAMA_RETRIES", "2"))
            last_error = None
            for attempt in range(retries + 1):
                try:
                    with httpx.Client(timeout=timeout_seconds) as client:
                        response = client.post(f"{base_url}/api/generate", json=payload)
                    if response.status_code >= 400:
                        last_error = f"http_{response.status_code}"
                        logger.warning("LLM summary failed status=%s", response.status_code)
                    else:
                        data = response.json()
                        response_text = str(data.get("response", "")).strip()
                        if response_text:
                            return response_text
                        last_error = "empty_response"
                except Exception as exc:  # pragma: no cover
                    last_error = "exception"
                    logger.warning("LLM summary failed error=%s", exc)

            SUMMARY_LLM_FAILURES.labels(reason=last_error or "unknown").inc()
            return None
        except Exception as exc:  # pragma: no cover
            logger.warning("LLM summary failed error=%s", exc)
            SUMMARY_LLM_FAILURES.labels(reason="exception").inc()
            return None

    def build_detailed_summary(candidate_raw_lines: list[str]) -> str:
        if not candidate_raw_lines:
            return "No text detected"
        paragraphs: list[list[str]] = []
        current: list[str] = []
        for line in candidate_raw_lines:
            cleaned = " ".join(line.split())
            if not cleaned:
                if current:
                    paragraphs.append(current)
                    current = []
                continue
            if cleaned[-1] not in ".!?":
                cleaned = f"{cleaned}."
            current.append(cleaned)
        if current:
            paragraphs.append(current)

        paragraph_text = [" ".join(section) for section in paragraphs if section]
        summary_text = "\n\n".join(paragraph_text).strip()
        max_chars = int(os.getenv("SUMMARY_MAX_CHARS", "2000"))
        if max_chars > 0 and len(summary_text) > max_chars:
            cutoff = max(summary_text.rfind(" ", 0, max_chars - 1), 0)
            summary_text = summary_text[: cutoff or max_chars - 1].rstrip()
            summary_text = f"{summary_text}..."
        return summary_text or "No text detected"

    vendor = pick_vendor(lines)
    total_value = pick_total(lines)
    items = pick_items(lines)
    date_value = dates[0] if dates else None

    detailed_summary = None
    if model_override:
        detailed_summary = fetch_llm_detailed_summary(validated_text)
    if not detailed_summary:
        detailed_summary = build_detailed_summary(raw_lines)
    date_text = ", ".join(dates[:5]) if dates else "Not detected"
    amount_text = ", ".join(amounts[:5]) if amounts else "Not detected"
    invoice_text = ", ".join(invoice_numbers[:5]) if invoice_numbers else "Not detected"
    email_text = ", ".join(emails[:5]) if emails else "Not detected"
    phone_text = ", ".join(phones[:5]) if phones else "Not detected"
    tax_text = ", ".join(tax_ids[:5]) if tax_ids else "Not detected"

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
        f"Detailed summary: {detailed_summary}",
        f"Keywords: {keyword_text}",
        f"Dates detected: {date_text}",
        f"Amounts detected: {amount_text}",
        "All low-confidence items reviewed by user",
    ]
    structured_fields: dict[str, str] = {
        "line_count": str(line_count),
        "word_count": str(word_count),
        "summary_points": detailed_summary,
        "detailed_summary": detailed_summary,
        "dates": date_text,
        "amounts": amount_text,
        "invoice_numbers": invoice_text,
        "emails": email_text,
        "phones": phone_text,
        "tax_ids": tax_text,
        "document_type": best_label,
        "document_type_confidence": confidence,
        "keywords": keyword_text,
        "doc_type": doc_type,
        "locale": locale,
    }

    return bullet_summary, structured_fields


def build_summary(document_id: str, model_override: str | None = None) -> dict:
    Base.metadata.create_all(bind=engine)
    logger.info("Build summary document_id=%s", document_id)
    start_time = time.perf_counter()
    with get_session() as session:
        document = session.get(Document, document_id)
        if document is None:
            raise ValueError("document_not_found")
        document_status = session.execute(
            select(Document.status).where(Document.id == document_id)
        ).scalar_one()
        if document_status not in (DocumentStatus.validated.value, DocumentStatus.summarized.value):
            raise ValueError("document_not_validated")

        doc_type_override = document.doc_type
        locale_override = document.locale

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

    bullet_summary, structured_fields = _build_summary_from_text(
        validated_text,
        model_override,
        doc_type_override=doc_type_override,
        locale_override=locale_override,
    )

    with get_session() as session:
        session.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(
                structured_fields=json.dumps(structured_fields),
                doc_type=structured_fields.get("doc_type"),
                locale=structured_fields.get("locale"),
            )
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

    SUMMARY_DURATION.labels("document").observe(time.perf_counter() - start_time)
    return {
        "bullet_summary": bullet_summary,
        "structured_fields": structured_fields,
        "validation_status": DocumentStatus.validated,
    }


def build_page_summary(document_id: str, page_id: str, model_override: str | None = None) -> dict:
    Base.metadata.create_all(bind=engine)
    logger.info("Build summary document_id=%s page_id=%s", document_id, page_id)
    start_time = time.perf_counter()
    with get_session() as session:
        page = session.get(DocumentPage, page_id)
        if page is None or page.document_id != document_id:
            raise ValueError("document_not_found")
        if page.status not in (DocumentStatus.validated.value, DocumentStatus.summarized.value):
            raise ValueError("page_not_validated")

        validated_text = page.validated_text or ""
        session.execute(
            update(DocumentPage)
            .where(DocumentPage.id == page_id)
            .values(status=DocumentStatus.summarized.value)
        )
        session.commit()

    bullet_summary, structured_fields = _build_summary_from_text(validated_text, model_override)

    with get_session() as session:
        session.execute(
            update(DocumentPage)
            .where(DocumentPage.id == page_id)
            .values(structured_fields=json.dumps(structured_fields))
        )
        session.add(
            AuditLog(
                id=uuid.uuid4().hex,
                document_id=document_id,
                page_id=page_id,
                event_type="summary_generated",
                detail=json.dumps({"field_count": len(structured_fields)}),
            )
        )
        session.commit()

    SUMMARY_DURATION.labels("page").observe(time.perf_counter() - start_time)
    return {
        "bullet_summary": bullet_summary,
        "structured_fields": structured_fields,
        "validation_status": DocumentStatus.validated,
    }
logger = logging.getLogger("vera.summary")
