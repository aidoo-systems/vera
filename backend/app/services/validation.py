from __future__ import annotations

from datetime import datetime
import json
import logging
import uuid
from sqlalchemy import func, select

from app.db.session import Base, engine, get_session
from app.models.documents import AuditLog, Correction, Document, DocumentPage, Token
from app.schemas.documents import DocumentStatus
from app.utils.time import utcnow

logger = logging.getLogger("vera.validation")


def apply_corrections(
    document_id: str,
    corrections: list[dict],
    reviewed_token_ids: list[str],
    review_complete: bool,
    structured_fields: dict[str, str] | None = None,
) -> tuple[str, DocumentStatus, datetime | None]:
    Base.metadata.create_all(bind=engine)
    corrections_by_token = {item["token_id"]: item["corrected_text"] for item in corrections}
    reviewed_set = set(reviewed_token_ids) | set(corrections_by_token.keys())

    with get_session() as session:
        document = session.get(Document, document_id)
        if document is None:
            raise ValueError("document_not_found")
        if document.status not in (DocumentStatus.ocr_done.value, DocumentStatus.review_in_progress.value):
            raise ValueError("invalid_document_status")
        logger.debug("Apply corrections document_id=%s", document_id)

        tokens = session.execute(
            select(Token)
            .where(Token.document_id == document_id)
            .order_by(Token.line_index.asc(), Token.token_index.asc())
        ).scalars().all()

        if review_complete:
            forced_token_ids = session.execute(
                select(Token.id)
                .where(Token.document_id == document_id)
                .where(Token.forced_review.is_(True))
            ).scalars().all()
            missing = [token_id for token_id in forced_token_ids if token_id not in reviewed_set]
            if missing:
                raise ValueError("review_incomplete")

        validated_lines: dict[int, list[str]] = {}
        for token in tokens:
            corrected_text = corrections_by_token.get(token.id, token.text)
            if token.id in corrections_by_token:
                correction = Correction(
                    id=uuid.uuid4().hex,
                    document_id=document_id,
                    page_id=token.page_id,
                    token_id=token.id,
                    original_text=token.text,
                    corrected_text=corrected_text,
                )
                session.add(correction)

            line_index = int(getattr(token, "line_index"))
            validated_lines.setdefault(line_index, []).append(corrected_text)

        validated_text = "\n".join(
            " ".join(validated_lines[line_index])
            for line_index in sorted(validated_lines.keys())
        )

        if review_complete:
            session.execute(
                Document.__table__.update()
                .where(Document.id == document_id)
                .values(
                    status=DocumentStatus.validated.value,
                    validated_text=validated_text,
                    review_complete_at=utcnow(),
                )
            )
            validated_at = utcnow()
            status_value = DocumentStatus.validated
        else:
            session.execute(
                Document.__table__.update()
                .where(Document.id == document_id)
                .values(status=DocumentStatus.review_in_progress.value, review_complete_at=None)
            )
            validated_at = None
            status_value = DocumentStatus.review_in_progress

        if structured_fields is not None:
            session.execute(
                Document.__table__.update()
                .where(Document.id == document_id)
                .values(structured_fields=json.dumps(structured_fields))
            )

        if corrections_by_token:
            logger.info("Corrections applied document_id=%s count=%s", document_id, len(corrections_by_token))
            session.add(
                AuditLog(
                    id=uuid.uuid4().hex,
                    document_id=document_id,
                    event_type="corrections_applied",
                    detail=json.dumps(
                        {
                            "count": len(corrections_by_token),
                            "token_ids": list(corrections_by_token.keys()),
                        }
                    ),
                )
            )

        session.add(
            AuditLog(
                id=uuid.uuid4().hex,
                document_id=document_id,
                event_type="review_completed" if review_complete else "review_saved",
                detail=json.dumps(
                    {
                        "review_complete": review_complete,
                        "reviewed_tokens": len(reviewed_set),
                    }
                ),
            )
        )

        if structured_fields is not None:
            session.add(
                AuditLog(
                    id=uuid.uuid4().hex,
                    document_id=document_id,
                    event_type="fields_updated",
                    detail=json.dumps({"field_count": len(structured_fields)}),
                )
            )

        session.commit()

    return validated_text, status_value, validated_at


