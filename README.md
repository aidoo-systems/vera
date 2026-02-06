# VERA — Validated Extraction & Review Assistant

VERA is a verification-first OCR application that extracts text from document images and PDFs, highlights low-confidence interpretations, lets users confirm corrections, and produces trustworthy summaries and structured output.

## v1 Scope
- Inputs: JPG, PNG, PDF (multi-page supported)
- Target documents: receipts, invoices, general business documents
- Language: English only

## Architecture
- Frontend: Next.js (React)
- Backend: FastAPI (Python)
- OCR: PaddleOCR (local, offline)
- Storage: SQLite + local file storage

## Document Lifecycle
`uploaded -> ocr_done -> review_in_progress -> validated -> summarized -> exported (or canceled)`

For multi-page PDFs, each page is reviewed independently. Page summaries/exports unlock per-page,
while document summaries/exports require all pages to be reviewed.

Validation is a hard gate. Summaries and exports are only available after explicit review completion.

## Getting Started (Docker, On-Prem)
1. `docker compose up -d --build`
2. Run migrations: `docker compose exec backend alembic upgrade head`
3. Frontend: `http://localhost:3000`
4. Backend: `http://localhost:4000`

If your database already has tables but Alembic has never been run (no `alembic_version` table),
you will see a `DuplicateTable` error when running migrations. In that case, stamp the baseline
before upgrading so Alembic knows the current schema state:
1. `docker compose exec backend alembic stamp 0001_create_tables`
2. `docker compose exec backend alembic upgrade head`

## Getting Started (Local)
1. Backend: `cd backend` → `pip install -r requirements.txt`
2. Set `DATABASE_URL` (Postgres recommended). Example:
   `postgresql+psycopg://vera:vera@localhost:5432/vera`
3. Run migrations: `alembic upgrade head`
4. Start API: `uvicorn app.main:app --reload --port 8000`
5. Start worker: `celery -A app.worker.celery_app worker --loglevel=info --concurrency=2`
6. Frontend: `cd frontend` → `npm install` → `npm run dev`

If your local database was created before Alembic was introduced, use the same baseline stamp
to avoid `DuplicateTable` errors:
1. `alembic stamp 0001_create_tables`
2. `alembic upgrade head`

## Notes
- PDF support requires Poppler (Docker image installs it automatically).
- Summaries and exports are gated behind explicit review completion.
- Page summaries/exports are available once that page is reviewed; document summary/export requires all pages.
- Document-level summary/export UI is only shown for multi-page documents.
- AI summaries use Ollama only when enabled in Settings; if Ollama is unavailable, offline detailed summaries are used.
- Uploads enforce file size and MIME validation; configure limits with `MAX_UPLOAD_MB` and `STRICT_MIME_VALIDATION`.

## Optional LLM summaries (Ollama)
VERA can optionally call an Ollama instance to generate a detailed summary for each page. Toggle AI summaries from Settings in the UI (the toggle is disabled unless Ollama is reachable).

Environment variables:
- `OLLAMA_URL` (default: `http://localhost:11434`)
- `OLLAMA_MODEL` (default: `llama3.1`)
- `OLLAMA_TIMEOUT` (default: `300` seconds)
- `OLLAMA_RETRIES` (default: `2`)
- `SUMMARY_MAX_CHARS` (default: `2000`)

When enabled, the backend will call `POST /api/generate` on the Ollama URL and use the returned detailed summary
in the Summary view. If Ollama is unavailable or times out, the backend falls back to offline detailed summaries
and the UI shows a warning toast.

If you run the backend in Docker but Ollama runs on your host, set `OLLAMA_URL=http://host.docker.internal:11434`.

## Status streaming
Document status updates are available via polling or Server-Sent Events:
- `GET /documents/{id}/pages/status`
- `GET /documents/{id}/status/stream`

## Retention
Set cleanup behavior with:
- `RETENTION_DAYS` (default: 30)
- `RETENTION_TRIGGER` (`post_export` or `post_review`)
- `RETENTION_MODE` (`delete` or `archive`)
- `RETENTION_ARCHIVE_DIR` (default: `./archive`)
- `RETENTION_INTERVAL_MINUTES` (default: 1440)

Run Celery beat to enable scheduled cleanup.

## Observability
- Request IDs are echoed in `X-Request-ID`.
- Metrics exposed at `GET /metrics`.

## Tests
- Backend: `cd backend && pytest`
- Frontend: `cd frontend && npm run test`

## Detected patterns
The summary view extracts the following patterns when possible (amounts are normalized):
- Dates (multiple formats)
- Amounts (symbols, currency codes, and totals)
- Invoice/Order IDs
- Emails
- Phone numbers
- Tax/VAT IDs

Extraction rules can be customized via `EXTRACTION_RULES_PATH` (JSON) to tune document-type keywords and term lists.
