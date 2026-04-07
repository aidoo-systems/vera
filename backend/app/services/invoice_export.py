"""Invoice export service — converts VERA's structured_fields into standards-compliant XML.

Supported formats:
  - Factur-X MINIMUM (EN 16931, profile urn:factur-x.eu:1p0:minimum)
  - UBL 2.1 Invoice (ISO/IEC 19845, PEPPOL-compatible)

Both formats use InvoiceData as the typed intermediate representation.
Missing mandatory fields produce best-effort output (empty element) plus a warning
entry in InvoiceData.warnings, surfaced to callers via the X-VERA-Warnings header.
"""

from __future__ import annotations

import json
import re
from datetime import datetime

from lxml import etree

from app.schemas.invoice import InvoiceData

_SENTINEL = "Not detected"


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _coerce(val: str | None) -> str | None:
    """Return None for empty strings, whitespace-only strings, and the 'Not detected' sentinel."""
    if val is None:
        return None
    stripped = val.strip()
    if not stripped or stripped == _SENTINEL:
        return None
    return stripped


def _split_first(val: str | None) -> str | None:
    """Take the first comma-separated value from a field like 'dates' or 'invoice_numbers'."""
    v = _coerce(val)
    if not v:
        return None
    return _coerce(v.split(",")[0])


def _split_last(val: str | None) -> str | None:
    """Take the last comma-separated value — used for invoice_total (last = highest total)."""
    v = _coerce(val)
    if not v:
        return None
    return _coerce(v.split(",")[-1])


def _split_list(val: str | None) -> list[str]:
    """Split a comma-joined field into a filtered list."""
    v = _coerce(val)
    if not v:
        return []
    return [s.strip() for s in v.split(",") if s.strip() and s.strip() != _SENTINEL]


