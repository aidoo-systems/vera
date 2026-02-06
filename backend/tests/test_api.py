from __future__ import annotations

import json
import uuid

from fastapi.testclient import TestClient

from app.db.session import Base, engine, get_session
from app.main import app
from app.models.documents import AuditLog, Correction, Document, DocumentPage, Token
from app.schemas.documents import DocumentStatus
from app.services import summary as summary_service


client = TestClient(app)


def _reset_db() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with get_session() as session:
        session.commit()


def _create_document(status: str) -> tuple[str, str]:
    document_id = uuid.uuid4().hex
    page_id = uuid.uuid4().hex
    with get_session() as session:
        session.add(
            Document(
                id=document_id,
                image_path="/tmp/sample.png",
                image_width=100,
                image_height=200,
                status=status,
                structured_fields=json.dumps({}),
                page_count=1,
            )
        )
        session.add(
            DocumentPage(
                id=page_id,
                document_id=document_id,
                page_index=0,
                image_path="/tmp/sample.png",
                image_width=100,
                image_height=200,
                status=status,
            )
        )
        session.commit()
    return document_id, page_id


def _create_document_with_pages(status: str, page_count: int) -> tuple[str, list[str]]:
    document_id = uuid.uuid4().hex
    page_ids: list[str] = []
    with get_session() as session:
        session.add(
            Document(
                id=document_id,
                image_path="/tmp/sample.png",
                image_width=100,
                image_height=200,
                status=status,
                structured_fields=json.dumps({}),
                page_count=page_count,
            )
        )
        for index in range(page_count):
            page_id = uuid.uuid4().hex
            page_ids.append(page_id)
            session.add(
                DocumentPage(
                    id=page_id,
                    document_id=document_id,
                    page_index=index,
                    image_path=f"/tmp/sample-{index}.png",
                    image_width=100,
                    image_height=200,
                    status=status,
                )
            )
        session.commit()
    return document_id, page_ids


