"""Tests for invoice export service — Factur-X MINIMUM and UBL 2.1 XML generation."""

from __future__ import annotations

import json
import uuid

import pytest
from lxml import etree

from app.schemas.invoice import InvoiceData
from app.services.invoice_export import (
    _clean_amount,
    _coerce,
    _parse_date,
    build_invoice_data,
    to_facturx_xml,
    to_ubl_xml,
)
from app.services.summary import _extract_currency_code

# ---------------------------------------------------------------------------
# _coerce
# ---------------------------------------------------------------------------


def test_coerce_empty_string_returns_none():
    assert _coerce("") is None


def test_coerce_whitespace_only_returns_none():
    assert _coerce("   ") is None


def test_coerce_sentinel_returns_none():
    assert _coerce("Not detected") is None
    assert _coerce("  Not detected  ") is None


def test_coerce_valid_value_strips_whitespace():
    assert _coerce("  INV-001  ") == "INV-001"


def test_coerce_none_input_returns_none():
    assert _coerce(None) is None


# ---------------------------------------------------------------------------
# _extract_currency_code
# ---------------------------------------------------------------------------


def test_extract_iso_code_eur():
    assert _extract_currency_code("EUR 1234.00") == "EUR"


def test_extract_iso_code_gbp():
    assert _extract_currency_code("GBP 99.50") == "GBP"


def test_extract_iso_code_case_insensitive():
    assert _extract_currency_code("eur 100.00") == "EUR"


def test_extract_iso_code_takes_priority_over_symbol():
    assert _extract_currency_code("GBP £1234.00") == "GBP"


def test_extract_pound_symbol():
    assert _extract_currency_code("£ 50.00") == "GBP"


def test_extract_euro_symbol():
    assert _extract_currency_code("€ 50.00") == "EUR"


def test_extract_dollar_defaults_to_usd():
    assert _extract_currency_code("$1234.50") == "USD"


def test_extract_no_signal_returns_none():
    assert _extract_currency_code("1234.50") is None


def test_extract_empty_returns_none():
    assert _extract_currency_code("") is None


# ---------------------------------------------------------------------------
# _parse_date
# ---------------------------------------------------------------------------


def test_parse_date_iso8601_fast_path():
    fx, ubl = _parse_date("2026-02-01")
    assert fx == "20260201"
    assert ubl == "2026-02-01"


def test_parse_date_european_dot():
    fx, ubl = _parse_date("01.02.2026")
    assert fx == "20260201"
    assert ubl == "2026-02-01"


def test_parse_date_slash_dmy():
    fx, ubl = _parse_date("01/02/2026")
    assert ubl == "2026-02-01"


def test_parse_date_month_name_full():
    fx, ubl = _parse_date("February 1, 2026")
    assert fx == "20260201"
    assert ubl == "2026-02-01"


def test_parse_date_month_name_abbrev():
    fx, ubl = _parse_date("Feb 1, 2026")
    assert ubl == "2026-02-01"


def test_parse_date_garbage_returns_none_none():
    assert _parse_date("not-a-date") == (None, None)


def test_parse_date_none_returns_none_none():
    assert _parse_date(None) == (None, None)


# ---------------------------------------------------------------------------
# _clean_amount
# ---------------------------------------------------------------------------


def test_clean_amount_strips_usd_prefix():
    assert _clean_amount("USD 1,234.50") == "1234.50"


def test_clean_amount_strips_pound_symbol():
    assert _clean_amount("£99.00") == "99.00"


def test_clean_amount_strips_euro_symbol():
    assert _clean_amount("€ 100.00") == "100.00"


def test_clean_amount_bare_decimal_unchanged():
    assert _clean_amount("1234.50") == "1234.50"


def test_clean_amount_none_returns_none():
    assert _clean_amount(None) is None


# ---------------------------------------------------------------------------
# build_invoice_data
# ---------------------------------------------------------------------------


_FULL_FIELDS: dict = {
    "invoice_numbers": "INV-2026-001, INV-2026-002",
    "dates": "2026-02-01, 2026-03-01",
    "currency_code": "EUR",
    "vendor_name": "Acme Corp",
    "amounts": "EUR 100.00, EUR 20.00, EUR 120.00",
    "tax_ids": "VAT-12345",
    "emails": "accounts@acme.com",
    "line_items": json.dumps(["Widget x2 EUR 20.00"]),
    "doc_type": "invoice",
    "locale": "EU",
}