def apply_page_corrections(
    document_id: str,
    page_id: str,
    corrections: list[dict],
    reviewed_token_ids: list[str],
    review_complete: bool,
    structured_fields: dict[str, str] | None = None,
    page_version: int | None = None,
) -> tuple[str, DocumentStatus, datetime | None]:
    Base.metadata.create_all(bind=engine)
    corrections_by_token = {item["token_id"]: item["corrected_text"] for item in corrections}
    reviewed_set = set(reviewed_token_ids) | set(corrections_by_token.keys())

    with get_session() as session:
        document = session.get(Document, document_id)
        page = session.get(DocumentPage, page_id)
        if document is None or page is None:
            raise ValueError("document_not_found")
        if page_version is None:
            raise ValueError("version_required")
        if document.status not in (DocumentStatus.ocr_done.value, DocumentStatus.review_in_progress.value):
            raise ValueError("invalid_document_status")
        logger.debug("Apply page corrections document_id=%s page_id=%s", document_id, page_id)

        tokens = session.execute(
            select(Token)
            .where(Token.document_id == document_id)
            .where(Token.page_id == page_id)
            .order_by(Token.line_index.asc(), Token.token_index.asc())
        ).scalars().all()

        if review_complete:
            forced_token_ids = session.execute(
                select(Token.id)
                .where(Token.document_id == document_id)
                .where(Token.page_id == page_id)
                .where(Token.forced_review.is_(True))
            ).scalars().all()
            missing = [token_id for token_id in forced_token_ids if token_id not in reviewed_set]
            if missing:
                raise ValueError("review_incomplete")

        validated_lines: dict[int, list[str]] = {}
        for token in tokens:
            corrected_text = corrections_by_token.get(token.id, token.text)
            if token.id in corrections_by_token:
                correction = Correction(
                    id=uuid.uuid4().hex,
                    document_id=document_id,
                    page_id=page_id,
                    token_id=token.id,
                    original_text=token.text,
                    corrected_text=corrected_text,
                )
                session.add(correction)

            line_index = int(getattr(token, "line_index"))
            validated_lines.setdefault(line_index, []).append(corrected_text)

        validated_text = "\n".join(
            " ".join(validated_lines[line_index])
            for line_index in sorted(validated_lines.keys())
        )

        update_values = {
            "version": DocumentPage.version + 1,
        }
        if review_complete:
            update_values.update(
                {
                    "status": DocumentStatus.validated.value,
                    "validated_text": validated_text,
                    "review_complete_at": utcnow(),
                }
            )
            validated_at = utcnow()
            status_value = DocumentStatus.validated
        else:
            update_values.update(
                {
                    "status": DocumentStatus.review_in_progress.value,
                    "review_complete_at": None,
                }
            )
            validated_at = None
            status_value = DocumentStatus.review_in_progress

        if structured_fields is not None:
            update_values["structured_fields"] = json.dumps(structured_fields)

        result = session.execute(
            DocumentPage.__table__.update()
            .where(DocumentPage.id == page_id)
            .where(DocumentPage.version == page_version)
            .values(**update_values)
        )
        if result.rowcount == 0:
            raise ValueError("version_conflict")

        if corrections_by_token:
            logger.info(
                "Corrections applied document_id=%s page_id=%s count=%s",
                document_id,
                page_id,
                len(corrections_by_token),
            )
            session.add(
                AuditLog(
                    id=uuid.uuid4().hex,
                    document_id=document_id,
                    page_id=page_id,
                    event_type="corrections_applied",
                    detail=json.dumps(
                        {
                            "count": len(corrections_by_token),
                            "token_ids": list(corrections_by_token.keys()),
                        }
                    ),
                )
            )

        session.add(
            AuditLog(
                id=uuid.uuid4().hex,
                document_id=document_id,
                page_id=page_id,
                event_type="review_completed" if review_complete else "review_saved",
                detail=json.dumps(
                    {
                        "review_complete": review_complete,
                        "reviewed_tokens": len(reviewed_set),
                    }
                ),
            )
        )

        if structured_fields is not None:
            session.add(
                AuditLog(
                    id=uuid.uuid4().hex,
                    document_id=document_id,
                    page_id=page_id,
                    event_type="fields_updated",
                    detail=json.dumps({"field_count": len(structured_fields)}),
                )
            )

        session.commit()

    with get_session() as session:
        page_count = session.execute(
            select(func.count(DocumentPage.id)).where(DocumentPage.document_id == document_id)
        ).scalar_one()
        validated_pages = session.execute(
            select(func.count(DocumentPage.id))
            .where(DocumentPage.document_id == document_id)
            .where(DocumentPage.review_complete_at.is_not(None))
        ).scalar_one()
        all_reviewed = page_count > 0 and page_count == validated_pages

        if all_reviewed:
            page_texts = session.execute(
                select(DocumentPage.validated_text)
                .where(DocumentPage.document_id == document_id)
                .order_by(DocumentPage.page_index.asc())
            ).scalars().all()
            document_text = "\n\n".join(text or "" for text in page_texts).strip()
            session.execute(
                Document.__table__.update()
                .where(Document.id == document_id)
                .values(
                    status=DocumentStatus.validated.value,
                    validated_text=document_text,
                    review_complete_at=utcnow(),
                )
            )
        else:
            session.execute(
                Document.__table__.update()
                .where(Document.id == document_id)
                .values(status=DocumentStatus.review_in_progress.value, review_complete_at=None)
            )
        session.commit()

    return validated_text, status_value, validated_at
