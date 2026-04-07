"""Shared dependencies for route modules."""

import logging
import os

from sqlalchemy import func, select

from app.models.documents import DocumentPage, Token

logger = logging.getLogger("vera")

upload_rate_limit = os.getenv("UPLOAD_RATE_LIMIT", "10/minute")


def _build_page_status(session, page: DocumentPage) -> dict:
    token_count = session.execute(
        select(func.count(Token.id)).where(Token.page_id == page.id)
    ).scalar_one()
    forced_review_count = session.execute(
        select(func.count(Token.id))
        .where(Token.page_id == page.id)
        .where(Token.forced_review.is_(True))
    ).scalar_one()
    updated_at = getattr(page, "updated_at", None)
    updated_at_value = updated_at.isoformat() if updated_at else None

    return {
        "page_id": page.id,
        "page_index": int(getattr(page, "page_index")),
        "status": page.status,
        "review_complete": bool(getattr(page, "review_complete_at")),
        "token_count": int(token_count or 0),
        "forced_review_count": int(forced_review_count or 0),
        "updated_at": updated_at_value,
        "version": int(getattr(page, "version", 1)),
    }