def test_build_invoice_data_full_fields():
    inv = build_invoice_data(_FULL_FIELDS)
    assert inv.invoice_number == "INV-2026-001"
    assert inv.invoice_date == "2026-02-01"
    assert inv.currency_code == "EUR"
    assert inv.seller_name == "Acme Corp"
    assert inv.buyer_name is None
    assert inv.invoice_total == "EUR 120.00"
    assert inv.tax_ids == ["VAT-12345"]
    assert inv.emails == ["accounts@acme.com"]
    assert inv.line_items == ["Widget x2 EUR 20.00"]
    assert inv.doc_type == "invoice"
    assert inv.locale == "EU"


def test_build_invoice_data_only_bt44_warning_when_full():
    inv = build_invoice_data(_FULL_FIELDS)
    assert len(inv.warnings) == 1
    assert "BT-44" in inv.warnings[0]


def test_build_invoice_data_empty_dict_all_none():
    inv = build_invoice_data({})
    assert inv.invoice_number is None
    assert inv.invoice_date is None
    assert inv.currency_code is None
    assert inv.seller_name is None
    assert inv.invoice_total is None


def test_build_invoice_data_empty_dict_six_warnings():
    inv = build_invoice_data({})
    assert len(inv.warnings) == 6  # BT-1, BT-2, BT-4, BT-27, BT-44, BT-112


def test_build_invoice_data_not_detected_sentinel_treated_as_none():
    inv = build_invoice_data({"invoice_numbers": "Not detected", "dates": "Not detected"})
    assert inv.invoice_number is None
    assert inv.invoice_date is None


def test_build_invoice_data_invoice_total_uses_last_amount():
    inv = build_invoice_data({"amounts": "USD 10.00, USD 20.00, USD 199.99"})
    assert inv.invoice_total == "USD 199.99"


def test_build_invoice_data_line_items_invalid_json_returns_empty():
    inv = build_invoice_data({"line_items": "not valid json"})
    assert inv.line_items == []


def test_build_invoice_data_buyer_name_always_none():
    inv = build_invoice_data(_FULL_FIELDS)
    assert inv.buyer_name is None


# ---------------------------------------------------------------------------
# to_facturx_xml — structural tests
# ---------------------------------------------------------------------------


def _fx_invoice() -> InvoiceData:
    return InvoiceData(
        invoice_number="INV-001",
        invoice_date="2026-02-01",
        currency_code="EUR",
        seller_name="Acme Corp",
        buyer_name=None,
        invoice_total="EUR 120.00",
        warnings=["BT-44 buyer_name not extractable from OCR"],
    )


def test_facturx_xml_is_well_formed():
    xml = to_facturx_xml(_fx_invoice(), "doc-123")
    etree.fromstring(xml)  # raises if malformed


def test_facturx_xml_root_tag():
    xml = to_facturx_xml(_fx_invoice(), "doc-123")
    root = etree.fromstring(xml)
    assert root.tag.endswith("CrossIndustryInvoice")


def test_facturx_xml_minimum_profile_id():
    xml = to_facturx_xml(_fx_invoice(), "doc-123")
    root = etree.fromstring(xml)
    ns = "urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100"
    ids = root.findall(f".//{{{ns}}}ID")
    profile_ids = [el.text for el in ids if el.text and "factur-x" in el.text]
    assert any("minimum" in pid for pid in profile_ids)


def test_facturx_xml_invoice_number_present():
    xml = to_facturx_xml(_fx_invoice(), "doc-123")
    assert b"INV-001" in xml


def test_facturx_xml_seller_name_present():
    xml = to_facturx_xml(_fx_invoice(), "doc-123")
    assert b"Acme Corp" in xml


def test_facturx_xml_currency_code_present():
    xml = to_facturx_xml(_fx_invoice(), "doc-123")
    assert b"EUR" in xml


def test_facturx_xml_all_none_still_well_formed():
    inv = InvoiceData()
    xml = to_facturx_xml(inv, "doc-empty")
    etree.fromstring(xml)  # must not raise


# ---------------------------------------------------------------------------
# to_ubl_xml — structural tests
# ---------------------------------------------------------------------------


def _ubl_invoice() -> InvoiceData:
    return InvoiceData(
        invoice_number="INV-001",
        invoice_date="2026-02-01",
        currency_code="GBP",
        seller_name="Widget Ltd",
        buyer_name=None,
        invoice_total="GBP 250.00",
        warnings=["BT-44 buyer_name not extractable from OCR"],
    )


