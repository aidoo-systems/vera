# VERA Backend

FastAPI service for OCR, confidence analysis, validation, and summary generation.

## Run (local)
1. Install dependencies: `pip install -r requirements.txt`
2. Install Poppler for PDF support (required for `pdf2image`).
3. Set `DATABASE_URL` for Postgres (recommended) or fallback to SQLite.
4. Run migrations: `alembic upgrade head`
5. Start API: `uvicorn app.main:app --reload --port 8000`
6. Start worker: `celery -A app.worker.celery_app worker --loglevel=info --concurrency=2`

## Reset local DB
If your schema changes, reset the local SQLite data directory:
`python scripts/reset_db.py`

## Docker
The Docker image installs Poppler + runtime libraries needed by PaddleOCR/OpenCV.
Use `docker compose exec backend alembic upgrade head` after first startup.

## API (v1 contract)
- `POST /documents/upload`
- `GET /documents/{id}`
- `POST /documents/{id}/validate`
- `GET /documents/{id}/summary`
- `GET /documents/{id}/export`
- `GET /health`

Validation requires an explicit `review_complete` flag before summaries or exports are available.

## Document lifecycle
`uploaded -> ocr_done -> review_in_progress -> validated -> summarized -> exported`
