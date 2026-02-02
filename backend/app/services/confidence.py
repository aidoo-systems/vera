from __future__ import annotations

import re


CURRENCY_PATTERN = re.compile(r"^(£|\$|€)\s*\d{1,3}(?:,\d{3})*(?:\.\d{2})?$")
DATE_PATTERN = re.compile(r"^(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2})$")
TOTAL_PATTERN = re.compile(r"\b(total|amount\s+due|balance\s+due|grand\s+total)\b", re.IGNORECASE)
INVOICE_PATTERN = re.compile(r"\b(invoice|inv|receipt)\s*#?\s*\d+\b", re.IGNORECASE)
MALFORMED_PRICE_PATTERN = re.compile(r"\d+\.\d$")


def classify_confidence(score: float) -> str:
    if score >= 0.92:
        return "trusted"
    if score >= 0.80:
        return "medium"
    return "low"


def detect_forced_flags(text: str) -> list[str]:
    flags: list[str] = []
    trimmed = text.strip()

    if CURRENCY_PATTERN.match(trimmed):
        flags.append("currency_amount")
    if DATE_PATTERN.match(trimmed):
        flags.append("date")
    if TOTAL_PATTERN.search(trimmed):
        flags.append("total_keyword")
    if INVOICE_PATTERN.search(trimmed):
        flags.append("invoice_number")
    if MALFORMED_PRICE_PATTERN.search(trimmed):
        flags.append("malformed_price")

    return flags