def test_ubl_xml_is_well_formed():
    xml = to_ubl_xml(_ubl_invoice(), "doc-456")
    etree.fromstring(xml)


def test_ubl_xml_root_tag():
    xml = to_ubl_xml(_ubl_invoice(), "doc-456")
    root = etree.fromstring(xml)
    assert root.tag.endswith("Invoice")


def test_ubl_xml_ubl_version():
    xml = to_ubl_xml(_ubl_invoice(), "doc-456")
    assert b"2.1" in xml


def test_ubl_xml_currency_in_tax_inclusive_amount_attribute():
    xml = to_ubl_xml(_ubl_invoice(), "doc-456")
    root = etree.fromstring(xml)
    cbc = "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
    amounts = root.findall(f".//{{{cbc}}}TaxInclusiveAmount")
    assert amounts, "TaxInclusiveAmount element not found"
    assert amounts[0].get("currencyID") == "GBP"


def test_ubl_xml_invoice_number_present():
    xml = to_ubl_xml(_ubl_invoice(), "doc-456")
    assert b"INV-001" in xml


def test_ubl_xml_all_none_still_well_formed():
    inv = InvoiceData()
    xml = to_ubl_xml(inv, "doc-empty")
    etree.fromstring(xml)


# ---------------------------------------------------------------------------
# Integration tests — export API endpoints
# ---------------------------------------------------------------------------


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


@pytest.fixture()
def validated_document(tmp_path):
    """Create a Document in validated status with structured_fields."""
    from app.db.session import Base, engine, get_session
    from app.models.documents import Document
    from app.schemas.documents import DocumentStatus

    Base.metadata.create_all(bind=engine)

    doc_id = uuid.uuid4().hex
    fields = json.dumps({
        "invoice_numbers": "INV-2026-TEST",
        "dates": "2026-02-01",
        "currency_code": "EUR",
        "vendor_name": "Test Corp",
        "amounts": "EUR 99.00",
        "tax_ids": "",
        "emails": "",
        "line_items": "[]",
        "doc_type": "invoice",
        "locale": "EU",
    })
    with get_session() as session:
        doc = Document(
            id=doc_id,
            image_path=str(tmp_path / "test.jpg"),
            image_width=100,
            image_height=100,
            status=DocumentStatus.validated.value,
            validated_text="Test Corp\nInvoice INV-2026-TEST\nTotal EUR 99.00",
            structured_fields=fields,
            page_count=1,
            version=1,
        )
        session.add(doc)
        session.commit()
    return doc_id


def test_export_facturx_returns_xml(client, validated_document):
    resp = client.get(f"/documents/{validated_document}/export?format=facturx")
    assert resp.status_code == 200
    assert "application/xml" in resp.headers["content-type"]
    assert resp.content.startswith(b"<?xml")


def test_export_ubl_returns_xml(client, validated_document):
    resp = client.get(f"/documents/{validated_document}/export?format=ubl")
    assert resp.status_code == 200
    assert "application/xml" in resp.headers["content-type"]
    assert resp.content.startswith(b"<?xml")


def test_export_facturx_content_disposition(client, validated_document):
    resp = client.get(f"/documents/{validated_document}/export?format=facturx")
    assert "attachment" in resp.headers.get("content-disposition", "")
    assert ".xml" in resp.headers.get("content-disposition", "")


def test_export_warnings_header_present_when_fields_missing(client, tmp_path):
    from app.db.session import Base, engine, get_session
    from app.models.documents import Document
    from app.schemas.documents import DocumentStatus

    Base.metadata.create_all(bind=engine)

    doc_id = uuid.uuid4().hex
    with get_session() as session:
        doc = Document(
            id=doc_id,
            image_path=str(tmp_path / "empty.jpg"),
            image_width=100,
            image_height=100,
            status=DocumentStatus.validated.value,
            validated_text="",
            structured_fields="{}",
            page_count=1,
            version=1,
        )
        session.add(doc)
        session.commit()

    resp = client.get(f"/documents/{doc_id}/export?format=facturx")
    assert resp.status_code == 200
    assert "BT-44" in resp.headers.get("x-vera-warnings", "")


def test_export_existing_json_format_unaffected(client, validated_document):
    resp = client.get(f"/documents/{validated_document}/export?format=json")
    assert resp.status_code == 200
    data = resp.json()
    assert "structured_fields" in data
