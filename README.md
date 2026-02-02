# VERA — Validated Extraction & Review Assistant

VERA is a verification-first OCR application that extracts text from document images, highlights low-confidence interpretations, allows the user to correct them, and only then produces trustworthy summaries and structured output.

## v1 Scope (Non-negotiable)
- Inputs: JPG, PNG
- Target documents: receipts, invoices
- Language: English only

## Architecture
- Frontend: Next.js (React)
- Backend: FastAPI (Python)
- OCR: PaddleOCR (local, offline)
- Storage: SQLite + local file storage

## Document Lifecycle
`uploaded -> ocr_done -> review_in_progress -> validated -> summarized -> exported`

Validation is a hard gate. Summaries and exports are only available after explicit review completion.

## Repository Structure
See `vera/` layout as specified in the project brief. The backend and frontend are intentionally simple and readable.

## Getting Started (Skeleton)
1. Backend: `cd vera/backend` then install requirements and run `uvicorn app.main:app --reload`.
2. Frontend: `cd vera/frontend` then initialize Next.js and wire the components.

This repo is intentionally a scaffold for v1. The next steps are to implement OCR in the backend, then build the frontend overlay and validation flow.
