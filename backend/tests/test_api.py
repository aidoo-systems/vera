from __future__ import annotations

import json
import uuid

from fastapi.testclient import TestClient

from app.db.session import Base, engine, get_session
from app.main import app
from app.models.documents import AuditLog, Correction, Document, Token
from app.schemas.documents import DocumentStatus


client = TestClient(app)


def _reset_db() -> None:
    Base.metadata.create_all(bind=engine)
    with get_session() as session:
        session.execute(AuditLog.__table__.delete())
        session.execute(Correction.__table__.delete())
        session.execute(Token.__table__.delete())
        session.execute(Document.__table__.delete())
        session.commit()


def _create_document(status: str) -> str:
    document_id = uuid.uuid4().hex
    with get_session() as session:
        session.add(
            Document(
                id=document_id,
                image_path="/tmp/sample.png",
                image_width=100,
                image_height=200,
                status=status,
                structured_fields=json.dumps({}),
            )
        )
        session.commit()
    return document_id


def _create_token(document_id: str, *, forced_review: bool, text: str = "Item") -> str:
    token_id = uuid.uuid4().hex
    with get_session() as session:
        session.add(
            Token(
                id=token_id,
                document_id=document_id,
                line_index=0,
                token_index=0,
                text=text,
                confidence=0.5,
                confidence_label="low",
                forced_review=forced_review,
                line_id="line-0",
                bbox=json.dumps([0.0, 0.0, 10.0, 10.0]),
                flags=json.dumps([]),
            )
        )
        session.commit()
    return token_id


def test_validate_requires_review_for_forced_tokens():
    _reset_db()
    document_id = _create_document(DocumentStatus.ocr_done.value)
    _create_token(document_id, forced_review=True)

    response = client.post(
        f"/documents/{document_id}/validate",
        json={"corrections": [], "reviewed_token_ids": [], "review_complete": True},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Review incomplete"


def test_validate_allows_review_complete_with_reviewed_tokens():
    _reset_db()
    document_id = _create_document(DocumentStatus.ocr_done.value)
    token_id = _create_token(document_id, forced_review=True, text="Total")

    response = client.post(
        f"/documents/{document_id}/validate",
        json={
            "corrections": [{"token_id": token_id, "corrected_text": "Total"}],
            "reviewed_token_ids": [token_id],
            "review_complete": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["validation_status"] == DocumentStatus.validated.value
    assert payload["validated_text"].strip() == "Total"


def test_summary_requires_validated_document():
    _reset_db()
    document_id = _create_document(DocumentStatus.review_in_progress.value)

    response = client.get(f"/documents/{document_id}/summary")

    assert response.status_code == 409
    assert response.json()["detail"] == "Document not validated"


def test_summary_returns_generic_structured_fields_from_validated_text():
    _reset_db()
    document_id = _create_document(DocumentStatus.validated.value)
    with get_session() as session:
        session.execute(
            Document.__table__.update()
            .where(Document.id == document_id)
            .values(validated_text="Acme Corp\n2026-02-01\nTotal $12.00")
        )
        session.commit()

    response = client.get(f"/documents/{document_id}/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["structured_fields"]["line_count"] == "3"
    assert payload["structured_fields"]["word_count"] == "5"
    assert payload["structured_fields"]["dates"] == "2026-02-01"
    assert payload["structured_fields"]["amounts"] == "$12.00"
    assert payload["structured_fields"]["document_type"] == "Invoice/Receipt"
    assert payload["structured_fields"]["document_type_confidence"] == "low"
    assert payload["structured_fields"]["keywords"] == "acme, corp, total"


def test_summary_detects_patterns_and_normalizes_amounts():
    _reset_db()
    document_id = _create_document(DocumentStatus.validated.value)
    validated_text = "\n".join(
        [
            "Invoice # INV-1007",
            "Date: 03/02/2026",
            "Total 59,99",
            "VAT ID: GB123456789",
            "Contact: billing@example.com",
            "+1 (415) 555-0100",
            "USD 1,234.50",
        ]
    )
    with get_session() as session:
        session.execute(
            Document.__table__.update()
            .where(Document.id == document_id)
            .values(validated_text=validated_text)
        )
        session.commit()

    response = client.get(f"/documents/{document_id}/summary")

    assert response.status_code == 200
    fields = response.json()["structured_fields"]
    assert fields["invoice_numbers"] == "INV-1007"
    assert fields["tax_ids"] == "GB123456789"
    assert fields["emails"] == "billing@example.com"
    assert fields["phones"] == "+1 (415) 555-0100"
    assert "59.99" in fields["amounts"]
    assert "USD 1234.50" in fields["amounts"]


def test_export_allows_summarized_documents():
    _reset_db()
    document_id = _create_document(DocumentStatus.summarized.value)
    with get_session() as session:
        session.execute(
            Document.__table__.update()
            .where(Document.id == document_id)
            .values(validated_text="Acme Corp")
        )
        session.commit()

    response = client.get(f"/documents/{document_id}/export?format=json")

    assert response.status_code == 200
    payload = response.json()
    assert payload["document_id"] == document_id
    assert payload["validated_text"] == "Acme Corp"
