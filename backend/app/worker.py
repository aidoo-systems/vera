from __future__ import annotations

import os

try:
    from celery import Celery
except ImportError:  # pragma: no cover
    Celery = None

from app.db.session import Base, engine, get_session
from app.models.documents import AuditLog, Document
from app.schemas.documents import DocumentStatus
from app.services.ocr import run_ocr_for_document

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
    )


@celery_app.task(name="vera.process_document")
def process_document(document_id: str) -> dict[str, str]:
    Base.metadata.create_all(bind=engine)
    with get_session() as session:
        document = session.get(Document, document_id)
        if document is None:
            return {"status": "missing"}
        image_path = str(getattr(document, "image_path"))
        session.execute(
            Document.__table__.update()
            .where(Document.id == document_id)
            .values(status=DocumentStatus.processing.value)
        )
        session.commit()

    try:
        image_url = f"/files/{os.path.basename(image_path)}"
        run_ocr_for_document(document_id, image_path, image_url)
        return {"status": "completed"}
    except Exception as exc:  # pragma: no cover
        with get_session() as session:
            session.execute(
                Document.__table__.update()
                .where(Document.id == document_id)
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
