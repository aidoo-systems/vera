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

## Getting Started (Docker)
1. `docker compose up -d --build`
2. Frontend: `http://localhost:3000`
3. Backend: `http://localhost:4000`

## Getting Started (Local)
1. Backend: `cd backend` → `pip install -r requirements.txt` → `uvicorn app.main:app --reload --port 8000`
2. Frontend: `cd frontend` → `npm install` → `npm run dev`

## Notes
- PDF support requires Poppler (Docker image installs it automatically).
- Summaries and exports are gated behind explicit review completion.
