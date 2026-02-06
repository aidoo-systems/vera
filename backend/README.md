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
- `GET /documents/{id}/pages/{page_id}`
- `POST /documents/{id}/pages/{page_id}/validate`
- `GET /documents/{id}/pages/status`
- `GET /documents/{id}/pages/{page_id}/status`
- `GET /documents/{id}/status/stream`
- `GET /documents/{id}/pages/{page_id}/summary`
- `GET /documents/{id}/pages/{page_id}/export`
- `GET /documents/{id}/summary`
- `GET /documents/{id}/export`
- `POST /llm/models/pull/stream`
- `GET /health`
- `GET /metrics`

Validation requires an explicit `review_complete` flag before summaries or exports are available.
Page summaries/exports are available once that page is reviewed; document summary/export requires all pages.

## Security & limits
- `MAX_UPLOAD_MB` (default: 25)
- `STRICT_MIME_VALIDATION` (default: 1)
- `UPLOAD_RATE_LIMIT` (default: `10/minute`)
- Optional malware scan: set `VIRUS_SCAN_COMMAND` to a shell command that returns non-zero on failure.

## Retention
- `RETENTION_DAYS` (default: 30)
- `RETENTION_TRIGGER` (`post_export` or `post_review`)
- `RETENTION_MODE` (`delete` or `archive`)
- `RETENTION_ARCHIVE_DIR` (default: `./archive`)
- `RETENTION_INTERVAL_MINUTES` (default: 1440)

## Summary extraction
- Offline summaries generate a detailed, ordered page summary from validated text.
- Optional AI summaries use Ollama when a `model` query parameter is provided; failures fall back to offline summaries.
- `EXTRACTION_RULES_PATH` (default: `app/config/extraction_rules.json`)
- `SUMMARY_MAX_CHARS` (default: `2000`)
- `OLLAMA_RETRIES` (default: `2`)

## Document lifecycle
`uploaded -> ocr_done -> review_in_progress -> validated -> summarized -> exported`

## Tests
Run from `backend/`:
- `pytest`