def _parse_date(date_str: str | None) -> tuple[str | None, str | None]:
    """Parse a raw date string into (facturx_date, ubl_date).

    Factur-X requires YYYYMMDD (format="102" in CII DateTimeString).
    UBL 2.1 requires YYYY-MM-DD (xsd:date).

    Returns (None, None) if the string cannot be parsed.
    """
    if not date_str:
        return None, None
    date_str = date_str.strip()

    # Fast path: already ISO 8601 YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
        return date_str.replace("-", ""), date_str

    formats = [
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d-%m-%Y",
        "%d.%m.%Y",
        "%B %d, %Y",
        "%d %B %Y",
        "%b %d, %Y",
        "%d %b %Y",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            ubl = dt.strftime("%Y-%m-%d")
            fx = dt.strftime("%Y%m%d")
            return fx, ubl
        except ValueError:
            continue
    return None, None


def _clean_amount(amount_str: str | None) -> str | None:
    """Strip currency prefix from an amount string, leaving a bare decimal.

    e.g. 'USD 1,234.50' → '1234.50', '£ 99.00' → '99.00'
    """
    if not amount_str:
        return None
    cleaned = re.sub(r"^(?:USD|EUR|GBP|AUD|CAD|[£$€])\s*", "", amount_str.strip())
    # Normalise thousands separator: remove commas in US-style amounts
    cleaned = cleaned.replace(",", "")
    return cleaned.strip() or None


# ---------------------------------------------------------------------------
# Public: build typed model from flat structured_fields dict
# ---------------------------------------------------------------------------


def build_invoice_data(structured_fields: dict) -> InvoiceData:
    """Map VERA's flat structured_fields dict to a typed InvoiceData model.

    All mandatory fields that are missing or undetected produce a warning entry.
    BT-44 (buyer_name) is always warned — VERA cannot extract buyer identity from OCR.
    """
    warnings: list[str] = []

    invoice_number = _split_first(structured_fields.get("invoice_numbers"))
    invoice_date = _split_first(structured_fields.get("dates"))
    currency_code = _coerce(structured_fields.get("currency_code"))
    seller_name = _coerce(structured_fields.get("vendor_name"))
    invoice_total = _split_last(structured_fields.get("amounts"))

    # Parse line_items — stored as JSON list since summary.py fix
    raw_items = structured_fields.get("line_items", "[]")
    try:
        line_items = json.loads(raw_items) if raw_items else []
        if not isinstance(line_items, list):
            line_items = []
    except (json.JSONDecodeError, TypeError):
        line_items = []

    # Emit warnings for missing mandatory fields
    if not invoice_number:
        warnings.append("BT-1 invoice_number not detected")
    if not invoice_date:
        warnings.append("BT-2 invoice_date not detected")
    if not currency_code:
        warnings.append("BT-4 currency_code not detected")
    if not seller_name:
        warnings.append("BT-27 seller_name not detected")
    # BT-44 buyer_name: structurally absent — always warn
    warnings.append("BT-44 buyer_name not extractable from OCR")
    if not invoice_total:
        warnings.append("BT-112 invoice_total not detected")

    return InvoiceData(
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        currency_code=currency_code,
        seller_name=seller_name,
        buyer_name=None,
        invoice_total=invoice_total,
        tax_ids=_split_list(structured_fields.get("tax_ids")),
        emails=_split_list(structured_fields.get("emails")),
        line_items=line_items,
        doc_type=_coerce(structured_fields.get("doc_type")),
        locale=_coerce(structured_fields.get("locale")),
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Public: Factur-X MINIMUM XML
# ---------------------------------------------------------------------------

_FX_RSM = "urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100"
_FX_RAM = "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
_FX_UDT = "urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100"


def to_facturx_xml(invoice: InvoiceData, document_id: str) -> bytes:
    """Generate a Factur-X MINIMUM XML document (CII syntax).

    Profile: urn:factur-x.eu:1p0:minimum
    Missing mandatory fields are emitted as empty elements; callers receive
    warnings via InvoiceData.warnings / X-VERA-Warnings response header.
    """
    nsmap = {"rsm": _FX_RSM, "ram": _FX_RAM, "udt": _FX_UDT}
    root = etree.Element(f"{{{_FX_RSM}}}CrossIndustryInvoice", nsmap=nsmap)

    # --- ExchangedDocumentContext ---
    ctx = etree.SubElement(root, f"{{{_FX_RSM}}}ExchangedDocumentContext")
    guideline = etree.SubElement(ctx, f"{{{_FX_RAM}}}GuidelineSpecifiedDocumentContextParameter")
    etree.SubElement(guideline, f"{{{_FX_RAM}}}ID").text = "urn:factur-x.eu:1p0:minimum"

    # --- ExchangedDocument ---
    doc = etree.SubElement(root, f"{{{_FX_RSM}}}ExchangedDocument")
    etree.SubElement(doc, f"{{{_FX_RAM}}}ID").text = invoice.invoice_number or ""
    etree.SubElement(doc, f"{{{_FX_RAM}}}TypeCode").text = "380"  # Commercial Invoice

    fx_date, _ = _parse_date(invoice.invoice_date)
    issue_dt = etree.SubElement(doc, f"{{{_FX_RAM}}}IssueDateTime")
    dt_str = etree.SubElement(issue_dt, f"{{{_FX_UDT}}}DateTimeString")
    dt_str.set("format", "102")
    dt_str.text = fx_date or ""

    # --- SupplyChainTradeTransaction ---
    txn = etree.SubElement(root, f"{{{_FX_RSM}}}SupplyChainTradeTransaction")

    agreement = etree.SubElement(txn, f"{{{_FX_RAM}}}ApplicableHeaderTradeAgreement")

    seller = etree.SubElement(agreement, f"{{{_FX_RAM}}}SellerTradeParty")
    etree.SubElement(seller, f"{{{_FX_RAM}}}Name").text = invoice.seller_name or ""

    buyer = etree.SubElement(agreement, f"{{{_FX_RAM}}}BuyerTradeParty")
    etree.SubElement(buyer, f"{{{_FX_RAM}}}Name").text = invoice.buyer_name or ""

    settlement = etree.SubElement(txn, f"{{{_FX_RAM}}}ApplicableHeaderTradeSettlement")
    etree.SubElement(settlement, f"{{{_FX_RAM}}}InvoiceCurrencyCode").text = invoice.currency_code or ""

    monetary = etree.SubElement(settlement, f"{{{_FX_RAM}}}SpecifiedTradeSettlementHeaderMonetarySummation")
    tax_incl = etree.SubElement(monetary, f"{{{_FX_RAM}}}TaxInclusiveAmount")
    tax_incl.text = _clean_amount(invoice.invoice_total) or ""

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)


# ---------------------------------------------------------------------------
# Public: UBL 2.1 Invoice XML
# ---------------------------------------------------------------------------

_UBL_INV = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
_UBL_CBC = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
_UBL_CAC = "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"


def to_ubl_xml(invoice: InvoiceData, document_id: str) -> bytes:
    """Generate a UBL 2.1 Invoice XML document.

    Covers the EN 16931 MINIMUM field set.
    Missing mandatory fields are emitted as empty elements; callers receive
    warnings via InvoiceData.warnings / X-VERA-Warnings response header.
    """
    nsmap = {
        None: _UBL_INV,
        "cbc": _UBL_CBC,
        "cac": _UBL_CAC,
    }
    root = etree.Element(f"{{{_UBL_INV}}}Invoice", nsmap=nsmap)

    cbc = _UBL_CBC
    cac = _UBL_CAC

    etree.SubElement(root, f"{{{cbc}}}UBLVersionID").text = "2.1"
    etree.SubElement(root, f"{{{cbc}}}CustomizationID").text = "urn:cen.eu:en16931:2017"
    etree.SubElement(root, f"{{{cbc}}}ID").text = invoice.invoice_number or ""

    _, ubl_date = _parse_date(invoice.invoice_date)
    etree.SubElement(root, f"{{{cbc}}}IssueDate").text = ubl_date or ""

    etree.SubElement(root, f"{{{cbc}}}InvoiceTypeCode").text = "380"
    etree.SubElement(root, f"{{{cbc}}}DocumentCurrencyCode").text = invoice.currency_code or ""

    # AccountingSupplierParty (seller)
    supplier = etree.SubElement(root, f"{{{cac}}}AccountingSupplierParty")
    supplier_party = etree.SubElement(supplier, f"{{{cac}}}Party")
    supplier_name_el = etree.SubElement(supplier_party, f"{{{cac}}}PartyName")
    etree.SubElement(supplier_name_el, f"{{{cbc}}}Name").text = invoice.seller_name or ""

    # AccountingCustomerParty (buyer)
    customer = etree.SubElement(root, f"{{{cac}}}AccountingCustomerParty")
    customer_party = etree.SubElement(customer, f"{{{cac}}}Party")
    customer_name_el = etree.SubElement(customer_party, f"{{{cac}}}PartyName")
    etree.SubElement(customer_name_el, f"{{{cbc}}}Name").text = invoice.buyer_name or ""

    # LegalMonetaryTotal
    totals = etree.SubElement(root, f"{{{cac}}}LegalMonetaryTotal")
    tax_incl = etree.SubElement(totals, f"{{{cbc}}}TaxInclusiveAmount")
    tax_incl.set("currencyID", invoice.currency_code or "")
    tax_incl.text = _clean_amount(invoice.invoice_total) or ""

    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)