def _create_token(document_id: str, page_id: str, *, forced_review: bool, text: str = "Item") -> str:
    token_id = uuid.uuid4().hex
    with get_session() as session:
        session.add(
            Token(
                id=token_id,
                document_id=document_id,
                page_id=page_id,
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
    document_id, page_id = _create_document(DocumentStatus.ocr_done.value)
    _create_token(document_id, page_id, forced_review=True)

    response = client.post(
        f"/documents/{document_id}/validate",
        json={"corrections": [], "reviewed_token_ids": [], "review_complete": True},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Review incomplete"


def test_validate_allows_review_complete_with_reviewed_tokens():
    _reset_db()
    document_id, page_id = _create_document(DocumentStatus.ocr_done.value)
    token_id = _create_token(document_id, page_id, forced_review=True, text="Total")

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
    document_id, _page_id = _create_document(DocumentStatus.review_in_progress.value)

    response = client.get(f"/documents/{document_id}/summary")

    assert response.status_code == 409
    assert response.json()["detail"] == "Document not validated"


def test_summary_returns_generic_structured_fields_from_validated_text():
    _reset_db()
    document_id, _page_id = _create_document(DocumentStatus.validated.value)
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
    assert payload["structured_fields"]["detailed_summary"] == "Acme Corp. 2026-02-01. Total $12.00."


def test_summary_falls_back_to_offline_when_llm_fails(monkeypatch):
    _reset_db()
    document_id, _page_id = _create_document(DocumentStatus.validated.value)
    with get_session() as session:
        session.execute(
            Document.__table__.update()
            .where(Document.id == document_id)
            .values(validated_text="Line one\nLine two")
        )
        session.commit()

    class FailingClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, *args, **kwargs):
            raise RuntimeError("boom")

    monkeypatch.setenv("OLLAMA_RETRIES", "0")
    monkeypatch.setattr(summary_service.httpx, "Client", FailingClient)

    response = client.get(f"/documents/{document_id}/summary?model=llama3.1")

    assert response.status_code == 200
    fields = response.json()["structured_fields"]
    assert fields["detailed_summary"] == "Line one. Line two."
    assert fields["summary_points"] == fields["detailed_summary"]


def test_summary_detects_patterns_and_normalizes_amounts():
    _reset_db()
    document_id, _page_id = _create_document(DocumentStatus.validated.value)
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
    document_id, _page_id = _create_document(DocumentStatus.summarized.value)
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


def test_page_summary_requires_validated_page():
    _reset_db()
    document_id, page_id = _create_document(DocumentStatus.review_in_progress.value)

    response = client.get(f"/documents/{document_id}/pages/{page_id}/summary")

    assert response.status_code == 409
    assert response.json()["detail"] == "Review incomplete"


def test_page_summary_returns_for_validated_page():
    _reset_db()
    document_id, page_id = _create_document(DocumentStatus.review_in_progress.value)
    with get_session() as session:
        session.execute(
            DocumentPage.__table__.update()
            .where(DocumentPage.id == page_id)
            .values(status=DocumentStatus.validated.value, validated_text="Acme Corp")
        )
        session.commit()

    response = client.get(f"/documents/{document_id}/pages/{page_id}/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["structured_fields"]["line_count"] == "1"


def test_page_export_requires_validated_page():
    _reset_db()
    document_id, page_id = _create_document(DocumentStatus.review_in_progress.value)

    response = client.get(f"/documents/{document_id}/pages/{page_id}/export?format=json")

    assert response.status_code == 409
    assert response.json()["detail"] == "Review incomplete"


def test_page_export_allows_validated_page():
    _reset_db()
    document_id, page_id = _create_document(DocumentStatus.review_in_progress.value)
    with get_session() as session:
        session.execute(
            DocumentPage.__table__.update()
            .where(DocumentPage.id == page_id)
            .values(status=DocumentStatus.validated.value, validated_text="Acme Corp")
        )
        session.commit()

    response = client.get(f"/documents/{document_id}/pages/{page_id}/export?format=json")

    assert response.status_code == 200
    payload = response.json()
    assert payload["page_id"] == page_id
    assert payload["validated_text"] == "Acme Corp"


def test_page_validate_requires_version():
    _reset_db()
    document_id, page_id = _create_document(DocumentStatus.review_in_progress.value)

    response = client.post(
        f"/documents/{document_id}/pages/{page_id}/validate",
        json={"corrections": [], "reviewed_token_ids": [], "review_complete": True},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Page version is required"


def test_page_validate_rejects_version_conflict():
    _reset_db()
    document_id, page_id = _create_document(DocumentStatus.review_in_progress.value)

    ok_response = client.post(
        f"/documents/{document_id}/pages/{page_id}/validate",
        json={"corrections": [], "reviewed_token_ids": [], "review_complete": True, "page_version": 1},
    )
    assert ok_response.status_code == 200

    conflict_response = client.post(
        f"/documents/{document_id}/pages/{page_id}/validate",
        json={"corrections": [], "reviewed_token_ids": [], "review_complete": True, "page_version": 1},
    )
    assert conflict_response.status_code == 409
    assert conflict_response.json()["detail"] == "Review out of date"


def test_document_summary_requires_all_pages_reviewed():
    _reset_db()
    document_id, page_ids = _create_document_with_pages(DocumentStatus.review_in_progress.value, 2)

    response = client.post(
        f"/documents/{document_id}/pages/{page_ids[0]}/validate",
        json={"corrections": [], "reviewed_token_ids": [], "review_complete": True, "page_version": 1},
    )

    assert response.status_code == 200
    summary_response = client.get(f"/documents/{document_id}/summary")
    assert summary_response.status_code == 409
    assert summary_response.json()["detail"] == "Document not validated"


def test_document_export_requires_all_pages_reviewed():
    _reset_db()
    document_id, page_ids = _create_document_with_pages(DocumentStatus.review_in_progress.value, 2)

    response = client.post(
        f"/documents/{document_id}/pages/{page_ids[0]}/validate",
        json={"corrections": [], "reviewed_token_ids": [], "review_complete": True, "page_version": 1},
    )

    assert response.status_code == 200
    export_response = client.get(f"/documents/{document_id}/export?format=json")
    assert export_response.status_code == 409
    assert export_response.json()["detail"] == "Document not validated"


def test_page_status_endpoint_returns_counts():
    _reset_db()
    document_id, page_id = _create_document(DocumentStatus.ocr_done.value)
    _create_token(document_id, page_id, forced_review=True, text="Item")

    response = client.get(f"/documents/{document_id}/pages/{page_id}/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["page_id"] == page_id
    assert payload["token_count"] == 1
    assert payload["forced_review_count"] == 1


def test_document_status_endpoint_returns_pages():
    _reset_db()
    document_id, page_ids = _create_document_with_pages(DocumentStatus.ocr_done.value, 2)

    response = client.get(f"/documents/{document_id}/pages/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["document_id"] == document_id
    assert len(payload["pages"]) == 2
