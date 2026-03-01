from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta

try:
    from celery import Celery
    from celery.schedules import crontab
except ImportError:  # pragma: no cover
    Celery = None
    crontab = None

from app.db.session import Base, engine, get_session
from sqlalchemy import select

from app.models.documents import AuditLog, Document, DocumentPage
from app.schemas.documents import DocumentStatus
from app.services.ocr import run_ocr_for_page
from app.services.retention import cleanup_documents

logger = logging.getLogger(__name__)

if Celery is None:  # pragma: no cover
    class _CeleryStub:
        def send_task(self, *args, **kwargs):
            raise RuntimeError("celery_not_installed")

        def task(self, *args, **kwargs):
            def decorator(func):
                return func

            return decorator

        def conf_update(self, *args, **kwargs):
            return None

    celery_app = _CeleryStub()
else:
    celery_app = Celery(
        "vera",
        broker=os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0"),
        backend=os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/0"),
    )
    celery_app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        task_track_started=True,
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
    )
    cleanup_interval_minutes = int(os.getenv("RETENTION_INTERVAL_MINUTES", "1440"))
    beat_schedule: dict = {
        "recover-stuck-documents": {
            "task": "vera.recover_stuck_documents",
            "schedule": crontab(minute="*/5"),
        },
    }
    if cleanup_interval_minutes > 0:
        beat_schedule["vera.cleanup_documents"] = {
            "task": "vera.cleanup_documents",
            "schedule": timedelta(minutes=cleanup_interval_minutes),
        }
    celery_app.conf.update(beat_schedule=beat_schedule)


@celery_app.task(name="vera.process_document")
def process_document(document_id: str) -> dict[str, str]:
    Base.metadata.create_all(bind=engine)
    with get_session() as session:
        document = session.get(Document, document_id)
        if document is None:
            return {"status": "missing"}
        session.execute(
            Document.__table__.update()
            .where(Document.id == document_id)
            .values(status=DocumentStatus.processing.value)
        )
        session.execute(
            DocumentPage.__table__.update()
            .where(DocumentPage.document_id == document_id)
            .values(status=DocumentStatus.processing.value)
        )
        session.commit()

    try:
        with get_session() as session:
            pages = session.execute(
                select(DocumentPage)
                .where(DocumentPage.document_id == document_id)
                .order_by(DocumentPage.page_index.asc())
            ).scalars().all()

        for page in pages:
            image_path = str(getattr(page, "image_path"))
            image_url = f"/files/{os.path.basename(image_path)}"
            result = run_ocr_for_page(document_id, page.id, image_path, image_url)
            if result.status == DocumentStatus.canceled:
                return {"status": "canceled"}

        with get_session() as session:
            session.execute(
                Document.__table__.update()
                .where(Document.id == document_id)
                .values(status=DocumentStatus.ocr_done.value, processing_task_id=None)
            )
            session.commit()
        return {"status": "completed"}
    except Exception as exc:  # pragma: no cover
        with get_session() as session:
            session.execute(
                Document.__table__.update()
                .where(Document.id == document_id)
                .values(status=DocumentStatus.failed.value, processing_task_id=None)
            )
            session.execute(
                DocumentPage.__table__.update()
                .where(DocumentPage.document_id == document_id)
                .values(status=DocumentStatus.failed.value)
            )
            session.add(
                AuditLog(
                    id=os.urandom(16).hex(),
                    document_id=document_id,
                    event_type="ocr_failed",
                    detail=str(exc),
                )
            )
            session.commit()
        raise


@celery_app.task(name="vera.recover_stuck_documents")
def recover_stuck_documents() -> dict[str, int]:
    """Mark documents stuck in processing longer than timeout as failed."""
    timeout_minutes = int(os.getenv("STUCK_TASK_TIMEOUT_MINUTES", "30"))
    cutoff = datetime.utcnow() - timedelta(minutes=timeout_minutes)
    with get_session() as session:
        stuck_docs = session.execute(
            select(Document).where(
                Document.status == DocumentStatus.processing.value,
                Document.updated_at < cutoff,
            )
        ).scalars().all()
        for doc in stuck_docs:
            session.execute(
                Document.__table__.update()
                .where(Document.id == doc.id)
                .values(status=DocumentStatus.failed.value, processing_task_id=None)
            )
            session.execute(
                DocumentPage.__table__.update()
                .where(
                    DocumentPage.document_id == doc.id,
                    DocumentPage.status == DocumentStatus.processing.value,
                )
                .values(status=DocumentStatus.failed.value)
            )
            session.add(
                AuditLog(
                    id=os.urandom(16).hex(),
                    document_id=doc.id,
                    event_type="auto_failed",
                    detail=json.dumps({
                        "reason": "stuck_in_processing",
                        "timeout_minutes": timeout_minutes,
                    }),
                )
            )
        session.commit()
        if stuck_docs:
            logger.warning("Recovered %d stuck document(s)", len(stuck_docs))
        return {"recovered": len(stuck_docs)}


@celery_app.task(name="vera.cleanup_documents")
def cleanup_documents_task() -> dict[str, int | str]:
    return cleanup_documents()
