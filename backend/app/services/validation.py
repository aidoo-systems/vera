from __future__ import annotations

from datetime import datetime
import uuid
from sqlalchemy import select

from app.db.session import Base, engine, get_session
from app.models.documents import Correction, Document, Token
from app.schemas.documents import DocumentStatus


def apply_corrections(
    document_id: str,
    corrections: list[dict],
    reviewed_token_ids: list[str],
    review_complete: bool,
) -> tuple[str, DocumentStatus, datetime | None]:
    Base.metadata.create_all(bind=engine)
    corrections_by_token = {item["token_id"]: item["corrected_text"] for item in corrections}
    reviewed_set = set(reviewed_token_ids) | set(corrections_by_token.keys())

    with get_session() as session:
        document = session.get(Document, document_id)
        if document is None:
            raise ValueError("document_not_found")

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
                )
            )
            validated_at = datetime.utcnow()
            status_value = DocumentStatus.validated
        else:
            session.execute(
                Document.__table__.update()
                .where(Document.id == document_id)
                .values(status=DocumentStatus.review_in_progress.value)
            )
            validated_at = None
            status_value = DocumentStatus.review_in_progress

        session.commit()

    return validated_text, status_value, validated_at
