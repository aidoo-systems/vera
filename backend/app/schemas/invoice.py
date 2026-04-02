from __future__ import annotations

from pydantic import BaseModel, Field


class InvoiceData(BaseModel):
    """Typed intermediate representation for invoice exports (Factur-X MINIMUM / UBL 2.1).

    All fields are optional — VERA uses best-effort extraction.
    Missing mandatory fields are listed in `warnings`.

    EN 16931 business term (BT) references for the MINIMUM profile:
      BT-1   invoice_number
      BT-2   invoice_date
      BT-4   currency_code
      BT-27  seller_name
      BT-44  buyer_name  (always None — not OCR-extractable)
      BT-112 invoice_total
    """

    # --- Factur-X MINIMUM / UBL mandatory ---
    invoice_number: str | None = None
    invoice_date: str | None = None       # raw string; normalised at serialisation time
    currency_code: str | None = None      # ISO 4217 (EUR, GBP, USD, …)
    seller_name: str | None = None
    buyer_name: str | None = None         # structurally absent — always None
    invoice_total: str | None = None      # raw string including currency prefix

    # --- Contextual extras (non-mandatory, included when available) ---
    tax_ids: list[str] = Field(default_factory=list)
    emails: list[str] = Field(default_factory=list)
    line_items: list[str] = Field(default_factory=list)
    doc_type: str | None = None
    locale: str | None = None

    # --- Populated by build_invoice_data for missing/uncertain mandatory fields ---
    warnings: list[str] = Field(default_factory=list)
