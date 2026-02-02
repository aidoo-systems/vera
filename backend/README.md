# VERA Backend

FastAPI service for OCR, confidence analysis, validation, and summary generation.

## Run (local)
1. Install dependencies: `pip install -r requirements.txt`
2. Install Poppler for PDF support (required for `pdf2image`).
3. Start API: `uvicorn app.main:app --reload --port 8000`

## Reset local DB
If your schema changes, reset the local SQLite data directory:
`python scripts/reset_db.py`

## Docker
The Docker image installs Poppler + runtime libraries needed by PaddleOCR/OpenCV.

## API (v1 contract)
- `POST /documents/upload`
- `GET /documents/{id}`
- `POST /documents/{id}/validate`
- `GET /documents/{id}/summary`
- `GET /documents/{id}/export`

Validation requires an explicit `review_complete` flag before summaries or exports are available.

## Document lifecycle
`uploaded -> ocr_done -> review_in_progress -> validated -> summarized -> exported`
