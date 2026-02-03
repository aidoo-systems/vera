# VERA — Validated Extraction & Review Assistant

VERA is a verification-first OCR application that extracts text from document images and PDFs, highlights low-confidence interpretations, lets users confirm corrections, and produces trustworthy summaries and structured output.

## v1 Scope
- Inputs: JPG, PNG, PDF
- Target documents: receipts, invoices, general business documents
- Language: English only

## Architecture
- Frontend: Next.js (React)
- Backend: FastAPI (Python)
- OCR: PaddleOCR (local, offline)
- Storage: SQLite + local file storage

## Document Lifecycle
`uploaded -> ocr_done -> review_in_progress -> validated -> summarized -> exported (or canceled)`

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
- AI summaries use Ollama only when enabled in Settings; failures do not fallback to offline summaries.

## Optional LLM summaries (Ollama)
VERA can optionally call an Ollama instance to generate smart summary points. Toggle AI summaries from Settings in the UI.

Environment variables:
- `OLLAMA_URL` (default: `http://localhost:11434`)
- `OLLAMA_MODEL` (default: `llama3.1`)
- `OLLAMA_TIMEOUT` (default: `300` seconds)

When enabled, the backend will call `POST /api/generate` on the Ollama URL and use the returned bullet points
in the Summary view. If Ollama is unavailable or times out, the summary remains unchanged and the UI shows
a warning toast. AI mode does not fallback to offline summaries.

If you run the backend in Docker but Ollama runs on your host, set `OLLAMA_URL=http://host.docker.internal:11434`.

## Detected patterns
The summary view extracts the following patterns when possible (amounts are normalized):
- Dates (multiple formats)
- Amounts (symbols, currency codes, and totals)
- Invoice/Order IDs
- Emails
- Phone numbers
- Tax/VAT IDs
