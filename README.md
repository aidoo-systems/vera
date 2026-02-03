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
`uploaded -> ocr_done -> review_in_progress -> validated -> summarized -> exported`

Validation is a hard gate. Summaries and exports are only available after explicit review completion.

## Getting Started (Docker, On-Prem)
1. `docker compose up -d --build`
2. Run migrations: `docker compose exec backend alembic upgrade head`
3. Frontend: `http://localhost:3000`
4. Backend: `http://localhost:4000`

## Getting Started (Local)
1. Backend: `cd backend` → `pip install -r requirements.txt`
2. Set `DATABASE_URL` (Postgres recommended). Example:
   `postgresql+psycopg://vera:vera@localhost:5432/vera`
3. Run migrations: `alembic upgrade head`
4. Start API: `uvicorn app.main:app --reload --port 8000`
5. Start worker: `celery -A app.worker.celery_app worker --loglevel=info --concurrency=2`
6. Frontend: `cd frontend` → `npm install` → `npm run dev`

## Notes
- PDF support requires Poppler (Docker image installs it automatically).
- Summaries and exports are gated behind explicit review completion.
